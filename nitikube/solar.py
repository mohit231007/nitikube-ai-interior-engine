from __future__ import annotations

from dataclasses import dataclass
from math import acos, asin, cos, degrees, pi, radians, sin


def solar_declination_deg(day_of_year: int) -> float:
    """Approximate solar declination using the Cooper equation.

    delta = 23.45 sin(360 (284+n) / 365)
    Suitable for conceptual solar geometry; detailed compliance/simulation can
    later use higher-fidelity ephemeris/weather engines.
    """
    if not 1 <= day_of_year <= 366:
        raise ValueError("day_of_year must be in [1, 366]")
    return 23.45 * sin(radians(360.0 * (284 + day_of_year) / 365.0))


def hour_angle_deg(solar_time_hours: float) -> float:
    """Solar hour angle: 15° per hour from solar noon."""
    if not 0 <= solar_time_hours <= 24:
        raise ValueError("solar_time_hours must be in [0, 24]")
    return 15.0 * (solar_time_hours - 12.0)


def solar_altitude_deg(latitude_deg: float, declination_deg: float, hour_angle_deg_value: float) -> float:
    """Solar altitude above the horizon from latitude, declination and hour angle."""
    if not -90 <= latitude_deg <= 90:
        raise ValueError("latitude must be in [-90, 90]")
    phi = radians(latitude_deg)
    delta = radians(declination_deg)
    omega = radians(hour_angle_deg_value)
    sin_alpha = sin(phi) * sin(delta) + cos(phi) * cos(delta) * cos(omega)
    sin_alpha = max(-1.0, min(1.0, sin_alpha))
    return degrees(asin(sin_alpha))


def solar_azimuth_from_south_deg(latitude_deg: float, declination_deg: float, hour_angle_deg_value: float) -> float:
    """Signed solar azimuth measured from due south: east negative, west positive.

    Uses an atan-free acos magnitude plus hour-angle sign for an interpretable
    architectural solar diagnostic. Near zenith, azimuth is numerically
    sensitive; detailed rendering should later use a full ephemeris library.
    """
    altitude = solar_altitude_deg(latitude_deg, declination_deg, hour_angle_deg_value)
    alpha = radians(altitude)
    phi = radians(latitude_deg)
    delta = radians(declination_deg)
    denom = cos(alpha) * cos(phi)
    if abs(denom) < 1e-12:
        return 0.0
    cos_gamma = (sin(alpha) * sin(phi) - sin(delta)) / denom
    cos_gamma = max(-1.0, min(1.0, cos_gamma))
    magnitude = degrees(acos(cos_gamma))
    return magnitude if hour_angle_deg_value >= 0 else -magnitude


def horizontal_shadow_length(object_height_m: float, solar_altitude_deg_value: float) -> float:
    """Horizontal shadow length = height / tan(altitude)."""
    from math import tan

    if object_height_m < 0:
        raise ValueError("object_height_m cannot be negative")
    if not 0 < solar_altitude_deg_value < 90:
        raise ValueError("solar altitude must be between 0 and 90 degrees")
    return object_height_m / tan(radians(solar_altitude_deg_value))


def overhang_depth_for_vertical_shade(window_height_m: float, solar_altitude_deg_value: float) -> float:
    """Idealized horizontal overhang depth to shade a vertical height at a given altitude.

    D = H / tan(alpha). This is a 2D section geometry check and ignores wall
    azimuth, sun azimuth and offsets; use it only as a transparent first-pass.
    """
    return horizontal_shadow_length(window_height_m, solar_altitude_deg_value)


@dataclass(frozen=True)
class SolarPosition:
    day_of_year: int
    solar_time_hours: float
    declination_deg: float
    hour_angle_deg: float
    altitude_deg: float
    azimuth_from_south_deg: float


def solar_position(latitude_deg: float, day_of_year: int, solar_time_hours: float) -> SolarPosition:
    decl = solar_declination_deg(day_of_year)
    hour = hour_angle_deg(solar_time_hours)
    altitude = solar_altitude_deg(latitude_deg, decl, hour)
    azimuth = solar_azimuth_from_south_deg(latitude_deg, decl, hour)
    return SolarPosition(day_of_year, solar_time_hours, decl, hour, altitude, azimuth)
