from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import quote_plus

import requests


@dataclass(frozen=True)
class ProductResult:
    title: str
    url: str
    description: str | None
    source: str
    live_verified: bool


def retailer_search_links(query: str, country: str = "IN") -> list[ProductResult]:
    """Zero-cost fallback: direct search links, clearly not live price claims."""
    q = quote_plus(query)
    if country.upper() == "IN":
        endpoints = [
            ("Amazon India", f"https://www.amazon.in/s?k={q}"),
            ("Flipkart", f"https://www.flipkart.com/search?q={q}"),
            ("IndiaMART", f"https://dir.indiamart.com/search.mp?ss={q}"),
        ]
    else:
        endpoints = [("Google Shopping search", f"https://www.google.com/search?tbm=shop&q={q}")]
    return [ProductResult(name, url, "Open retailer search; price/stock not yet verified by NitiKube.", name, False) for name, url in endpoints]


def brave_web_search(query: str, api_key: str, count: int = 8, timeout_s: int = 10) -> list[ProductResult]:
    """Optional live search adapter. Caller controls quota and must hard-stop on free-tier exhaustion."""
    if not api_key:
        return []
    headers = {"Accept": "application/json", "X-Subscription-Token": api_key}
    params = {"q": query, "count": min(max(count, 1), 20), "search_lang": "en"}
    response = requests.get("https://api.search.brave.com/res/v1/web/search", headers=headers, params=params, timeout=timeout_s)
    response.raise_for_status()
    results = response.json().get("web", {}).get("results", [])
    return [
        ProductResult(
            title=item.get("title", "Untitled result"),
            url=item.get("url", ""),
            description=item.get("description"),
            source="Brave Search",
            live_verified=True,
        )
        for item in results
        if item.get("url")
    ]


def specification_query(*, category: str, watts: float | None = None, kelvin: int | None = None, beam_angle_deg: float | None = None, cri_min: int | None = None, lumens: str | None = None, location: str | None = None) -> str:
    parts = [category]
    if watts is not None:
        parts.append(f"{watts:g}W")
    if kelvin is not None:
        parts.append(f"{kelvin}K")
    if beam_angle_deg is not None:
        parts.append(f"{beam_angle_deg:g} degree beam")
    if cri_min is not None:
        parts.append(f"CRI {cri_min}+")
    if lumens:
        parts.append(f"{lumens} lumens")
    if location:
        parts.append(location)
    return " ".join(parts)
