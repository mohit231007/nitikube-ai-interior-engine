from __future__ import annotations

from dataclasses import asdict, dataclass
from html import escape
import hashlib
import json
from typing import Any, Mapping, Sequence

from .project_orchestrator import verify_design_package_hash


@dataclass(frozen=True)
class ReportAudit:
    package_hash_valid: bool
    selected_room_count: int
    required_room_count: int
    professional_verification_flag_count: int
    standard_pass_count: int
    standard_fail_count: int
    standard_unknown_count: int
    standard_not_applicable_count: int
    mandatory_standard_unresolved_count: int
    lifecycle_feasible_count: int
    lifecycle_nonfeasible_count: int
    warnings: tuple[str, ...]


@dataclass(frozen=True)
class FinalReportArtifact:
    report_id: str
    html: str
    audit: ReportAudit


def _load_json(payload: str | bytes | Mapping[str, Any]) -> dict[str, Any]:
    if isinstance(payload, Mapping):
        return dict(payload)
    if isinstance(payload, bytes):
        payload = payload.decode("utf-8")
    data = json.loads(payload)
    if not isinstance(data, dict):
        raise ValueError("expected a JSON object")
    return data


def validate_design_package(package: Mapping[str, Any]) -> None:
    if package.get("schema") != "nitikube.design_package":
        raise ValueError("not a nitikube.design_package artifact")
    if not str(package.get("schema_version") or "").strip():
        raise ValueError("design package schema_version is required")
    if not str(package.get("package_id") or "").strip():
        raise ValueError("design package package_id is required")
    required_room_ids = package.get("required_room_ids")
    selected = package.get("selected_options")
    if not isinstance(required_room_ids, list) or not required_room_ids:
        raise ValueError("design package requires non-empty required_room_ids")
    if not isinstance(selected, list):
        raise ValueError("design package selected_options must be a list")


def _standards_summary(standards: Mapping[str, Any] | None) -> dict[str, int]:
    summary = {"pass": 0, "fail": 0, "unknown": 0, "not_applicable": 0, "mandatory_unresolved": 0}
    if standards is None:
        return summary
    if standards.get("schema") != "nitikube.rule_evaluation":
        raise ValueError("standards attachment is not nitikube.rule_evaluation")
    results = standards.get("results")
    if not isinstance(results, list):
        raise ValueError("standards attachment results must be a list")
    for row in results:
        status = str(row.get("status") or "").casefold()
        if status in summary:
            summary[status] += 1
        if bool(row.get("mandatory")) and status in {"fail", "unknown"}:
            summary["mandatory_unresolved"] += 1
    return summary


def _lifecycle_summary(lifecycle: Mapping[str, Any] | None) -> dict[str, int]:
    summary = {"feasible": 0, "nonfeasible": 0}
    if lifecycle is None:
        return summary
    if lifecycle.get("schema") != "nitikube.lifecycle_comparison":
        raise ValueError("lifecycle attachment is not nitikube.lifecycle_comparison")
    results = lifecycle.get("results")
    if not isinstance(results, list):
        raise ValueError("lifecycle attachment results must be a list")
    for row in results:
        if bool(row.get("feasible")):
            summary["feasible"] += 1
        else:
            summary["nonfeasible"] += 1
    return summary


