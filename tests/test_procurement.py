from datetime import datetime, timezone
import json

import pytest

from nitikube.procurement import (
    AvailabilityState,
    FreshnessState,
    ProcurementRequirement,
    ProductOffer,
    best_offer_per_product,
    evaluate_offer,
    group_product_offers,
    load_offers_json,
    price_freshness,
    product_identity_key,
    rank_offers,
)
from nitikube.product_page import extract_jsonld_blocks, parse_product_html, product_proposals_from_jsonld
from nitikube.spec_match import ProductRequirement, ProductSpecification


def _product(name="COB", price=500.0, source_url="https://shop.example/p", verified_at="2026-08-11T10:00:00+00:00"):
    return ProductSpecification(
        name=name,
        category="COB downlight",
        watts=7.0,
        lumens=500.0,
        kelvin=3000,
        beam_angle_deg=36.0,
        cri=90.0,
        price=price,
        source_url=source_url,
        verified_at=verified_at,
    )


def _offer(**overrides):
    values = {
        "offer_id": "A",
        "product": _product(),
        "retailer": "Retailer",
        "product_url": "https://shop.example/p",
        "brand": "Brand",
        "model": "MODEL-1",
        "currency": "INR",
        "availability": AvailabilityState.IN_STOCK,
        "warranty_months": 24.0,
        "delivery_location": "Gurugram, Haryana",
        "checked_at": "2026-08-11T10:00:00+00:00",
        "price_source_url": "https://shop.example/p",
    }
    values.update(overrides)
    return ProductOffer(**values)


def _requirement(**overrides):
    product_req = ProductRequirement(
        category="COB downlight",
        lumens_min=450.0,
        lumens_max=550.0,
        kelvin_allowed=(3000,),
        beam_angle_target_deg=36.0,
        beam_angle_tolerance_deg=2.0,
        cri_min=90.0,
        max_price=600.0,
    )
    values = {
        "product_requirement": product_req,
        "currency": "INR",
        "require_verified_price": True,
        "max_price_age_hours": 48.0,
        "require_in_stock": True,
        "min_warranty_months": 12.0,
        "delivery_location": "Gurugram",
        "require_delivery_location_match": True,
    }
    values.update(overrides)
    return ProcurementRequirement(**values)


def test_price_freshness_requires_timestamp_and_source():
    now = datetime(2026, 8, 11, 20, 0, tzinfo=timezone.utc)
    state, age = price_freshness(_offer(), 48.0, now=now)
    assert state == FreshnessState.FRESH
    assert age == pytest.approx(10.0)

    no_timestamp = _offer(
        checked_at=None,
        product=_product(verified_at=None),
    )
    state, age = price_freshness(no_timestamp, 48.0, now=now)
    assert state == FreshnessState.UNKNOWN
    assert age is None

    stale = _offer(
        checked_at="2026-08-01T10:00:00+00:00",
        product=_product(verified_at="2026-08-01T10:00:00+00:00"),
    )
    state, age = price_freshness(stale, 48.0, now=now)
    assert state == FreshnessState.STALE
    assert age > 48


def test_future_price_timestamp_is_not_accepted_as_fresh():
    now = datetime(2026, 8, 11, 20, 0, tzinfo=timezone.utc)
    future = _offer(
        checked_at="2026-08-12T10:00:00+00:00",
        product=_product(verified_at="2026-08-12T10:00:00+00:00"),
    )
    state, age = price_freshness(future, 48.0, now=now)
    assert state == FreshnessState.UNKNOWN
    assert age is None


def test_fully_evidenced_offer_is_feasible():
    now = datetime(2026, 8, 11, 20, 0, tzinfo=timezone.utc)
    evaluation = evaluate_offer(_offer(), _requirement(), now=now)
    assert evaluation.feasible is True
    assert evaluation.specification.feasible is True
    assert "specification" in evaluation.checks_passed
    assert "verified_price" in evaluation.checks_passed
    assert "availability" in evaluation.checks_passed
    assert evaluation.checks_failed == ()
    assert evaluation.checks_unknown == ()


def test_unknown_required_evidence_does_not_become_feasible():
    now = datetime(2026, 8, 11, 20, 0, tzinfo=timezone.utc)
    offer = _offer(
        availability=AvailabilityState.UNKNOWN,
        warranty_months=None,
        delivery_location=None,
    )
    evaluation = evaluate_offer(offer, _requirement(), now=now)
    assert evaluation.feasible is False
    assert "availability" in evaluation.checks_unknown
    assert "warranty" in evaluation.checks_unknown
    assert "delivery_location" in evaluation.checks_unknown


def test_failed_specification_cannot_be_rescued_by_good_evidence():
    now = datetime(2026, 8, 11, 20, 0, tzinfo=timezone.utc)
    bad_product = ProductSpecification(
        name="Wrong CCT",
        category="COB downlight",
        watts=7.0,
        lumens=500.0,
        kelvin=5700,
        beam_angle_deg=36.0,
        cri=90.0,
        price=400.0,
        source_url="https://shop.example/bad",
        verified_at="2026-08-11T10:00:00+00:00",
    )
    evaluation = evaluate_offer(_offer(product=bad_product), _requirement(), now=now)
    assert evaluation.feasible is False
    assert "kelvin" in evaluation.specification.failed
    assert "specification" in evaluation.checks_failed


