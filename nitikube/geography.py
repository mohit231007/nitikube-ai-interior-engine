from __future__ import annotations

from dataclasses import dataclass

import requests


@dataclass(frozen=True)
class GeoLocation:
    name: str
    country: str | None
    admin1: str | None
    latitude: float
    longitude: float
    elevation_m: float | None
    timezone: str | None

    @property
    def label(self) -> str:
        parts = [self.name, self.admin1, self.country]
        return ", ".join(str(x) for x in parts if x)


def geocode_location(name: str, *, count: int = 5, timeout_s: int = 8) -> list[GeoLocation]:
    """Optional no-key geocoding adapter for the MVP.

    External providers are replaceable and must not be treated as permanent
    zero-cost infrastructure.
    """
    if not name.strip():
        raise ValueError("location name is required")
    params = {"name": name.strip(), "count": min(max(count, 1), 10), "language": "en", "format": "json"}
    response = requests.get("https://geocoding-api.open-meteo.com/v1/search", params=params, timeout=timeout_s)
    response.raise_for_status()
    payload = response.json()
    results = []
    for item in payload.get("results", []):
        results.append(
            GeoLocation(
                name=item.get("name", name),
                country=item.get("country"),
                admin1=item.get("admin1"),
                latitude=float(item["latitude"]),
                longitude=float(item["longitude"]),
                elevation_m=item.get("elevation"),
                timezone=item.get("timezone"),
            )
        )
    return results