def audit_report_inputs(
    design_package: str | bytes | Mapping[str, Any],
    *,
    standards_evaluation: str | bytes | Mapping[str, Any] | None = None,
    lifecycle_comparison: str | bytes | Mapping[str, Any] | None = None,
) -> ReportAudit:
    package = _load_json(design_package)
    validate_design_package(package)
    standards = _load_json(standards_evaluation) if standards_evaluation is not None else None
    lifecycle = _load_json(lifecycle_comparison) if lifecycle_comparison is not None else None
    standards_summary = _standards_summary(standards)
    lifecycle_summary = _lifecycle_summary(lifecycle)
    hash_valid = verify_design_package_hash(package)
    flags = package.get("professional_verification_flags") or []
    warnings: list[str] = []
    if not hash_valid:
        warnings.append("design package hash verification failed")
    if len(package.get("selected_options") or []) != len(package.get("required_room_ids") or []):
        warnings.append("selected room count differs from required room count")
    if standards is None:
        warnings.append("no standards/guidance evaluation artifact attached")
    elif standards_summary["mandatory_unresolved"]:
        warnings.append("mandatory standards/guidance results contain FAIL/UNKNOWN states")
    if lifecycle is None:
        warnings.append("no lifecycle material comparison artifact attached")
    elif lifecycle_summary["nonfeasible"]:
        warnings.append("lifecycle comparison contains non-feasible/unknown options")
    if flags:
        warnings.append("professional verification flags remain open in the design package")

    return ReportAudit(
        package_hash_valid=hash_valid,
        selected_room_count=len(package.get("selected_options") or []),
        required_room_count=len(package.get("required_room_ids") or []),
        professional_verification_flag_count=len(flags),
        standard_pass_count=standards_summary["pass"],
        standard_fail_count=standards_summary["fail"],
        standard_unknown_count=standards_summary["unknown"],
        standard_not_applicable_count=standards_summary["not_applicable"],
        mandatory_standard_unresolved_count=standards_summary["mandatory_unresolved"],
        lifecycle_feasible_count=lifecycle_summary["feasible"],
        lifecycle_nonfeasible_count=lifecycle_summary["nonfeasible"],
        warnings=tuple(warnings),
    )


def _money(value: Any) -> str:
    try:
        return f"₹{float(value):,.0f}"
    except (TypeError, ValueError):
        return "—"


def _number(value: Any, digits: int = 2) -> str:
    try:
        return f"{float(value):,.{digits}f}"
    except (TypeError, ValueError):
        return "—"


def _table(headers: Sequence[str], rows: Sequence[Sequence[Any]]) -> str:
    head = "".join(f"<th>{escape(str(header))}</th>" for header in headers)
    body = "".join(
        "<tr>" + "".join(f"<td>{escape(str(value))}</td>" for value in row) + "</tr>"
        for row in rows
    )
    return f"<div class='table-wrap'><table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>"


def _selected_options_section(package: Mapping[str, Any]) -> str:
    rows = []
    for item in package.get("selected_options") or []:
        rows.append(
            (
                item.get("room_id", ""),
                item.get("option_id", ""),
                item.get("name", ""),
                _money(item.get("cost")),
                _number(item.get("utility"), 2),
                item.get("score_source", ""),
                item.get("source_artifact", ""),
                str(item.get("source_sha256", ""))[:16] + "…" if item.get("source_sha256") else "",
            )
        )
    return _table(
        ["Room", "Option", "Design package", "Cost", "Utility", "Score source", "Source artifact", "Source SHA"],
        rows,
    )


def _artifact_section(package: Mapping[str, Any]) -> str:
    refs = []
    geometry = package.get("geometry_artifact")
    if isinstance(geometry, Mapping):
        refs.append(geometry)
    refs.extend(ref for ref in package.get("option_artifacts") or [] if isinstance(ref, Mapping))
    rows = [
        (
            ref.get("name", ""),
            ref.get("kind", ""),
            str(ref.get("sha256", ""))[:20] + "…" if ref.get("sha256") else "",
            ref.get("bytes_size", ""),
        )
        for ref in refs
    ]
    return _table(["Artifact", "Kind", "SHA-256", "Bytes"], rows)


def _standards_section(standards: Mapping[str, Any] | None) -> str:
    if standards is None:
        return "<p class='unknown'>No standards/guidance evaluation artifact was attached.</p>"
    rows = []
    for item in standards.get("results") or []:
        rows.append(
            (
                item.get("rule_id", ""),
                item.get("status", ""),
                item.get("actual_value", ""),
                item.get("actual_unit", ""),
                item.get("normalized_actual", ""),
                item.get("normalized_unit", ""),
                "YES" if item.get("mandatory") else "NO",
                item.get("reason", ""),
            )
        )
    return _table(
        ["Rule", "Status", "Actual", "Unit", "Normalized", "Canonical unit", "Mandatory", "Reason"],
        rows,
    )


