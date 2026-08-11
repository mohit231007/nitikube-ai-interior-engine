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
    verified_geometry: dict[str, Any] | None = None

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(asdict(self), indent=indent, ensure_ascii=False)

    def attach_verified_geometry(self, geometry_payload: str | dict[str, Any]) -> None:
        """Attach an authoritative NitiKube verified-geometry document.

        This keeps project persistence backward-compatible while making the
        verified geometry graph available to future whole-home engines. The
        schema check prevents arbitrary JSON from silently being treated as
        authoritative geometry.
        """
        data = json.loads(geometry_payload) if isinstance(geometry_payload, str) else dict(geometry_payload)
        if data.get("schema") != "nitikube.verified_geometry":
            raise ValueError("unsupported verified geometry schema")
        self.verified_geometry = data

    @classmethod
    def from_json(cls, payload: str) -> "ProjectSnapshot":
        data = json.loads(payload)
        rooms = [RoomInput(**room) for room in data.pop("rooms", [])]
        return cls(rooms=rooms, **data)
