from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
import json
import math
import re
from typing import Any, Iterable, Sequence

from .spec_match import ProductRequirement, ProductSpecification, SpecificationMatch, match_product


class AvailabilityState(str, Enum):
    IN_STOCK = "in_stock"
    OUT_OF_STOCK = "out_of_stock"
    PREORDER = "preorder"
    UNKNOWN = "unknown"


class FreshnessState(str, Enum):
    FRESH = "fresh"
    STALE = "stale"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class ProductOffer:
    offer_id: str
    product: ProductSpecification
    retailer: str
    product_url: str
    brand: str | None = None
    model: str | None = None
    sku: str | None = None
    currency: str = "INR"
    availability: AvailabilityState = AvailabilityState.UNKNOWN
    warranty_months: float | None = None
    delivery_location: str | None = None
    checked_at: str | None = None
    price_source_url: str | None = None
    source_kind: str = "structured_input"
    notes: tuple[str, ...] = ()

    @property
    def price(self) -> float | None:
        return self.product.price

    @property
    def price_verified(self) -> bool:
        return (
            self.product.price is not None
            and bool(self.price_source_url or self.product.source_url)
            and bool(self.checked_at or self.product.verified_at)
        )


@dataclass(frozen=True)
class ProcurementRequirement:
    product_requirement: ProductRequirement
    currency: str = "INR"
    require_verified_price: bool = True
    max_price_age_hours: float | None = 168.0
    require_in_stock: bool = False
    min_warranty_months: float | None = None
    delivery_location: str | None = None
    require_delivery_location_match: bool = False


@dataclass(frozen=True)
class ProcurementEvaluation:
    offer_id: str
    product_name: str
    feasible: bool
    specification: SpecificationMatch
    freshness: FreshnessState
    price_age_hours: float | None
    checks_passed: tuple[str, ...]
    checks_failed: tuple[str, ...]
    checks_unknown: tuple[str, ...]
    rank_score: float


@dataclass(frozen=True)
class ProductGroup:
    identity_key: str
    offers: tuple[ProductOffer, ...]


def _parse_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    if dt.tzinfo is None:
        return None
    return dt.astimezone(timezone.utc)


def price_age_hours(offer: ProductOffer, *, now: datetime | None = None) -> float | None:
    checked = _parse_timestamp(offer.checked_at or offer.product.verified_at)
    if checked is None:
        return None
    now_utc = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    age = (now_utc - checked).total_seconds() / 3600.0
    # Future timestamps are invalid evidence rather than negative-age "fresh" prices.
    if age < -1e-6:
        return None
    return max(0.0, age)


def price_freshness(
    offer: ProductOffer,
    max_age_hours: float | None,
    *,
    now: datetime | None = None,
) -> tuple[FreshnessState, float | None]:
    if max_age_hours is None:
        return FreshnessState.UNKNOWN, price_age_hours(offer, now=now)
    if max_age_hours < 0:
        raise ValueError("max_age_hours cannot be negative")
    age = price_age_hours(offer, now=now)
    if age is None or not offer.price_verified:
        return FreshnessState.UNKNOWN, age
    return (FreshnessState.FRESH if age <= max_age_hours else FreshnessState.STALE), age


def normalize_identity_token(value: str | None) -> str:
    if not value:
        return ""
    return re.sub(r"[^a-z0-9]+", "", value.casefold())


def product_identity_key(offer: ProductOffer) -> str:
    """Return a conservative deduplication key.

    We merge variants only when there is a strong explicit identifier. Missing
    model/SKU data does not trigger fuzzy title-based merging because that could
    incorrectly combine different wattages, sizes, colours or pack variants.
    """
    brand = normalize_identity_token(offer.brand)
    model = normalize_identity_token(offer.model)
    sku = normalize_identity_token(offer.sku)
    if model:
        return f"brand-model:{brand}:{model}"
    if sku:
        return f"brand-sku:{brand}:{sku}"
    return f"offer:{offer.offer_id}"


def group_product_offers(offers: Iterable[ProductOffer]) -> list[ProductGroup]:
    grouped: dict[str, list[ProductOffer]] = {}
    order: list[str] = []
    for offer in offers:
        key = product_identity_key(offer)
        if key not in grouped:
            grouped[key] = []
            order.append(key)
        grouped[key].append(offer)
    return [ProductGroup(key, tuple(grouped[key])) for key in order]


