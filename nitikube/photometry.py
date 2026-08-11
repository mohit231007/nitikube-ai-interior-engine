from __future__ import annotations

from bisect import bisect_right
from dataclasses import dataclass
import math
import re
from typing import Iterable, Sequence

from .geometry import grid_positions


FT_TO_M = 0.3048


@dataclass(frozen=True)
class IESPhotometry:
    header_lines: tuple[str, ...]
    tilt: str
    number_of_lamps: int
    lumens_per_lamp: float
    candela_multiplier: float
    vertical_angles_deg: tuple[float, ...]
    horizontal_angles_deg: tuple[float, ...]
    candela_values: tuple[tuple[float, ...], ...]
    photometric_type: int
    units_type: int
    luminous_width: float
    luminous_length: float
    luminous_height: float
    ballast_factor: float
    future_use: float
    input_watts: float

    @property
    def rotationally_symmetric(self) -> bool:
        return len(self.horizontal_angles_deg) == 1

    @property
    def supports_full_horizontal_interpolation(self) -> bool:
        if self.rotationally_symmetric:
            return True
        return (
            len(self.horizontal_angles_deg) >= 2
            and abs(self.horizontal_angles_deg[0]) <= 1e-7
            and abs(self.horizontal_angles_deg[-1] - 360.0) <= 1e-7
        )

    @property
    def total_nominal_lamp_lumens(self) -> float | None:
        if self.lumens_per_lamp < 0:
            return None
        return self.number_of_lamps * self.lumens_per_lamp


@dataclass(frozen=True)
class PhotometricFixture:
    fixture_id: str
    x_m: float
    y_m: float
    height_above_plane_m: float
    rotation_deg: float = 0.0
    multiplier: float = 1.0


@dataclass(frozen=True)
class IlluminancePoint:
    x_m: float
    y_m: float
    lux: float


@dataclass(frozen=True)
class IlluminanceSummary:
    minimum_lux: float
    average_lux: float
    maximum_lux: float
    min_to_avg: float
    min_to_max: float
    max_to_avg: float
    target_min_lux: float | None
    target_max_lux: float | None
    target_band_fraction: float | None
    sample_points: int
    maintenance_factor: float


_NUMBER_RE = re.compile(r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[Ee][-+]?\d+)?")


def _numeric_tokens(text: str) -> list[float]:
    return [float(match.group(0)) for match in _NUMBER_RE.finditer(text)]


def _strict_int(value: float, label: str) -> int:
    rounded = int(round(value))
    if abs(value - rounded) > 1e-8:
        raise ValueError(f"{label} must be an integer in an IES file")
    return rounded


def _strictly_nondecreasing(values: Sequence[float]) -> bool:
    return all(b >= a for a, b in zip(values, values[1:]))


