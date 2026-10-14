"""Weather risk classification.

Everything in this module is pure and deterministic so it can be unit tested
without network access. Thresholds come straight from the assessment brief.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum


class RiskLevel(IntEnum):
    LOW = 0
    MODERATE = 1
    HIGH = 2
    SEVERE = 3
    NO_TRAVEL = 4

    @property
    def label(self) -> str:
        return {
            RiskLevel.LOW: "Low",
            RiskLevel.MODERATE: "Moderate",
            RiskLevel.HIGH: "High",
            RiskLevel.SEVERE: "Severe",
            RiskLevel.NO_TRAVEL: "No Travel",
        }[self]

    @property
    def key(self) -> str:
        return self.name.lower()


# Each band is (lower bound, level). A value belongs to the highest band whose
# lower bound it reaches. Lower bounds are inclusive, matching the brief:
#   Wind  <25 | 25-34 | 35-44 | 45-54 | >=55 mph
#   Rain  <0.10 | 0.10-0.25 | 0.25-0.50 | 0.50-1.00 | >1.00 in/hr
#   Snow  <0.5 | 0.5-1.0 | 1.0-2.0 | 2.0-3.0 | >3.0 in/hr
WIND_BANDS = [
    (25.0, RiskLevel.MODERATE),
    (35.0, RiskLevel.HIGH),
    (45.0, RiskLevel.SEVERE),
    (55.0, RiskLevel.NO_TRAVEL),
]
RAIN_BANDS = [
    (0.10, RiskLevel.MODERATE),
    (0.25, RiskLevel.HIGH),
    (0.50, RiskLevel.SEVERE),
]
SNOW_BANDS = [
    (0.5, RiskLevel.MODERATE),
    (1.0, RiskLevel.HIGH),
    (2.0, RiskLevel.SEVERE),
]
# "No Travel" for rain and snow is strictly greater than the top bound.
RAIN_NO_TRAVEL_ABOVE = 1.00
SNOW_NO_TRAVEL_ABOVE = 3.0

# Load rules (lb).
HEAVY_LOAD_NO_TRAVEL_LB = 30_000  # 45-54 mph wind + load > 30,000 lb -> No Travel
HEAVY_LOAD_SEVERE_LB = 40_000  # 35-44 mph wind + load > 40,000 lb -> Severe


def _band(value: float, bands: list[tuple[float, RiskLevel]]) -> RiskLevel:
    level = RiskLevel.LOW
    for lower, band_level in bands:
        if value >= lower:
            level = band_level
    return level


def classify_wind(wind_mph: float) -> RiskLevel:
    return _band(wind_mph, WIND_BANDS)


def classify_rain(rain_in_hr: float) -> RiskLevel:
    if rain_in_hr > RAIN_NO_TRAVEL_ABOVE:
        return RiskLevel.NO_TRAVEL
    return _band(rain_in_hr, RAIN_BANDS)


def classify_snow(snow_in_hr: float) -> RiskLevel:
    if snow_in_hr > SNOW_NO_TRAVEL_ABOVE:
        return RiskLevel.NO_TRAVEL
    return _band(snow_in_hr, SNOW_BANDS)


def apply_load_rules(wind_mph: float, load_lb: float, wind_level: RiskLevel) -> tuple[RiskLevel, str | None]:
    """Escalate the wind level for heavy loads. Returns (level, reason)."""
    if wind_mph >= 55:
        return RiskLevel.NO_TRAVEL, "Wind ≥55 mph is No Travel for any load"
    if 45 <= wind_mph < 55 and load_lb > HEAVY_LOAD_NO_TRAVEL_LB:
        return RiskLevel.NO_TRAVEL, f"Wind {wind_mph:.0f} mph with load over {HEAVY_LOAD_NO_TRAVEL_LB:,} lb"
    if 35 <= wind_mph < 45 and load_lb > HEAVY_LOAD_SEVERE_LB:
        return max(wind_level, RiskLevel.SEVERE), f"Wind {wind_mph:.0f} mph with load over {HEAVY_LOAD_SEVERE_LB:,} lb"
    return wind_level, None


@dataclass
class Weather:
    wind_mph: float = 0.0
    gust_mph: float | None = None
    rain_in_hr: float = 0.0
    snow_in_hr: float = 0.0
    temp_f: float | None = None
    weather_code: int | None = None
    available: bool = True


@dataclass
class RiskAssessment:
    level: RiskLevel
    wind_level: RiskLevel
    rain_level: RiskLevel
    snow_level: RiskLevel
    reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "level": int(self.level),
            "level_key": self.level.key,
            "level_name": self.level.label,
            "components": {
                "wind": self.wind_level.label,
                "rain": self.rain_level.label,
                "snow": self.snow_level.label,
            },
            "reasons": self.reasons,
        }


def assess(weather: Weather, load_lb: float) -> RiskAssessment:
    """Classify one checkpoint. The overall level is the worst component."""
    if not weather.available:
        return RiskAssessment(
            RiskLevel.LOW, RiskLevel.LOW, RiskLevel.LOW, RiskLevel.LOW,
            ["Forecast not available for this time; treated as Low"],
        )

    wind_level = classify_wind(weather.wind_mph)
    wind_level, load_reason = apply_load_rules(weather.wind_mph, load_lb, wind_level)
    rain_level = classify_rain(weather.rain_in_hr)
    snow_level = classify_snow(weather.snow_in_hr)

    reasons: list[str] = []
    if wind_level > RiskLevel.LOW:
        reasons.append(load_reason or f"Wind {weather.wind_mph:.0f} mph ({wind_level.label})")
    if rain_level > RiskLevel.LOW:
        reasons.append(f"Rain {weather.rain_in_hr:.2f} in/hr ({rain_level.label})")
    if snow_level > RiskLevel.LOW:
        reasons.append(f"Snow {weather.snow_in_hr:.2f} in/hr ({snow_level.label})")

    level = max(wind_level, rain_level, snow_level)
    return RiskAssessment(level, wind_level, rain_level, snow_level, reasons)


def heat_intensity(weather: Weather, load_lb: float) -> float:
    """Continuous 0..1 value for the heatmap.

    The discrete level drives the colour scale; the fractional part interpolates
    inside the band so the heatmap changes smoothly instead of in steps.
    """
    if not weather.available:
        return 0.0
    level = assess(weather, load_lb).level
    if level >= RiskLevel.NO_TRAVEL:
        return 1.0

    def frac(value: float, bands: list[float]) -> float:
        # bands are the lower bounds of Moderate..NoTravel for this metric
        edges = [0.0, *bands]
        for i in range(len(edges) - 1):
            lo, hi = edges[i], edges[i + 1]
            if lo <= value < hi:
                return (value - lo) / (hi - lo)
        return 0.0

    # Only the metrics that actually set the level contribute the fractional part.
    candidates = [
        (classify_wind(weather.wind_mph), frac(weather.wind_mph, [25, 35, 45, 55])),
        (classify_rain(weather.rain_in_hr), frac(weather.rain_in_hr, [0.10, 0.25, 0.50, 1.00])),
        (classify_snow(weather.snow_in_hr), frac(weather.snow_in_hr, [0.5, 1.0, 2.0, 3.0])),
    ]
    within = max((f for lvl, f in candidates if lvl == level), default=0.0)
    return round(min(1.0, (int(level) + within * 0.99) / 4), 3)
