from __future__ import annotations

from dataclasses import dataclass
from math import sqrt, tan, radians


@dataclass(frozen=True)
class FitResult:
    fits: bool
    room_length_ft: float
    room_width_ft: float
    required_length_ft: float
    required_width_ft: float
    length_margin_ft: float
    width_margin_ft: float


def rectangular_fit(
    *,
    room_length_ft: float,
    room_width_ft: float,
    item_length_ft: float,
    item_width_ft: float,
    clearance_length_each_side_ft: float = 0.0,
    clearance_width_each_side_ft: float = 0.0,
    allow_rotation: bool = True,
) -> FitResult:
    """Check whether a rectangular furniture envelope fits a rectangular room.

    The function is pure geometry: it does not claim a particular clearance is
    a code or ergonomic standard. Callers must provide clearances appropriate
    to the use case and source them when presented as standards.
    """
    vals = [room_length_ft, room_width_ft, item_length_ft, item_width_ft]
    if any(v <= 0 for v in vals):
        raise ValueError("room and item dimensions must be positive")
    if clearance_length_each_side_ft < 0 or clearance_width_each_side_ft < 0:
        raise ValueError("clearances cannot be negative")

    req_l = item_length_ft + 2 * clearance_length_each_side_ft
    req_w = item_width_ft + 2 * clearance_width_each_side_ft

    candidates = [(req_l, req_w)]
    if allow_rotation:
        candidates.append((req_w, req_l))

    fitting = [
        (l, w)
        for l, w in candidates
        if l <= room_length_ft and w <= room_width_ft
    ]
    if fitting:
        chosen_l, chosen_w = max(
            fitting,
            key=lambda x: min(room_length_ft - x[0], room_width_ft - x[1]),
        )
        fits = True
    else:
        chosen_l, chosen_w = min(
            candidates,
            key=lambda x: max(x[0] - room_length_ft, x[1] - room_width_ft),
        )
        fits = False

    return FitResult(
        fits=fits,
        room_length_ft=room_length_ft,
        room_width_ft=room_width_ft,
        required_length_ft=chosen_l,
        required_width_ft=chosen_w,
        length_margin_ft=room_length_ft - chosen_l,
        width_margin_ft=room_width_ft - chosen_w,
    )


@dataclass(frozen=True)
class DiningEnvelope:
    table_length_ft: float
    table_width_ft: float
    chair_depth_ft: float
    pullback_clearance_ft: float
    required_length_ft: float
    required_width_ft: float


def dining_envelope(
    *,
    table_length_ft: float,
    table_width_ft: float,
    chair_depth_ft: float,
    pullback_clearance_ft: float,
) -> DiningEnvelope:
    """Bounding rectangle for table + chairs + selected pull-back clearance."""
    if min(table_length_ft, table_width_ft, chair_depth_ft) <= 0:
        raise ValueError("table/chair dimensions must be positive")
    if pullback_clearance_ft < 0:
        raise ValueError("pullback clearance cannot be negative")
    expansion = chair_depth_ft + pullback_clearance_ft
    return DiningEnvelope(
        table_length_ft=table_length_ft,
        table_width_ft=table_width_ft,
        chair_depth_ft=chair_depth_ft,
        pullback_clearance_ft=pullback_clearance_ft,
        required_length_ft=table_length_ft + 2 * expansion,
        required_width_ft=table_width_ft + 2 * expansion,
    )


def screen_dimensions_in(diagonal_in: float, aspect_width: float = 16, aspect_height: float = 9) -> tuple[float, float]:
    if diagonal_in <= 0 or aspect_width <= 0 or aspect_height <= 0:
        raise ValueError("screen inputs must be positive")
    scale = diagonal_in / sqrt(aspect_width**2 + aspect_height**2)
    return aspect_width * scale, aspect_height * scale


def viewing_distance_for_horizontal_fov_ft(
    diagonal_in: float,
    horizontal_fov_deg: float,
    aspect_width: float = 16,
    aspect_height: float = 9,
) -> float:
    """Pure geometry: distance that makes a screen subtend a chosen horizontal FOV.

    d = screen_width / (2 tan(FOV/2)). This function deliberately does not
    label any FOV as a recommended standard; UI/source layers own that claim.
    """
    if not (1 < horizontal_fov_deg < 179):
        raise ValueError("horizontal_fov_deg must be between 1 and 179")
    width_in, _ = screen_dimensions_in(diagonal_in, aspect_width, aspect_height)
    distance_in = width_in / (2 * tan(radians(horizontal_fov_deg / 2)))
    return distance_in / 12.0