def parse_ies(payload: str | bytes) -> IESPhotometry:
    """Parse the core photometric block of a common IES LM-63 file.

    Current verified calculation scope intentionally supports `TILT=NONE` and
    Type-C photometry. Type A/B and included/external tilt data are rejected
    rather than silently interpreted with the wrong geometry.
    """
    if isinstance(payload, bytes):
        payload = payload.decode("utf-8", errors="replace")
    lines = payload.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    tilt_index = None
    tilt_value = None
    for index, raw_line in enumerate(lines):
        line = raw_line.strip()
        if line.upper().startswith("TILT="):
            tilt_index = index
            tilt_value = line.split("=", 1)[1].strip()
            break
    if tilt_index is None or tilt_value is None:
        raise ValueError("IES file does not contain a TILT= line")
    if tilt_value.upper() != "NONE":
        raise NotImplementedError("Current NitiKube photometry supports only TILT=NONE IES files")

    header = tuple(line.rstrip() for line in lines[:tilt_index] if line.strip())
    numbers = _numeric_tokens("\n".join(lines[tilt_index + 1 :]))
    if len(numbers) < 13:
        raise ValueError("IES photometric numeric block is incomplete")

    cursor = 0
    number_of_lamps = _strict_int(numbers[cursor], "number_of_lamps"); cursor += 1
    lumens_per_lamp = numbers[cursor]; cursor += 1
    candela_multiplier = numbers[cursor]; cursor += 1
    num_vertical = _strict_int(numbers[cursor], "num_vertical_angles"); cursor += 1
    num_horizontal = _strict_int(numbers[cursor], "num_horizontal_angles"); cursor += 1
    photometric_type = _strict_int(numbers[cursor], "photometric_type"); cursor += 1
    units_type = _strict_int(numbers[cursor], "units_type"); cursor += 1
    luminous_width = numbers[cursor]; cursor += 1
    luminous_length = numbers[cursor]; cursor += 1
    luminous_height = numbers[cursor]; cursor += 1
    ballast_factor = numbers[cursor]; cursor += 1
    future_use = numbers[cursor]; cursor += 1
    input_watts = numbers[cursor]; cursor += 1

    if number_of_lamps < 1:
        raise ValueError("IES number_of_lamps must be >= 1")
    if candela_multiplier <= 0:
        raise ValueError("IES candela multiplier must be positive")
    if num_vertical < 2 or num_horizontal < 1:
        raise ValueError("IES file requires at least 2 vertical and 1 horizontal angle")
    if photometric_type != 1:
        raise NotImplementedError("Current NitiKube point-by-point engine supports IES Type C only")
    if units_type not in {1, 2}:
        raise ValueError("IES units type must be 1 (feet) or 2 (metres)")

    expected = cursor + num_vertical + num_horizontal + num_vertical * num_horizontal
    if len(numbers) < expected:
        raise ValueError(
            f"IES photometric block is truncated: expected at least {expected} numeric values, got {len(numbers)}"
        )

    vertical_angles = tuple(numbers[cursor : cursor + num_vertical]); cursor += num_vertical
    horizontal_angles = tuple(numbers[cursor : cursor + num_horizontal]); cursor += num_horizontal
    if not _strictly_nondecreasing(vertical_angles):
        raise ValueError("IES vertical angles must be nondecreasing")
    if not _strictly_nondecreasing(horizontal_angles):
        raise ValueError("IES horizontal angles must be nondecreasing")
    if vertical_angles[0] < -1e-7 or vertical_angles[-1] > 180.0 + 1e-7:
        raise ValueError("IES vertical angles must lie in [0,180]")
    if horizontal_angles[0] < -1e-7 or horizontal_angles[-1] > 360.0 + 1e-7:
        raise ValueError("IES horizontal angles must lie in [0,360]")

    rows: list[tuple[float, ...]] = []
    for _ in range(num_horizontal):
        row = tuple(value * candela_multiplier for value in numbers[cursor : cursor + num_vertical])
        cursor += num_vertical
        if any(value < 0 or not math.isfinite(value) for value in row):
            raise ValueError("IES candela values must be finite and non-negative")
        rows.append(row)

    photometry = IESPhotometry(
        header_lines=header,
        tilt=tilt_value,
        number_of_lamps=number_of_lamps,
        lumens_per_lamp=lumens_per_lamp,
        candela_multiplier=candela_multiplier,
        vertical_angles_deg=vertical_angles,
        horizontal_angles_deg=horizontal_angles,
        candela_values=tuple(rows),
        photometric_type=photometric_type,
        units_type=units_type,
        luminous_width=luminous_width,
        luminous_length=luminous_length,
        luminous_height=luminous_height,
        ballast_factor=ballast_factor,
        future_use=future_use,
        input_watts=input_watts,
    )
    if not photometry.supports_full_horizontal_interpolation:
        raise NotImplementedError(
            "Current NitiKube engine supports rotationally symmetric Type-C IES files or files with explicit 0°..360° horizontal planes; partial symmetry planes require a dedicated LM-63 symmetry interpreter"
        )
    return photometry


def _linear_interpolate(xs: Sequence[float], ys: Sequence[float], x: float) -> float:
    if len(xs) != len(ys) or not xs:
        raise ValueError("interpolation arrays must be non-empty and equal length")
    if x < xs[0] - 1e-9 or x > xs[-1] + 1e-9:
        return 0.0
    if x <= xs[0]:
        return float(ys[0])
    if x >= xs[-1]:
        return float(ys[-1])
    upper = bisect_right(xs, x)
    lower = upper - 1
    x0, x1 = xs[lower], xs[upper]
    y0, y1 = ys[lower], ys[upper]
    if abs(x1 - x0) <= 1e-12:
        return float(y1)
    fraction = (x - x0) / (x1 - x0)
    return y0 + fraction * (y1 - y0)


