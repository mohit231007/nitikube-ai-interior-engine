import json

import pytest

from nitikube.standards import (
    NumericRule,
    RuleContext,
    RuleOperator,
    RuleStatus,
    StandardSource,
    convert_value,
    detect_conflicts,
    evaluate_rule,
    evaluate_rules,
    load_rules_csv,
    load_rules_json,
    rule_interval,
    validate_rule,
)


def source(**overrides):
    data = {
        "title": "Test Standard",
        "authority": "Test Authority",
        "jurisdiction": "India",
        "document_version": "2026-test",
        "source_url": "https://example.com/standard",
        "checked_at": "2026-08-11T18:00:00+00:00",
        "effective_date": "2026-01-01",
        "locator": "Section X",
    }
    data.update(overrides)
    return StandardSource(**data)


def rule(rule_id="r1", **overrides):
    data = {
        "rule_id": rule_id,
        "subject": "circulation",
        "metric": "passage_width",
        "operator": RuleOperator.MIN,
        "value": 900,
        "unit": "mm",
        "source": source(),
        "room_types": ("bathroom",),
        "applicability_tags": ("residential",),
        "mandatory": True,
        "summary": "Synthetic test rule only",
    }
    data.update(overrides)
    return NumericRule(**data)


def test_supported_length_and_airflow_unit_conversions():
    assert convert_value(1000, "mm", "m") == pytest.approx(1.0)
    assert convert_value(1, "ft", "mm") == pytest.approx(304.8)
    assert convert_value(100, "cfm", "m3/h") == pytest.approx(169.901079552)
    with pytest.raises(ValueError, match="incompatible"):
        convert_value(100, "lux", "mm")


def test_standard_source_requires_http_url_and_timezone_timestamp():
    bad_url = rule(source=source(source_url="file:///standard.pdf"))
    with pytest.raises(ValueError, match="http"):
        validate_rule(bad_url)
    bad_time = rule(source=source(checked_at="2026-08-11T18:00:00"))
    with pytest.raises(ValueError, match="timezone"):
        validate_rule(bad_time)


def test_range_rule_requires_upper_bound_and_order():
    with pytest.raises(ValueError, match="requires finite upper_value"):
        validate_rule(rule(operator=RuleOperator.RANGE, value=1, unit="m", upper_value=None))
    with pytest.raises(ValueError, match="cannot be below"):
        validate_rule(rule(operator=RuleOperator.RANGE, value=2, upper_value=1, unit="m"))


def test_rule_interval_normalizes_to_canonical_units():
    lower, upper, unit = rule_interval(rule(value=900, unit="mm"))
    assert lower == pytest.approx(0.9)
    assert upper == pytest.approx(float("inf"))
    assert unit == "m"


def test_rule_evaluation_passes_after_unit_normalization():
    result = evaluate_rule(
        rule(),
        actual_value=3.0,
        actual_unit="ft",
        context=RuleContext(room_type="bathroom", tags=("residential",), jurisdiction="India"),
    )
    assert result.status == RuleStatus.PASS
    assert result.normalized_actual == pytest.approx(0.9144)
    assert result.normalized_unit == "m"


def test_failed_and_unknown_are_distinct():
    context = RuleContext(room_type="bathroom", tags=("residential",), jurisdiction="India")
    failed = evaluate_rule(rule(), 800, "mm", context=context)
    unknown = evaluate_rule(rule(), None, None, context=context)
    assert failed.status == RuleStatus.FAIL
    assert unknown.status == RuleStatus.UNKNOWN
    assert unknown.normalized_actual is None


def test_incompatible_actual_unit_is_unknown_not_compliant():
    result = evaluate_rule(
        rule(),
        100,
        "lux",
        context=RuleContext(room_type="bathroom", tags=("residential",), jurisdiction="India"),
    )
    assert result.status == RuleStatus.UNKNOWN
    assert "cannot be compared" in result.reason