def _lifecycle_section(lifecycle: Mapping[str, Any] | None) -> str:
    if lifecycle is None:
        return "<p class='unknown'>No lifecycle material comparison artifact was attached.</p>"
    rows = []
    for item in lifecycle.get("results") or []:
        rows.append(
            (
                item.get("option_id", ""),
                "YES" if item.get("feasible") else "NO",
                _money(item.get("initial_installed_cost")),
                item.get("replacement_count", ""),
                _money(item.get("npv_cost")),
                _money(item.get("equivalent_annual_cost")),
                _number(item.get("npv_cost_per_area"), 2),
                ", ".join(item.get("unknown_fields") or []),
                ", ".join(item.get("failed_constraints") or []),
            )
        )
    return _table(
        ["Option", "Feasible", "Initial", "Replacements", "NPV cost", "Equivalent annual", "NPV / area", "Unknown", "Failed constraints"],
        rows,
    )


def _flags_section(package: Mapping[str, Any]) -> str:
    flags = package.get("professional_verification_flags") or []
    if not flags:
        return "<p class='good'>No project-specific professional-verification flags are recorded in this package.</p>"
    return "<ul class='flags'>" + "".join(f"<li>{escape(str(flag))}</li>" for flag in flags) + "</ul>"


def _warnings_section(audit: ReportAudit) -> str:
    if not audit.warnings:
        return "<p class='good'>No report-level warnings were generated from the attached artifacts.</p>"
    return "<ul class='warnings'>" + "".join(f"<li>{escape(warning)}</li>" for warning in audit.warnings) + "</ul>"


def render_final_report(
    design_package: str | bytes | Mapping[str, Any],
    *,
    standards_evaluation: str | bytes | Mapping[str, Any] | None = None,
    lifecycle_comparison: str | bytes | Mapping[str, Any] | None = None,
    allow_invalid_package_hash: bool = False,
) -> FinalReportArtifact:
    package = _load_json(design_package)
    validate_design_package(package)
    standards = _load_json(standards_evaluation) if standards_evaluation is not None else None
    lifecycle = _load_json(lifecycle_comparison) if lifecycle_comparison is not None else None
    audit = audit_report_inputs(package, standards_evaluation=standards, lifecycle_comparison=lifecycle)
    if not audit.package_hash_valid and not allow_invalid_package_hash:
        raise ValueError("design package hash is invalid; report generation is blocked unless explicitly overridden")

    project_name = escape(str(package.get("project_name") or "NitiKube Project"))
    package_id = escape(str(package.get("package_id") or ""))
    created_at = escape(str(package.get("created_at") or ""))
    required_rooms = ", ".join(escape(str(room_id)) for room_id in package.get("required_room_ids") or [])
    hash_status = "PASS" if audit.package_hash_valid else "FAIL / OVERRIDDEN"
    html = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>{project_name} — NitiKube Design Package</title>
