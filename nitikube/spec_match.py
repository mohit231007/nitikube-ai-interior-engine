from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class ProductSpecification:
    name: str
    category: str
    watts: float | None = None
    lumens: float | None = None
    kelvin: int | None = None
    beam_angle_deg: float | None = None
    cri: float | None = None
    price: float | None = None
    source_url: str | None = None
    verified_at: str | None = None

    @property
    def price_verified(self) -> bool:
        return self.price is not None and bool(self.source_url) and bool(self.verified_at)


@dataclass(frozen=True)
class ProductRequirement:
    category: str
    watts_min: float | None = None
    watts_max: float | None = None
    lumens_min: float | None = None
    lumens_max: float | None = None
    kelvin_allowed: tuple[int, ...] = ()
    beam_angle_target_deg: float | None = None
    beam_angle_tolerance_deg: float = 5.0
    cri_min: float | None = None
    max_price: float | None = None


@dataclass(frozen=True)
class SpecificationMatch:
    product_name: str
    feasible: bool
    score: float
    matched: tuple[str, ...]
    failed: tuple[str, ...]
    unknown: tuple[str, ...]


def _in_range(value: float | None, minimum: float | None, maximum: float | None) -> bool | None:
    if value is None:
        return None
    if minimum is not None and value < minimum:
        return False
    if maximum is not None and value > maximum:
        return False
    return True


def match_product(product: ProductSpecification, req: ProductRequirement) -> SpecificationMatch:
    matched: list[str] = []
    failed: list[str] = []
    unknown: list[str] = []
    checks: list[tuple[str, bool | None]] = []

    checks.append(("category", product.category.casefold() == req.category.casefold()))
    if req.watts_min is not None or req.watts_max is not None:
        checks.append(("watts", _in_range(product.watts, req.watts_min, req.watts_max)))
    if req.lumens_min is not None or req.lumens_max is not None:
        checks.append(("lumens", _in_range(product.lumens, req.lumens_min, req.lumens_max)))
    if req.kelvin_allowed:
        checks.append(("kelvin", None if product.kelvin is None else product.kelvin in req.kelvin_allowed))
    if req.beam_angle_target_deg is not None:
        checks.append((
            "beam_angle",
            None if product.beam_angle_deg is None else abs(product.beam_angle_deg - req.beam_angle_target_deg) <= req.beam_angle_tolerance_deg,
        ))
    if req.cri_min is not None:
        checks.append(("cri", None if product.cri is None else product.cri >= req.cri_min))
    if req.max_price is not None:
        checks.append(("price", None if product.price is None else product.price <= req.max_price))

    for name, state in checks:
        if state is True:
            matched.append(name)
        elif state is False:
            failed.append(name)
        else:
            unknown.append(name)

    # A required-but-unknown specification is not proof of feasibility.
    feasible = not failed and not unknown
    score = 100.0 * len(matched) / len(checks) if checks else 0.0

    return SpecificationMatch(
        product_name=product.name,
        feasible=feasible,
        score=round(score, 2),
        matched=tuple(matched),
        failed=tuple(failed),
        unknown=tuple(unknown),
    )


def rank_products(products: Iterable[ProductSpecification], req: ProductRequirement) -> list[tuple[ProductSpecification, SpecificationMatch]]:
    evaluated = [(product, match_product(product, req)) for product in products]
    return sorted(
        evaluated,
        key=lambda pair: (pair[1].feasible, pair[1].score, pair[0].price_verified),
        reverse=True,
    )