def _location_matches(actual: str | None, requested: str | None) -> bool | None:
    if requested is None:
        return True
    if not actual:
        return None
    requested_tokens = {token for token in re.split(r"[^a-z0-9]+", requested.casefold()) if token}
    actual_tokens = {token for token in re.split(r"[^a-z0-9]+", actual.casefold()) if token}
    if not requested_tokens:
        return True
    return requested_tokens.issubset(actual_tokens) or actual_tokens.issubset(requested_tokens)


def evaluate_offer(
    offer: ProductOffer,
    requirement: ProcurementRequirement,
    *,
    now: datetime | None = None,
) -> ProcurementEvaluation:
    spec = match_product(offer.product, requirement.product_requirement)
    passed: list[str] = []
    failed: list[str] = []
    unknown: list[str] = []

    if spec.feasible:
        passed.append("specification")
    elif spec.failed:
        failed.append("specification")
    else:
        unknown.append("specification")

    if offer.currency.casefold() == requirement.currency.casefold():
        passed.append("currency")
    else:
        failed.append("currency")

    freshness, age = price_freshness(offer, requirement.max_price_age_hours, now=now)
    if requirement.require_verified_price:
        if not offer.price_verified:
            unknown.append("verified_price")
        else:
            passed.append("verified_price")
        if requirement.max_price_age_hours is not None:
            if freshness == FreshnessState.FRESH:
                passed.append("price_freshness")
            elif freshness == FreshnessState.STALE:
                failed.append("price_freshness")
            else:
                unknown.append("price_freshness")

    if requirement.require_in_stock:
        if offer.availability == AvailabilityState.IN_STOCK:
            passed.append("availability")
        elif offer.availability in {AvailabilityState.OUT_OF_STOCK, AvailabilityState.PREORDER}:
            failed.append("availability")
        else:
            unknown.append("availability")

    if requirement.min_warranty_months is not None:
        if offer.warranty_months is None:
            unknown.append("warranty")
        elif offer.warranty_months >= requirement.min_warranty_months:
            passed.append("warranty")
        else:
            failed.append("warranty")

    if requirement.delivery_location is not None:
        state = _location_matches(offer.delivery_location, requirement.delivery_location)
        if state is True:
            passed.append("delivery_location")
        elif state is False:
            failed.append("delivery_location")
        elif requirement.require_delivery_location_match:
            unknown.append("delivery_location")

    feasible = not failed and not unknown

    # Ranking is transparent and never turns unknowns into matches. Specification
    # match contributes most; evidence freshness/availability/warranty are small
    # tie-breakers. A non-feasible offer can rank for investigation but never as
    # an approved procurement choice.
    evidence_checks = len(passed) + len(failed) + len(unknown)
    evidence_fraction = len(passed) / evidence_checks if evidence_checks else 0.0
    score = 0.75 * spec.score + 25.0 * evidence_fraction
    if feasible:
        score += 5.0
    return ProcurementEvaluation(
        offer_id=offer.offer_id,
        product_name=offer.product.name,
        feasible=feasible,
        specification=spec,
        freshness=freshness,
        price_age_hours=age,
        checks_passed=tuple(passed),
        checks_failed=tuple(failed),
        checks_unknown=tuple(unknown),
        rank_score=round(score, 2),
    )


def rank_offers(
    offers: Iterable[ProductOffer],
    requirement: ProcurementRequirement,
    *,
    now: datetime | None = None,
) -> list[tuple[ProductOffer, ProcurementEvaluation]]:
    evaluated = [(offer, evaluate_offer(offer, requirement, now=now)) for offer in offers]
    return sorted(
        evaluated,
        key=lambda pair: (
            pair[1].feasible,
            pair[1].rank_score,
            pair[0].price_verified,
            pair[0].availability == AvailabilityState.IN_STOCK,
            -(pair[0].price if pair[0].price is not None else math.inf),
        ),
        reverse=True,
    )


def best_offer_per_product(
    offers: Iterable[ProductOffer],
    requirement: ProcurementRequirement,
    *,
    now: datetime | None = None,
) -> list[tuple[ProductGroup, ProductOffer, ProcurementEvaluation]]:
    result = []
    for group in group_product_offers(offers):
        ranked = rank_offers(group.offers, requirement, now=now)
        if ranked:
            best_offer, evaluation = ranked[0]
            result.append((group, best_offer, evaluation))
    return sorted(result, key=lambda item: (item[2].feasible, item[2].rank_score), reverse=True)