<style>
:root{{--ink:#17202a;--muted:#667085;--line:#d0d5dd;--paper:#fff;--soft:#f8fafc;--ok:#166534;--warn:#92400e;--bad:#991b1b}}
*{{box-sizing:border-box}}body{{font-family:Arial,Helvetica,sans-serif;color:var(--ink);background:var(--paper);margin:0;line-height:1.45}}
main{{max-width:1200px;margin:0 auto;padding:36px}}h1{{margin:0 0 6px;font-size:30px}}h2{{border-bottom:1px solid var(--line);padding-bottom:8px;margin-top:34px}}h3{{margin-top:26px}}
.tagline{{color:var(--muted);font-size:16px}}.meta{{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px;margin:24px 0}}.card{{border:1px solid var(--line);border-radius:10px;padding:14px;background:var(--soft)}}.label{{font-size:11px;text-transform:uppercase;letter-spacing:.05em;color:var(--muted)}}.value{{font-size:18px;font-weight:700;margin-top:4px}}.table-wrap{{overflow-x:auto}}table{{border-collapse:collapse;width:100%;font-size:12px}}th,td{{border:1px solid var(--line);padding:8px;vertical-align:top;text-align:left}}th{{background:var(--soft)}}.good{{color:var(--ok)}}.unknown{{color:var(--warn)}}.warnings,.flags{{padding-left:20px}}.warnings li{{color:var(--warn);margin:5px 0}}.flags li{{color:var(--bad);margin:5px 0}}code{{word-break:break-all}}.footnote{{font-size:12px;color:var(--muted);margin-top:32px}}@media print{{main{{max-width:none;padding:10mm}}.table-wrap{{overflow:visible}}}}
</style>
</head>
<body><main>
<h1>{project_name}</h1>
<div class="tagline">NitiKube Interior DesignOS · Measured interiors. Verified decisions.</div>
<div class="meta">
  <div class="card"><div class="label">Package hash</div><div class="value">{hash_status}</div></div>
  <div class="card"><div class="label">Selected rooms</div><div class="value">{audit.selected_room_count} / {audit.required_room_count}</div></div>
  <div class="card"><div class="label">Selected cost</div><div class="value">{_money(package.get('selected_cost'))}</div></div>
  <div class="card"><div class="label">Budget remaining</div><div class="value">{_money(package.get('budget_remaining'))}</div></div>
</div>
<p><strong>Created:</strong> {created_at}</p>
<p><strong>Package ID:</strong> <code>{package_id}</code></p>
<p><strong>Required room IDs:</strong> {required_rooms}</p>

<h2>Executive audit</h2>
{_warnings_section(audit)}
<p>This report is assembled deterministically from the attached NitiKube artifacts. It does not upgrade UNKNOWN/UNVERIFIED inputs into verified facts and does not clear professional-verification requirements.</p>

<h2>Selected room design packages</h2>
{_selected_options_section(package)}

<h2>Input artifact provenance</h2>
{_artifact_section(package)}

<h2>Open professional-verification flags</h2>
{_flags_section(package)}

<h2>Standards / guidance evidence</h2>
<p>PASS: {audit.standard_pass_count} · FAIL: {audit.standard_fail_count} · UNKNOWN: {audit.standard_unknown_count} · N/A: {audit.standard_not_applicable_count} · mandatory unresolved: {audit.mandatory_standard_unresolved_count}</p>
{_standards_section(standards)}

<h2>Lifecycle material value</h2>
<p>Feasible compared options: {audit.lifecycle_feasible_count} · non-feasible/unknown: {audit.lifecycle_nonfeasible_count}</p>
{_lifecycle_section(lifecycle)}

<h2>Calculation/evidence contract</h2>
<ul>
<li>Geometry and hard feasibility are owned by deterministic room/geometry engines.</li>
<li>Lighting may use lumen/beam methods or uploaded manufacturer IES point-by-point photometry; unsupported photometric cases fail closed.</li>
<li>Material facts, prices and standards require source/evidence states rather than model memory.</li>
<li>Climate/geography recommendations are driven by measured/modelled variables, not city-name stereotypes.</li>
<li>Budget optimisation selects among already-feasible options; it does not make unsafe geometry feasible.</li>
<li>Lifecycle cost is conditional on explicit service-life, maintenance, escalation and discount assumptions.</li>
<li>Professional/regulatory verification remains required wherever flagged.</li>
</ul>

<div class="footnote">Generated by NitiKube deterministic report renderer. The report itself is an aid for decision-making and contractor/professional coordination; it is not a stamped architectural/structural/electrical/plumbing approval.</div>
</main></body></html>"""
    report_id = hashlib.sha256(html.encode("utf-8")).hexdigest()
    return FinalReportArtifact(report_id=report_id, html=html, audit=audit)


def audit_json(artifact: FinalReportArtifact) -> str:
    return json.dumps(
        {
            "schema": "nitikube.final_report_audit",
            "schema_version": "0.22",
            "report_id": artifact.report_id,
            "audit": asdict(artifact.audit),
        },
        indent=2,
        ensure_ascii=False,
    )