def candela_at(photometry: IESPhotometry, vertical_angle_deg: float, horizontal_angle_deg: float = 0.0) -> float:
    """Interpolate luminous intensity in candela for a downward Type-C direction."""
    if not math.isfinite(vertical_angle_deg) or not math.isfinite(horizontal_angle_deg):
        raise ValueError("photometric angles must be finite")
    gamma = float(vertical_angle_deg)
    if gamma < 0 or gamma > 180:
        return 0.0

    if photometry.rotationally_symmetric:
        return _linear_interpolate(photometry.vertical_angles_deg, photometry.candela_values[0], gamma)

    if not photometry.supports_full_horizontal_interpolation:
        raise NotImplementedError("partial horizontal-plane symmetry is not implemented")

    phi = horizontal_angle_deg % 360.0
    h_angles = photometry.horizontal_angles_deg
    # Interpolate vertically on each bracketing C-plane, then horizontally.
    if phi <= h_angles[0]:
        return _linear_interpolate(photometry.vertical_angles_deg, photometry.candela_values[0], gamma)
    if phi >= h_angles[-1]:
        return _linear_interpolate(photometry.vertical_angles_deg, photometry.candela_values[-1], gamma)
    upper = bisect_right(h_angles, phi)
    lower = upper - 1
    h0, h1 = h_angles[lower], h_angles[upper]
    i0 = _linear_interpolate(photometry.vertical_angles_deg, photometry.candela_values[lower], gamma)
    i1 = _linear_interpolate(photometry.vertical_angles_deg, photometry.candela_values[upper], gamma)
    if abs(h1 - h0) <= 1e-12:
        return i1
    fraction = (phi - h0) / (h1 - h0)
    return i0 + fraction * (i1 - i0)


def direct_horizontal_illuminance_lux(
    photometry: IESPhotometry,
    fixture: PhotometricFixture,
    point_x_m: float,
    point_y_m: float,
) -> float:
    """Direct illuminance on a horizontal plane from one downward fixture.

    E = I(gamma,C) * cos(gamma) / r². This computes direct light only; it does
    not model interreflection, room-surface reflectance, obstruction or daylight.
    """
    if fixture.height_above_plane_m <= 0:
        raise ValueError("fixture height above evaluation plane must be positive")
    if fixture.multiplier < 0:
        raise ValueError("fixture multiplier cannot be negative")
    dx = point_x_m - fixture.x_m
    dy = point_y_m - fixture.y_m
    horizontal = math.hypot(dx, dy)
    h = fixture.height_above_plane_m
    distance_sq = horizontal * horizontal + h * h
    gamma_rad = math.atan2(horizontal, h)
    gamma_deg = math.degrees(gamma_rad)
    if gamma_deg > 90.0 + 1e-9:
        return 0.0
    azimuth_deg = (math.degrees(math.atan2(dy, dx)) - fixture.rotation_deg) % 360.0
    intensity_cd = candela_at(photometry, gamma_deg, azimuth_deg)
    return max(0.0, fixture.multiplier * intensity_cd * math.cos(gamma_rad) / distance_sq)


def total_direct_illuminance_lux(
    photometry: IESPhotometry,
    fixtures: Iterable[PhotometricFixture],
    point_x_m: float,
    point_y_m: float,
    *,
    maintenance_factor: float = 1.0,
) -> float:
    if not 0 < maintenance_factor <= 1:
        raise ValueError("maintenance_factor must be in (0,1]")
    return maintenance_factor * sum(
        direct_horizontal_illuminance_lux(photometry, fixture, point_x_m, point_y_m)
        for fixture in fixtures
    )