def test_context_controls_room_tags_and_jurisdiction_applicability():
    base = rule()
    assert evaluate_rule(base, 1, "m", context=RuleContext(room_type="bedroom", tags=("residential",), jurisdiction="India")).status == RuleStatus.NOT_APPLICABLE
    assert evaluate_rule(base, 1, "m", context=RuleContext(room_type="bathroom", tags=("commercial",), jurisdiction="India")).status == RuleStatus.NOT_APPLICABLE
    assert evaluate_rule(base, 1, "m", context=RuleContext(room_type="bathroom", tags=("residential",), jurisdiction="Norway")).status == RuleStatus.NOT_APPLICABLE


def test_global_rule_can_apply_under_specific_jurisdiction_context():
    global_rule = rule(source=source(jurisdiction="Global"))
    result = evaluate_rule(
        global_rule,
        1,
        "m",
        context=RuleContext(room_type="bathroom", tags=("residential",), jurisdiction="India"),
    )
    assert result.status == RuleStatus.PASS


def test_evaluate_rules_joins_actuals_by_exact_metric_name():
    rules = [
        rule("r1", metric="passage_width"),
        rule("r2", metric="fixture_front_clearance", value=700),
    ]
    actuals = {"passage_width": (950, "mm"), "fixture_front_clearance": (650, "mm")}
    results = evaluate_rules(
        rules,
        actuals,
        context=RuleContext(room_type="bathroom", tags=("residential",), jurisdiction="India"),
    )
    assert [result.status for result in results] == [RuleStatus.PASS, RuleStatus.FAIL]


def test_conflict_detection_surfaces_disjoint_same_scope_rules():
    rules = [
        rule("min1", operator=RuleOperator.MIN, value=1000, unit="mm"),
        rule("max1", operator=RuleOperator.MAX, value=900, unit="mm"),
    ]
    conflicts = detect_conflicts(rules)
    assert len(conflicts) == 1
    assert set(conflicts[0].rule_ids) == {"min1", "max1"}
    assert conflicts[0].normalized_unit == "m"


def test_different_jurisdictions_are_not_called_conflicts():
    rules = [
        rule("india", operator=RuleOperator.MIN, value=1000, source=source(jurisdiction="India")),
        rule("norway", operator=RuleOperator.MAX, value=900, source=source(jurisdiction="Norway")),
    ]
    assert detect_conflicts(rules) == ()


def test_overlapping_same_scope_intervals_are_not_conflicts():
    rules = [
        rule("min", operator=RuleOperator.MIN, value=800),
        rule("max", operator=RuleOperator.MAX, value=1200),
    ]
    assert detect_conflicts(rules) == ()


def test_json_loader_requires_unique_rule_ids_and_source_provenance():
    row = {
        "rule_id": "r1",
        "subject": "lighting",
        "metric": "illuminance",
        "operator": "range",
        "value": 100,
        "upper_value": 200,
        "unit": "lux",
        "room_types": ["living"],
        "applicability_tags": ["residential"],
        "mandatory": False,
        "summary": "Synthetic test only",
        "source": {
            "title": "Synthetic",
            "authority": "Test",
            "jurisdiction": "Global",
            "document_version": "1",
            "source_url": "https://example.com/s",
            "checked_at": "2026-08-11T18:00:00+00:00",
        },
    }
    rules = load_rules_json(json.dumps({"rules": [row]}))
    assert rules[0].operator == RuleOperator.RANGE
    duplicate = json.dumps({"rules": [row, row]})
    with pytest.raises(ValueError, match="unique"):
        load_rules_json(duplicate)


def test_csv_loader_supports_flat_source_columns_and_pipe_lists():
    payload = """rule_id,subject,metric,operator,value,upper_value,unit,room_types,applicability_tags,mandatory,title,authority,jurisdiction,document_version,source_url,checked_at,effective_date,locator,summary
r1,circulation,passage_width,min,900,,mm,bathroom|kitchen,residential|dwelling,true,Synthetic,Test Authority,India,1,https://example.com/s,2026-08-11T18:00:00+00:00,2026-01-01,Section X,Test only
"""
    rules = load_rules_csv(payload)
    assert len(rules) == 1
    assert rules[0].room_types == ("bathroom", "kitchen")
    assert rules[0].applicability_tags == ("residential", "dwelling")
    assert rules[0].mandatory is True
