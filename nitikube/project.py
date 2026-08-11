from __future__ import annotations

from dataclasses import asdict, dataclass, field
import json
from typing import Any


@dataclass
class RoomInput:
    name: str
    length_ft: float
    width_ft: float
    ceiling_height_ft: float


@dataclass
class ProjectSnapshot:
    project_name: str
    location: str | None = None
    budget_inr: float | None = None
    rooms: list[RoomInput] = field(default_factory=list)
    preferences: dict[str, Any] = field(default_factory=dict)
    verified_inputs: dict[str, bool] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(asdict(self), indent=indent, ensure_ascii=False)

    @classmethod
    def from_json(cls, payload: str) -> "ProjectSnapshot":
        data = json.loads(payload)
        rooms = [RoomInput(**room) for room in data.pop("rooms", [])]
        return cls(rooms=rooms, **data)
