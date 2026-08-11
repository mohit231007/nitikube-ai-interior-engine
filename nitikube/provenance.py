from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class EvidenceState(str, Enum):
    VERIFIED = "verified"
    USER_PROVIDED = "user_provided"
    UNVERIFIED = "unverified"
    SUBJECTIVE = "subjective"


@dataclass(frozen=True)
class EvidenceRecord:
    name: str
    value: Any
    unit: str | None
    state: EvidenceState
    source_url: str | None = None
    checked_at: str | None = None
    note: str | None = None

    @property
    def has_provenance(self) -> bool:
        if self.state in {EvidenceState.USER_PROVIDED, EvidenceState.SUBJECTIVE}:
            return True
        return bool(self.source_url and self.checked_at)


def validate_numeric_evidence(record: EvidenceRecord) -> tuple[bool, str]:
    """Guard against presenting unsourced numeric facts as verified evidence."""
    if not isinstance(record.value, (int, float)):
        return True, "non_numeric"
    if record.state == EvidenceState.VERIFIED and not record.has_provenance:
        return False, "verified numeric evidence requires source_url and checked_at"
    if record.state == EvidenceState.UNVERIFIED:
        return False, "numeric evidence is explicitly unverified"
    return True, "ok"


def now_utc_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()
