"""Small geometry helpers. Coordinates are (lat, lon) in degrees, distances in miles."""
from __future__ import annotations

import math
from bisect import bisect_left
from dataclasses import dataclass

EARTH_RADIUS_MI = 3958.7613
METERS_PER_MILE = 1609.344


def haversine_mi(a: tuple[float, float], b: tuple[float, float]) -> float:
    lat1, lon1 = map(math.radians, a)
    lat2, lon2 = map(math.radians, b)
    dlat, dlon = lat2 - lat1, lon2 - lon1
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 2 * EARTH_RADIUS_MI * math.asin(min(1.0, math.sqrt(h)))


def offset_point(origin: tuple[float, float], bearing_deg: float, distance_mi: float) -> tuple[float, float]:
    """Point reached travelling `distance_mi` from origin on the given bearing."""
    lat1, lon1 = map(math.radians, origin)
    brg = math.radians(bearing_deg)
    d = distance_mi / EARTH_RADIUS_MI
    lat2 = math.asin(math.sin(lat1) * math.cos(d) + math.cos(lat1) * math.sin(d) * math.cos(brg))
    lon2 = lon1 + math.atan2(math.sin(brg) * math.sin(d) * math.cos(lat1), math.cos(d) - math.sin(lat1) * math.sin(lat2))
    return math.degrees(lat2), (math.degrees(lon2) + 540) % 360 - 180


def bearing_deg(a: tuple[float, float], b: tuple[float, float]) -> float:
    lat1, lon1 = map(math.radians, a)
    lat2, lon2 = map(math.radians, b)
    dlon = lon2 - lon1
    x = math.sin(dlon) * math.cos(lat2)
    y = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(dlon)
    return (math.degrees(math.atan2(x, y)) + 360) % 360


@dataclass
class Polyline:
    """A route geometry with cumulative distance (mi) and time (s) per vertex."""

    points: list[tuple[float, float]]
    cum_mi: list[float]
    cum_s: list[float]

    @property
    def total_mi(self) -> float:
        return self.cum_mi[-1] if self.cum_mi else 0.0

    @property
    def total_s(self) -> float:
        return self.cum_s[-1] if self.cum_s else 0.0

    def locate(self, mile: float) -> tuple[tuple[float, float], float]:
        """Interpolated (lat, lon) and elapsed seconds at a distance along the line."""
        if mile <= 0:
            return self.points[0], 0.0
        if mile >= self.total_mi:
            return self.points[-1], self.total_s
        i = bisect_left(self.cum_mi, mile)
        i = max(1, i)
        d0, d1 = self.cum_mi[i - 1], self.cum_mi[i]
        t = 0.0 if d1 == d0 else (mile - d0) / (d1 - d0)
        (la0, lo0), (la1, lo1) = self.points[i - 1], self.points[i]
        point = (la0 + (la1 - la0) * t, lo0 + (lo1 - lo0) * t)
        secs = self.cum_s[i - 1] + (self.cum_s[i] - self.cum_s[i - 1]) * t
        return point, secs


def build_polyline(
    points: list[tuple[float, float]],
    segment_seconds: list[float] | None = None,
    max_speed_mph: float | None = None,
) -> Polyline:
    """Build cumulative distance/time arrays.

    `segment_seconds` comes from the routing engine (one value per segment).
    `max_speed_mph` caps speed per segment, which is how we adjust car routing
    times to realistic truck times.
    """
    cum_mi = [0.0]
    cum_s = [0.0]
    n_seg = len(points) - 1
    seg_mi = [haversine_mi(points[i], points[i + 1]) for i in range(n_seg)]
    for i in range(n_seg):
        secs = segment_seconds[i] if segment_seconds and i < len(segment_seconds) else None
        if secs is None:
            secs = seg_mi[i] / 55.0 * 3600  # sensible default if the engine gave no timing
        if max_speed_mph and seg_mi[i] > 0:
            secs = max(secs, seg_mi[i] / max_speed_mph * 3600)
        cum_mi.append(cum_mi[-1] + seg_mi[i])
        cum_s.append(cum_s[-1] + secs)
    return Polyline(points, cum_mi, cum_s)


def thin(poly: Polyline, min_gap_mi: float = 0.25, max_points: int = 1500) -> list[list[float]]:
    """Reduce vertices for the browser. Returns [lat, lon, mile] triples."""
    if not poly.points:
        return []
    gap = max(min_gap_mi, poly.total_mi / max_points if max_points else min_gap_mi)
    out = [[*poly.points[0], 0.0]]
    last = 0.0
    for p, m in zip(poly.points[1:-1], poly.cum_mi[1:-1]):
        if m - last >= gap:
            out.append([p[0], p[1], m])
            last = m
    out.append([*poly.points[-1], poly.total_mi])
    return [[round(a, 5), round(b, 5), round(c, 2)] for a, b, c in out]


def overlap_ratio(a: Polyline, b: Polyline, tolerance_mi: float = 1.0, samples: int = 60) -> float:
    """Share of route `a` (by sampled distance) that lies within `tolerance_mi` of route `b`."""
    if a.total_mi == 0 or b.total_mi == 0:
        return 1.0
    b_samples = [b.locate(b.total_mi * j / (samples * 2))[0] for j in range(samples * 2 + 1)]
    hits = 0
    for k in range(samples + 1):
        p, _ = a.locate(a.total_mi * k / samples)
        if min(haversine_mi(p, q) for q in b_samples) <= tolerance_mi + b.total_mi / (samples * 2):
            hits += 1
    return hits / (samples + 1)
