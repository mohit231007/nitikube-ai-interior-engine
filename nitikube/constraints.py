from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class ScopeCategory(str, Enum):
    COSMETIC = "cosmetic"
    FURNITURE = "furniture"
    LIGHTING_LAYOUT = "lighting_layout"
    MATERIAL_SELECTION = "material_selection"
    NON_STRUCTURAL_PARTITION = "non_structural_partition"
    LOAD_BEARING_OR_STRUCTURAL = "load_bearing_or_structural"
    MAJOR_ELECTRICAL_SERVICE = "major_electrical_service"
    GAS_SYSTEM = "gas_system"
    FIRE_CODE_CERTIFICATION = "fire_code_certification"
    STATUTORY_APPROVAL = "statutory_approval"


@dataclass(frozen=True)
class ScopeGuardrail:
    category: ScopeCategory
    professional_verification_required: bool
    message: str


PROFESSIONAL_CATEGORIES = {
    ScopeCategory.LOAD_BEARING_OR_STRUCTURAL,
    ScopeCategory.MAJOR_ELECTRICAL_SERVICE,
    ScopeCategory.GAS_SYSTEM,
    ScopeCategory.FIRE_CODE_CERTIFICATION,
    ScopeCategory.STATUTORY_APPROVAL,
}


def guard_scope(category: ScopeCategory) -> ScopeGuardrail:
    required = category in PROFESSIONAL_CATEGORIES
    if required:
        message = "Qualified professional / statutory verification is required before execution."
    elif category == ScopeCategory.NON_STRUCTURAL_PARTITION:
        message = "Interior planning may proceed, but confirm the partition is genuinely non-structural and check local rules/services before execution."
    else:
        message = "NitiKube can assist with planning/calculation; installation must still follow manufacturer instructions and applicable local requirements."
    return ScopeGuardrail(category, required, message)