def _float_or_none(value: Any) -> float | None:
    if value is None or value == "":
        return None
    result = float(value)
    if not math.isfinite(result):
        raise ValueError("numeric product values must be finite")
    return result


def _int_or_none(value: Any) -> int | None:
    number = _float_or_none(value)
    return int(number) if number is not None else None


def offer_from_dict(data: dict[str, Any]) -> ProductOffer:
    required = ["offer_id", "name", "category", "retailer", "product_url"]
    missing = [field for field in required if not str(data.get(field, "")).strip()]
    if missing:
        raise ValueError(f"missing required offer fields: {missing}")
    availability = AvailabilityState(str(data.get("availability") or "unknown").casefold())
    checked_at = data.get("checked_at") or data.get("verified_at")
    source_url = data.get("source_url") or data.get("price_source_url") or data.get("product_url")
    product = ProductSpecification(
        name=str(data["name"]),
        category=str(data["category"]),
        watts=_float_or_none(data.get("watts")),
        lumens=_float_or_none(data.get("lumens")),
        kelvin=_int_or_none(data.get("kelvin")),
        beam_angle_deg=_float_or_none(data.get("beam_angle_deg")),
        cri=_float_or_none(data.get("cri")),
        price=_float_or_none(data.get("price")),
        source_url=source_url,
        verified_at=checked_at,
    )
    return ProductOffer(
        offer_id=str(data["offer_id"]),
        product=product,
        retailer=str(data["retailer"]),
        product_url=str(data["product_url"]),
        brand=str(data["brand"]) if data.get("brand") not in {None, ""} else None,
        model=str(data["model"]) if data.get("model") not in {None, ""} else None,
        sku=str(data["sku"]) if data.get("sku") not in {None, ""} else None,
        currency=str(data.get("currency") or "INR"),
        availability=availability,
        warranty_months=_float_or_none(data.get("warranty_months")),
        delivery_location=str(data["delivery_location"]) if data.get("delivery_location") not in {None, ""} else None,
        checked_at=checked_at,
        price_source_url=source_url,
        source_kind=str(data.get("source_kind") or "structured_input"),
        notes=tuple(data.get("notes", [])) if isinstance(data.get("notes", []), list) else (str(data.get("notes")),),
    )


def load_offers_json(payload: str | bytes) -> list[ProductOffer]:
    if isinstance(payload, bytes):
        payload = payload.decode("utf-8")
    data = json.loads(payload)
    rows = data.get("offers") if isinstance(data, dict) else data
    if not isinstance(rows, list):
        raise ValueError("product offer JSON must be a list or {'offers': [...]} object")
    offers = [offer_from_dict(row) for row in rows]
    ids = [offer.offer_id for offer in offers]
    if len(ids) != len(set(ids)):
        raise ValueError("offer_id values must be unique")
    return offers


def procurement_rows(
    ranked: Sequence[tuple[ProductOffer, ProcurementEvaluation]],
) -> list[dict[str, Any]]:
    rows = []
    for offer, evaluation in ranked:
        rows.append(
            {
                "offer_id": offer.offer_id,
                "product": offer.product.name,
                "brand": offer.brand,
                "model": offer.model,
                "retailer": offer.retailer,
                "price": offer.price,
                "currency": offer.currency,
                "price_verified": offer.price_verified,
                "price_age_hours": round(evaluation.price_age_hours, 2) if evaluation.price_age_hours is not None else None,
                "freshness": evaluation.freshness.value,
                "availability": offer.availability.value,
                "warranty_months": offer.warranty_months,
                "delivery_location": offer.delivery_location,
                "spec_score": evaluation.specification.score,
                "feasible": evaluation.feasible,
                "rank_score": evaluation.rank_score,
                "matched_specs": ", ".join(evaluation.specification.matched),
                "failed_specs": ", ".join(evaluation.specification.failed),
                "unknown_specs": ", ".join(evaluation.specification.unknown),
                "checks_failed": ", ".join(evaluation.checks_failed),
                "checks_unknown": ", ".join(evaluation.checks_unknown),
                "product_url": offer.product_url,
            }
        )
    return rows
