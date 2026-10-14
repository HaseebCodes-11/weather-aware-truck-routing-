"""Routing via OSRM (public demo server by default, configurable).

OSRM returns at most a few alternatives and sometimes only one. To always offer
three genuinely different options, we add detour candidates through via-points
offset to either side of the straight line, then keep the ones that don't
overlap an existing route too much.
"""
from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

from ..core.geo import METERS_PER_MILE, Polyline, bearing_deg, build_polyline, haversine_mi, offset_point, overlap_ratio
from .http import UpstreamError, get_json

OSRM_URL = os.getenv("OSRM_URL", "https://router.project-osrm.org").rstrip("/")
TRUCK_MAX_SPEED_MPH = float(os.getenv("TRUCK_MAX_SPEED_MPH", "65"))
MAX_DETOUR_FACTOR = 1.6  # ignore alternatives that take more than 60% longer than the fastest
MAX_OVERLAP = 0.8  # alternatives must differ on at least 20% of their length


@dataclass
class RouteOption:
    polyline: Polyline
    osrm_distance_mi: float
    osrm_duration_s: float
    summary: str
    source: str  # "osrm" or "via-point"

    @property
    def duration_s(self) -> float:
        return self.polyline.total_s


def _request(coords: list[tuple[float, float]], alternatives: int) -> list[dict]:
    path = ";".join(f"{lon:.6f},{lat:.6f}" for lat, lon in coords)
    params = {
        "overview": "full",
        "geometries": "geojson",
        "annotations": "duration",
        "steps": "false",
        "alternatives": str(alternatives) if alternatives else "false",
    }
    data = get_json("routing", f"{OSRM_URL}/route/v1/driving/{path}", params)
    if data.get("code") != "Ok":
        raise UpstreamError("routing", data.get("message") or data.get("code") or "no route", 422)
    return data.get("routes", [])


def _to_option(route: dict, source: str) -> RouteOption:
    points = [(lat, lon) for lon, lat in route["geometry"]["coordinates"]]
    seg_secs: list[float] = []
    for leg in route.get("legs", []):
        seg_secs.extend(leg.get("annotation", {}).get("duration", []))
    if len(seg_secs) != len(points) - 1:
        seg_secs = []  # fall back to distance-proportional timing
    poly = build_polyline(points, seg_secs or None, TRUCK_MAX_SPEED_MPH)
    if not seg_secs:
        # Spread OSRM's total duration proportionally, still capped at truck speed.
        total = route.get("duration", 0.0)
        scale = total / poly.total_s if poly.total_s else 1.0
        poly.cum_s = [s * scale for s in poly.cum_s]
    summary = ", ".join(s for s in (leg.get("summary", "") for leg in route.get("legs", [])) if s)
    return RouteOption(
        polyline=poly,
        osrm_distance_mi=route.get("distance", 0.0) / METERS_PER_MILE,
        osrm_duration_s=route.get("duration", 0.0),
        summary=summary,
        source=source,
    )


def _is_distinct(candidate: RouteOption, chosen: list[RouteOption]) -> bool:
    for other in chosen:
        if overlap_ratio(candidate.polyline, other.polyline) > MAX_OVERLAP:
            return False
        if overlap_ratio(other.polyline, candidate.polyline) > MAX_OVERLAP:
            return False
    return True


def get_routes(origin: tuple[float, float], destination: tuple[float, float], wanted: int = 3) -> list[RouteOption]:
    if haversine_mi(origin, destination) < 1:
        raise UpstreamError("routing", "origin and destination are too close together", 422)

    options = [_to_option(r, "osrm") for r in _request([origin, destination], alternatives=wanted)]
    if not options:
        raise UpstreamError("routing", "no route found", 422)

    chosen: list[RouteOption] = []
    for opt in options:
        if _is_distinct(opt, chosen):
            chosen.append(opt)

    if len(chosen) < wanted:
        straight = haversine_mi(origin, destination)
        mid = ((origin[0] + destination[0]) / 2, (origin[1] + destination[1]) / 2)
        brg = bearing_deg(origin, destination)
        vias = [
            offset_point(mid, (brg + side) % 360, straight * frac)
            for frac in (0.15, 0.3)
            for side in (90, -90)
        ]

        def fetch(via):
            try:
                routes = _request([origin, via, destination], alternatives=0)
                return _to_option(routes[0], "via-point") if routes else None
            except UpstreamError:
                return None

        with ThreadPoolExecutor(max_workers=4) as pool:
            detours = [d for d in pool.map(fetch, vias) if d]

        fastest = min(o.duration_s for o in chosen)
        for d in sorted(detours, key=lambda o: o.duration_s):
            if len(chosen) >= wanted:
                break
            if d.duration_s <= fastest * MAX_DETOUR_FACTOR and _is_distinct(d, chosen):
                chosen.append(d)

    return sorted(chosen, key=lambda o: o.duration_s)[:wanted]
