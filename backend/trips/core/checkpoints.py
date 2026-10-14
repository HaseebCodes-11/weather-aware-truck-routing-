"""Place weather checkpoints along a route and compute when the truck reaches them."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta

from .geo import Polyline
from .risk import RiskAssessment, Weather

ALLOWED_INTERVALS_MI = (10, 25, 50)


@dataclass
class Checkpoint:
    index: int
    mile: float
    lat: float
    lon: float
    eta: datetime
    weather: Weather | None = None
    risk: RiskAssessment | None = None
    extra: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        w = self.weather
        return {
            "index": self.index,
            "mile": round(self.mile, 1),
            "lat": round(self.lat, 5),
            "lon": round(self.lon, 5),
            "eta": self.eta.isoformat(),
            "weather": None if w is None else {
                "available": w.available,
                "wind_mph": round(w.wind_mph, 1),
                "gust_mph": None if w.gust_mph is None else round(w.gust_mph, 1),
                "rain_in_hr": round(w.rain_in_hr, 3),
                "snow_in_hr": round(w.snow_in_hr, 3),
                "temp_f": None if w.temp_f is None else round(w.temp_f, 1),
                "weather_code": w.weather_code,
            },
            "risk": None if self.risk is None else self.risk.to_dict(),
        }


def place_checkpoints(poly: Polyline, departure: datetime, interval_mi: float) -> list[Checkpoint]:
    """Checkpoints at the origin, every `interval_mi`, and at the destination.

    The ETA at each checkpoint is departure + time to reach that mile, so each
    one is matched to the forecast hour the truck is actually there.
    """
    if interval_mi <= 0:
        raise ValueError("interval must be positive")
    miles: list[float] = []
    m = 0.0
    while m < poly.total_mi - 1e-6:
        miles.append(m)
        m += interval_mi
    miles.append(poly.total_mi)
    # Avoid a near-duplicate final checkpoint (e.g. 2 miles after the last one).
    if len(miles) > 2 and miles[-1] - miles[-2] < interval_mi * 0.2:
        miles.pop(-2)

    out = []
    for i, mile in enumerate(miles):
        (lat, lon), secs = poly.locate(mile)
        out.append(Checkpoint(i, mile, lat, lon, departure + timedelta(seconds=secs)))
    return out
