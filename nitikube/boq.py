from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Iterable


@dataclass(frozen=True)
class BOQItem:
    category: str
    description: str
    calculated_quantity: float
    unit: str
    unit_rate: float | None = None
    currency: str = "INR"
    source_url: str | None = None
    verified_at: str | None = None

    @property
    def extended_cost(self) -> float | None:
        if self.unit_rate is None:
            return None
        return self.calculated_quantity * self.unit_rate

    @property
    def price_verified(self) -> bool:
        return self.unit_rate is not None and bool(self.source_url) and bool(self.verified_at)


@dataclass(frozen=True)
class QuantityAudit:
    calculated_quantity: float
    quoted_quantity: float
    absolute_difference: float
    percent_difference: float
    status: str


def audit_quantity(calculated_quantity: float, quoted_quantity: float, tolerance_pct: float = 5.0) -> QuantityAudit:
    if calculated_quantity <= 0 or quoted_quantity < 0:
        raise ValueError("calculated quantity must be positive and quoted quantity non-negative")
    if tolerance_pct < 0:
        raise ValueError("tolerance_pct cannot be negative")

    diff = quoted_quantity - calculated_quantity
    pct = diff / calculated_quantity * 100.0
    if abs(pct) <= tolerance_pct:
        status = "within_tolerance"
    elif pct > tolerance_pct:
        status = "quoted_above_calculated"
    else:
        status = "quoted_below_calculated"

    return QuantityAudit(
        calculated_quantity=calculated_quantity,
        quoted_quantity=quoted_quantity,
        absolute_difference=diff,
        percent_difference=pct,
        status=status,
    )


def total_known_cost(items: Iterable[BOQItem]) -> float:
    return sum(item.extended_cost or 0.0 for item in items)


def all_prices_verified(items: Iterable[BOQItem]) -> bool:
    items = list(items)
    return bool(items) and all(item.price_verified for item in items if item.unit_rate is not None)


def boq_rows(items: Iterable[BOQItem]) -> list[dict]:
    rows = []
    for item in items:
        row = asdict(item)
        row["extended_cost"] = item.extended_cost
        row["price_verified"] = item.price_verified
        rows.append(row)
    return rows


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()
