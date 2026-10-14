"""Offline fakes for the routing and weather services."""
from datetime import datetime, timedelta, timezone

from trips.clients.weather import HourlySeries
from trips.core.geo import build_polyline


class FakeRoute:
    def __init__(self, points, mph, summary="", source="osrm"):
        self.polyline = build_polyline(points, None, None)
        # Constant speed so ETAs are easy to reason about in tests.
        self.polyline.cum_s = [m / mph * 3600 for m in self.polyline.cum_mi]
        self.summary = summary
        self.source = source

    @property
    def duration_s(self):
        return self.polyline.total_s


def straight_line(a, b, n=40):
    return [(a[0] + (b[0] - a[0]) * i / n, a[1] + (b[1] - a[1]) * i / n) for i in range(n + 1)]


def flat_series(start, hours, wind=5.0, rain=0.0, snow=0.0):
    start = start.replace(minute=0, second=0, microsecond=0)
    return HourlySeries(start, [wind] * hours, [wind + 5] * hours, [rain] * hours, [snow] * hours, [50.0] * hours, [0] * hours)


def make_weather_fn(rule):
    """`rule(lat, lon, start)` returns an HourlySeries for that coordinate."""

    def fn(coords, start, end):
        return [rule(lat, lon, start) for lat, lon in coords]

    return fn


def future(hours=2):
    return (datetime.now(timezone.utc) + timedelta(hours=hours)).replace(minute=0, second=0, microsecond=0)
