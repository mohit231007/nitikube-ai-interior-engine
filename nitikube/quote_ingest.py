from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from typing import Any

import pandas as pd


@dataclass(frozen=True)
class QuoteLine:
    row_number: int
    description: str
    quantity: float
    unit: str
    unit_rate: float | None
    quoted_amount: float | None

    @property
    def calculated_amount(self) -> float | None:
        if self.unit_rate is None:
            return None
        return self.quantity * self.unit_rate


@dataclass(frozen=True)
class QuoteArithmeticAudit:
    row_number: int
    description: str
    quoted_amount: float | None
    calculated_amount: float | None
    difference: float | None
    difference_pct: float | None
    status: str


def read_quote_table(file_bytes: bytes, filename: str) -> pd.DataFrame:
    """Read structured quotation data from CSV or XLSX/XLS.

    This deliberately avoids guessing the semantic column mapping; the UI asks
    the user to map description/quantity/unit/rate/amount after the table is
    loaded. Scanned-image/PDF extraction belongs to a separate CV/OCR stage.
    """
    lower = filename.lower()
    if lower.endswith(".csv"):
        return pd.read_csv(BytesIO(file_bytes))
    if lower.endswith((".xlsx", ".xlsm")):
        return pd.read_excel(BytesIO(file_bytes), engine="openpyxl")
    if lower.endswith(".xls"):
        raise ValueError("Legacy .xls is not supported in the zero-cost MVP; save/export as .xlsx or .csv")
    raise ValueError("Supported structured quotation formats: .csv, .xlsx, .xlsm")


def _optional_number(value: Any) -> float | None:
    if value is None or pd.isna(value) or str(value).strip() == "":
        return None
    return float(value)


def map_quote_lines(
    table: pd.DataFrame,
    *,
    description_col: str,
    quantity_col: str,
    unit_col: str | None = None,
    unit_rate_col: str | None = None,
    amount_col: str | None = None,
) -> list[QuoteLine]:
    required = [description_col, quantity_col]
    missing = [col for col in required if col not in table.columns]
    if missing:
        raise ValueError(f"missing mapped columns: {', '.join(missing)}")
    for optional in [unit_col, unit_rate_col, amount_col]:
        if optional is not None and optional not in table.columns:
            raise ValueError(f"mapped column not present: {optional}")

    lines: list[QuoteLine] = []
    for idx, row in table.iterrows():
        description = str(row[description_col]).strip()
        if not description or description.casefold() == "nan":
            continue
        quantity = _optional_number(row[quantity_col])
        if quantity is None or quantity < 0:
            raise ValueError(f"row {idx + 2}: quantity is missing or negative")
        unit = "" if unit_col is None or pd.isna(row[unit_col]) else str(row[unit_col]).strip()
        rate = None if unit_rate_col is None else _optional_number(row[unit_rate_col])
        amount = None if amount_col is None else _optional_number(row[amount_col])
        if rate is not None and rate < 0:
            raise ValueError(f"row {idx + 2}: unit rate cannot be negative")
        if amount is not None and amount < 0:
            raise ValueError(f"row {idx + 2}: amount cannot be negative")
        lines.append(QuoteLine(idx + 2, description, quantity, unit, rate, amount))
    return lines


def audit_quote_arithmetic(lines: list[QuoteLine], tolerance_pct: float = 0.5, absolute_tolerance: float = 1.0) -> list[QuoteArithmeticAudit]:
    if tolerance_pct < 0 or absolute_tolerance < 0:
        raise ValueError("tolerances cannot be negative")
    audits: list[QuoteArithmeticAudit] = []
    for line in lines:
        calculated = line.calculated_amount
        quoted = line.quoted_amount
        if calculated is None or quoted is None:
            audits.append(QuoteArithmeticAudit(line.row_number, line.description, quoted, calculated, None, None, "insufficient_data"))
            continue
        diff = quoted - calculated
        denom = max(abs(calculated), 1e-12)
        pct = diff / denom * 100.0
        within = abs(diff) <= absolute_tolerance or abs(pct) <= tolerance_pct
        status = "matches" if within else "arithmetic_mismatch"
        audits.append(QuoteArithmeticAudit(line.row_number, line.description, quoted, calculated, diff, pct, status))
    return audits


def quote_total(lines: list[QuoteLine], prefer_quoted_amount: bool = True) -> float:
    total = 0.0
    for line in lines:
        amount = line.quoted_amount if prefer_quoted_amount and line.quoted_amount is not None else line.calculated_amount
        if amount is not None:
            total += amount
    return total