def test_deduplication_is_conservative_and_variant_safe():
    a = _offer(offer_id="A", brand="Brand X", model="M-1", retailer="Shop 1")
    b = _offer(offer_id="B", brand="Brand X", model="M-1", retailer="Shop 2")
    c = _offer(offer_id="C", brand="Brand X", model="M-2", retailer="Shop 1")
    d = _offer(offer_id="D", brand=None, model=None, sku=None, retailer="Shop 3")
    e = _offer(offer_id="E", brand=None, model=None, sku=None, retailer="Shop 4")

    assert product_identity_key(a) == product_identity_key(b)
    assert product_identity_key(a) != product_identity_key(c)
    assert product_identity_key(d) != product_identity_key(e)

    groups = group_product_offers([a, b, c, d, e])
    sizes = sorted(len(group.offers) for group in groups)
    assert sizes == [1, 1, 1, 2]


def test_ranking_prefers_feasible_fresh_offer_and_low_price_tie_breaker():
    now = datetime(2026, 8, 11, 20, 0, tzinfo=timezone.utc)
    expensive = _offer(offer_id="A", product=_product(name="Same Product", price=550.0), retailer="Shop 1")
    cheap = _offer(offer_id="B", product=_product(name="Same Product", price=450.0), retailer="Shop 2")
    stale = _offer(
        offer_id="C",
        product=_product(name="Same Product", price=350.0, verified_at="2026-08-01T10:00:00+00:00"),
        checked_at="2026-08-01T10:00:00+00:00",
        retailer="Shop 3",
    )
    ranked = rank_offers([expensive, stale, cheap], _requirement(), now=now)
    assert ranked[0][0].offer_id == "B"
    assert ranked[0][1].feasible is True
    assert ranked[-1][0].offer_id == "C"
    assert ranked[-1][1].freshness == FreshnessState.STALE


def test_best_offer_per_explicit_product_identity():
    now = datetime(2026, 8, 11, 20, 0, tzinfo=timezone.utc)
    expensive = _offer(offer_id="A", product=_product(price=550.0), retailer="Shop 1")
    cheap = _offer(offer_id="B", product=_product(price=450.0), retailer="Shop 2")
    groups = best_offer_per_product([expensive, cheap], _requirement(), now=now)
    assert len(groups) == 1
    assert groups[0][1].offer_id == "B"


def test_structured_offer_json_keeps_unknowns_unknown():
    payload = {
        "offers": [
            {
                "offer_id": "x",
                "name": "Candidate",
                "category": "COB downlight",
                "retailer": "Retailer",
                "product_url": "https://example.com/x",
                "price": None,
                "availability": "unknown",
            }
        ]
    }
    offers = load_offers_json(json.dumps(payload))
    assert len(offers) == 1
    assert offers[0].price is None
    assert offers[0].availability == AvailabilityState.UNKNOWN
    assert offers[0].price_verified is False


def test_jsonld_html_parser_extracts_product_offer_without_network():
    html = """
    <html><head>
      <script type="application/ld+json">
      {
        "@context": "https://schema.org",
        "@type": "Product",
        "name": "Example COB",
        "brand": {"@type": "Brand", "name": "Example Brand"},
        "model": "C36-7",
        "sku": "SKU-7",
        "category": "COB downlight",
        "additionalProperty": [
          {"@type": "PropertyValue", "name": "Beam Angle", "value": 36, "unitText": "degree"}
        ],
        "offers": {
          "@type": "Offer",
          "price": "499.00",
          "priceCurrency": "INR",
          "availability": "https://schema.org/InStock",
          "url": "https://shop.example/cob"
        }
      }
      </script>
    </head></html>
    """
    blocks = extract_jsonld_blocks(html)
    assert len(blocks) == 1
    proposals = parse_product_html(html)
    assert len(proposals) == 1
    p = proposals[0]
    assert p.name == "Example COB"
    assert p.brand == "Example Brand"
    assert p.model == "C36-7"
    assert p.price == pytest.approx(499.0)
    assert p.currency == "INR"
    assert p.availability == AvailabilityState.IN_STOCK
    assert p.additional_properties["Beam Angle"]["value"] == 36


def test_jsonld_keeps_multiple_offers_separate():
    data = {
        "@type": "Product",
        "name": "Product",
        "offers": [
            {"@type": "Offer", "price": 100, "priceCurrency": "INR", "url": "https://a.example"},
            {"@type": "Offer", "price": 120, "priceCurrency": "INR", "url": "https://b.example"},
        ],
    }
    proposals = product_proposals_from_jsonld(data)
    assert [proposal.price for proposal in proposals] == [100.0, 120.0]
    assert [proposal.offer_url for proposal in proposals] == ["https://a.example", "https://b.example"]


def test_invalid_jsonld_is_ignored_not_repaired():
    html = '<script type="application/ld+json">{invalid json</script>'
    assert parse_product_html(html) == []
