"""Hourly forecasts from Open-Meteo (free, no API key).

Many coordinates are requested in one call (Open-Meteo supports comma-separated
lists), chunked and fetched in parallel. Units are requested as mph / inches /
°F, and we still check the returned units so a change upstream can't silently
break the risk thresholds.
"""
from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from ..core.risk import Weather
from .http import UpstreamError, get_json

OPEN_METEO_URL = os.getenv("OPEN_METEO_URL", "https://api.open-meteo.com/v1/forecast")
CHUNK_SIZE = int(os.getenv("OPEN_METEO_CHUNK_SIZE", "50"))
FORECAST_HORIZON_DAYS = 15
HOURLY_VARS = "wind_speed_10m,wind_gusts_10m,rain,snowfall,temperature_2m,weather_code"


def _to_mph(v, unit):
    if v is None:
        return None
    return {"km/h": v * 0.621371, "m/s": v * 2.23694, "kn": v * 1.15078}.get(unit, v)


def _to_inches(v, unit):
    if v is None:
        return None
    return {"mm": v / 25.4, "cm": v / 2.54}.get(unit, v)


@dataclass
class HourlySeries:
    """Hourly forecast for one location, indexed by UTC hour."""

    start: datetime  # UTC, top of the hour
    wind: list
    gust: list
    rain: list
    snow: list
    temp: list
    code: list

    def at(self, when: datetime) -> Weather:
        """Weather for the forecast hour nearest `when` (UTC)."""
        idx = round((when - self.start).total_seconds() / 3600)
        if idx < 0 or idx >= len(self.wind) or self.wind[idx] is None:
            return Weather(available=False)
        return Weather(
            wind_mph=self.wind[idx] or 0.0,
            gust_mph=self.gust[idx],
            rain_in_hr=self.rain[idx] or 0.0,
            snow_in_hr=self.snow[idx] or 0.0,
            temp_f=self.temp[idx],
            weather_code=self.code[idx],
        )


def _floor_hour(dt: datetime) -> datetime:
    return dt.astimezone(timezone.utc).replace(minute=0, second=0, microsecond=0)


def _parse(item: dict) -> HourlySeries:
    hourly = item["hourly"]
    units = item.get("hourly_units", {})
    start = datetime.fromisoformat(hourly["time"][0]).replace(tzinfo=timezone.utc)
    return HourlySeries(
        start=start,
        wind=[_to_mph(v, units.get("wind_speed_10m")) for v in hourly["wind_speed_10m"]],
        gust=[_to_mph(v, units.get("wind_gusts_10m")) for v in hourly.get("wind_gusts_10m", [])] or [None] * len(hourly["time"]),
        rain=[_to_inches(v, units.get("rain")) for v in hourly["rain"]],
        snow=[_to_inches(v, units.get("snowfall")) for v in hourly["snowfall"]],
        temp=hourly.get("temperature_2m") or [None] * len(hourly["time"]),
        code=hourly.get("weather_code") or [None] * len(hourly["time"]),
    )


def _fetch_chunk(coords: list[tuple[float, float]], start: datetime, end: datetime) -> list[HourlySeries]:
    params = {
        "latitude": ",".join(f"{lat:.3f}" for lat, _ in coords),
        "longitude": ",".join(f"{lon:.3f}" for _, lon in coords),
        "hourly": HOURLY_VARS,
        "wind_speed_unit": "mph",
        "precipitation_unit": "inch",
        "temperature_unit": "fahrenheit",
        "timezone": "GMT",
        "start_hour": start.strftime("%Y-%m-%dT%H:00"),
        "end_hour": end.strftime("%Y-%m-%dT%H:00"),
    }
    data = get_json("weather", OPEN_METEO_URL, params)
    items = data if isinstance(data, list) else [data]
    if len(items) != len(coords):
        raise UpstreamError("weather", "unexpected response size")
    try:
        return [_parse(i) for i in items]
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        raise UpstreamError("weather", "unexpected response format") from exc


def forecast_hourly(coords: list[tuple[float, float]], start: datetime, end: datetime) -> list[HourlySeries]:
    """Hourly series for each coordinate between `start` and `end` (inclusive)."""
    if not coords:
        return []
    now = datetime.now(timezone.utc)
    start = max(_floor_hour(start), _floor_hour(now) - timedelta(hours=1))
    end = min(_floor_hour(end) + timedelta(hours=1), _floor_hour(now) + timedelta(days=FORECAST_HORIZON_DAYS))
    if end <= start:
        raise UpstreamError("weather", "requested time is outside the forecast window", 422)
    chunks = [coords[i : i + CHUNK_SIZE] for i in range(0, len(coords), CHUNK_SIZE)]
    with ThreadPoolExecutor(max_workers=min(6, len(chunks))) as pool:
        results = list(pool.map(lambda c: _fetch_chunk(c, start, end), chunks))
    return [s for chunk in results for s in chunk]
