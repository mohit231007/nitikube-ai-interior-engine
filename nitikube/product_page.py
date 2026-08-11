from __future__ import annotations

from dataclasses import dataclass, field
from html.parser import HTMLParser
import json
import re
from typing import Any, Iterable

from .procurement import AvailabilityState


@dataclass(frozen=True)
class ProductPageProposal:
    name: str | None = None
    brand: str | None = None
    model: str | None = None
    sku: str | None = None
    category: str | None = None
    price: float | None = None
    currency: str | None = None
    availability: AvailabilityState = AvailabilityState.UNKNOWN
    offer_url: str | None = None
    additional_properties: dict[str, Any] = field(default_factory=dict)
    source_format: str = "json_ld"
    warnings: tuple[str, ...] = ()


class _JsonLdCollector(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._collecting = False
        self._parts: list[str] = []
        self.blocks: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.casefold() != "script":
            return
        attr_map = {k.casefold(): (v or "") for k, v in attrs}
        script_type = attr_map.get("type", "").casefold().split(";")[0].strip()
        if script_type == "application/ld+json":
            self._collecting = True
            self._parts = []

    def handle_data(self, data: str) -> None:
        if self._collecting:
            self._parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.casefold() == "script" and self._collecting:
            block = "".join(self._parts).strip()
            if block:
                self.blocks.append(block)
            self._collecting = False
            self._parts = []


def extract_jsonld_blocks(html: str | bytes) -> list[Any]:
    if isinstance(html, bytes):
        html = html.decode("utf-8", errors="replace")
    collector = _JsonLdCollector()
    collector.feed(html)
    parsed = []
    for block in collector.blocks:
        try:
            parsed.append(json.loads(block))
        except json.JSONDecodeError:
            # Invalid structured data is ignored but never repaired by guessing.
            continue
    return parsed


def _walk_jsonld(value: Any) -> Iterable[dict[str, Any]]:
    if isinstance(value, dict):
        graph = value.get("@graph")
        if isinstance(graph, list):
            for item in graph:
                yield from _walk_jsonld(item)
        yield value
        for key, child in value.items():
            if key == "@graph":
                continue
            if isinstance(child, (dict, list)):
                yield from _walk_jsonld(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_jsonld(child)


def _types(node: dict[str, Any]) -> set[str]:
    value = node.get("@type")
    if isinstance(value, str):
        return {value.casefold()}
    if isinstance(value, list):
        return {str(item).casefold() for item in value}
    return set()


def _brand_name(value: Any) -> str | None:
    if isinstance(value, str):
        return value.strip() or None
    if isinstance(value, dict):
        name = value.get("name")
        return str(name).strip() if name else None
    return None


def _number(value: Any) -> float | None:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    if isinstance(value, str):
        cleaned = value.strip().replace(",", "")
        match = re.search(r"[-+]?\d+(?:\.\d+)?", cleaned)
        if match:
            try:
                return float(match.group(0))
            except ValueError:
                return None
    return None


def _availability(value: Any) -> AvailabilityState:
    text = str(value or "").casefold()
    if text.endswith("instock") or "in_stock" in text:
        return AvailabilityState.IN_STOCK
    if text.endswith("outofstock") or "out_of_stock" in text:
        return AvailabilityState.OUT_OF_STOCK
    if text.endswith("preorder") or "preorder" in text:
        return AvailabilityState.PREORDER
    return AvailabilityState.UNKNOWN


def _additional_properties(product: dict[str, Any]) -> dict[str, Any]:
    values = product.get("additionalProperty") or product.get("additionalProperties") or []
    if isinstance(values, dict):
        values = [values]
    result: dict[str, Any] = {}
    if isinstance(values, list):
        for item in values:
            if not isinstance(item, dict):
                continue
            name = item.get("name") or item.get("propertyID")
            value = item.get("value")
            unit = item.get("unitText") or item.get("unitCode")
            if not name:
                continue
            key = str(name).strip()
            result[key] = {"value": value, "unit": unit} if unit else value
    return result


def _offer_nodes(product: dict[str, Any]) -> list[dict[str, Any]]:
    offers = product.get("offers")
    if isinstance(offers, dict):
        return [offers]
    if isinstance(offers, list):
        return [item for item in offers if isinstance(item, dict)]
    return []


def product_proposals_from_jsonld(data: Any) -> list[ProductPageProposal]:
    products = [node for node in _walk_jsonld(data) if "product" in _types(node)]
    proposals: list[ProductPageProposal] = []
    for product in products:
        offer_nodes = _offer_nodes(product)
        # Keep distinct offers instead of collapsing seller/price variants.
        if not offer_nodes:
            offer_nodes = [{}]
        for offer in offer_nodes:
            price = _number(offer.get("price"))
            if price is None and isinstance(offer.get("priceSpecification"), dict):
                price = _number(offer["priceSpecification"].get("price"))
            currency = offer.get("priceCurrency")
            if currency is None and isinstance(offer.get("priceSpecification"), dict):
                currency = offer["priceSpecification"].get("priceCurrency")
            warnings = []
            if price is None:
                warnings.append("no structured price found")
            if not offer.get("availability"):
                warnings.append("no structured availability found")
            proposals.append(
                ProductPageProposal(
                    name=str(product.get("name")).strip() if product.get("name") else None,
                    brand=_brand_name(product.get("brand")),
                    model=str(product.get("model") or product.get("mpn") or "").strip() or None,
                    sku=str(product.get("sku") or "").strip() or None,
                    category=str(product.get("category") or "").strip() or None,
                    price=price,
                    currency=str(currency).strip() if currency else None,
                    availability=_availability(offer.get("availability")),
                    offer_url=str(offer.get("url") or product.get("url") or "").strip() or None,
                    additional_properties=_additional_properties(product),
                    warnings=tuple(warnings),
                )
            )
    return proposals


def parse_product_html(html: str | bytes) -> list[ProductPageProposal]:
    blocks = extract_jsonld_blocks(html)
    proposals: list[ProductPageProposal] = []
    for block in blocks:
        proposals.extend(product_proposals_from_jsonld(block))
    return proposals


def proposal_rows(proposals: Iterable[ProductPageProposal]) -> list[dict[str, Any]]:
    rows = []
    for index, proposal in enumerate(proposals, start=1):
        rows.append(
            {
                "proposal": index,
                "name": proposal.name,
                "brand": proposal.brand,
                "model": proposal.model,
                "sku": proposal.sku,
                "category": proposal.category,
                "price": proposal.price,
                "currency": proposal.currency,
                "availability": proposal.availability.value,
                "offer_url": proposal.offer_url,
                "additional_properties": json.dumps(proposal.additional_properties, ensure_ascii=False),
                "warnings": "; ".join(proposal.warnings),
            }
        )
    return rows