def even_fixture_grid_from_feet(
    *,
    room_length_ft: float,
    room_width_ft: float,
    rows: int,
    cols: int,
    ceiling_height_ft: float,
    evaluation_plane_height_ft: float,
    fixture_multiplier: float = 1.0,
) -> tuple[PhotometricFixture, ...]:
    if ceiling_height_ft <= evaluation_plane_height_ft:
        raise ValueError("ceiling height must be above evaluation plane")
    if fixture_multiplier < 0:
        raise ValueError("fixture multiplier cannot be negative")
    vertical_m = (ceiling_height_ft - evaluation_plane_height_ft) * FT_TO_M
    points = grid_positions(room_length_ft, room_width_ft, rows, cols)
    return tuple(
        PhotometricFixture(
            fixture_id=f"F{index}",
            x_m=x_ft * FT_TO_M,
            y_m=y_ft * FT_TO_M,
            height_above_plane_m=vertical_m,
            multiplier=fixture_multiplier,
        )
        for index, (x_ft, y_ft) in enumerate(points, start=1)
    )


def illuminance_grid(
    photometry: IESPhotometry,
    fixtures: Sequence[PhotometricFixture],
    *,
    room_width_m: float,
    room_length_m: float,
    x_samples: int,
    y_samples: int,
    maintenance_factor: float = 1.0,
) -> tuple[IlluminancePoint, ...]:
    if room_width_m <= 0 or room_length_m <= 0:
        raise ValueError("room dimensions must be positive")
    if x_samples < 2 or y_samples < 2:
        raise ValueError("x_samples and y_samples must be >= 2")
    if not fixtures:
        raise ValueError("at least one fixture is required")

    points = []
    for yi in range(y_samples):
        y = room_length_m * yi / (y_samples - 1)
        for xi in range(x_samples):
            x = room_width_m * xi / (x_samples - 1)
            lux = total_direct_illuminance_lux(
                photometry,
                fixtures,
                x,
                y,
                maintenance_factor=maintenance_factor,
            )
            points.append(IlluminancePoint(x, y, lux))
    return tuple(points)


def summarize_illuminance(
    points: Sequence[IlluminancePoint],
    *,
    maintenance_factor: float,
    target_min_lux: float | None = None,
    target_max_lux: float | None = None,
) -> IlluminanceSummary:
    if not points:
        raise ValueError("illuminance summary requires sample points")
    if not 0 < maintenance_factor <= 1:
        raise ValueError("maintenance_factor must be in (0,1]")
    values = [point.lux for point in points]
    minimum = min(values)
    maximum = max(values)
    average = sum(values) / len(values)
    if target_min_lux is not None and target_min_lux < 0:
        raise ValueError("target_min_lux cannot be negative")
    if target_max_lux is not None and target_max_lux < 0:
        raise ValueError("target_max_lux cannot be negative")
    if target_min_lux is not None and target_max_lux is not None and target_min_lux > target_max_lux:
        raise ValueError("target minimum cannot exceed target maximum")

    band_fraction = None
    if target_min_lux is not None or target_max_lux is not None:
        lower = -math.inf if target_min_lux is None else target_min_lux
        upper = math.inf if target_max_lux is None else target_max_lux
        band_fraction = sum(lower <= value <= upper for value in values) / len(values)

    return IlluminanceSummary(
        minimum_lux=minimum,
        average_lux=average,
        maximum_lux=maximum,
        min_to_avg=minimum / average if average > 0 else 0.0,
        min_to_max=minimum / maximum if maximum > 0 else 0.0,
        max_to_avg=maximum / average if average > 0 else 0.0,
        target_min_lux=target_min_lux,
        target_max_lux=target_max_lux,
        target_band_fraction=band_fraction,
        sample_points=len(values),
        maintenance_factor=maintenance_factor,
    )


def grid_matrix(
    points: Sequence[IlluminancePoint],
    *,
    x_samples: int,
    y_samples: int,
) -> list[list[float]]:
    if len(points) != x_samples * y_samples:
        raise ValueError("point count does not match requested grid shape")
    return [
        [points[row * x_samples + col].lux for col in range(x_samples)]
        for row in range(y_samples)
    ]


def points_rows(points: Iterable[IlluminancePoint]) -> list[dict[str, float]]:
    return [
        {"x_m": point.x_m, "y_m": point.y_m, "lux": point.lux}
        for point in points
    ]
