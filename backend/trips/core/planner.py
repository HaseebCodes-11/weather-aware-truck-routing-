"""Trip planning pipeline: routes -> checkpoints -> weather -> risk -> recommendation.

External calls are injected (`routes_fn`, `weather_fn`) so the whole pipeline
can be tested offline with fixtures.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Callable

from .checkpoints import Checkpoint, place_checkpoints
from .geo import bearing_deg, haversine_mi, offset_point, thin
from .recommend import explain, ranking_key, summarize
from .risk import RiskLevel, Weather, assess, heat_intensity

ROUTE_IDS = "ABC"
ADVICE_SEARCH_HOURS = 48
CORRIDOR_SAMPLES_PER_ROUTE = 24
CORRIDOR_OFFSET_MI = 25
CORRIDOR_DEDUP_MI = 10


@dataclass
class TripRequest:
    origin: dict  # {"label", "lat", "lon"}
    destination: dict
    departure: datetime  # timezone-aware
    load_lb: float
    interval_mi: int


def _key(c: Checkpoint) -> tuple[float, float]:
    # ~1 km grid; neighbouring checkpoints from different routes share a forecast.
    return (round(c.lat, 2), round(c.lon, 2))


def _evaluate(route, checkpoints, series_by_key, load_lb, shift: timedelta = timedelta(0)):
    for cp in checkpoints:
        series = series_by_key.get(_key(cp))
        cp.weather = series.at(cp.eta + shift) if series else Weather(available=False)
        cp.risk = assess(cp.weather, load_lb)
    risk = summarize(checkpoints)
    return risk, ranking_key(risk, route.duration_s)


def corridor_points(routes) -> list[list[float]]:
    """Grid of points along and to either side of every route, for the heatmap."""
    pts: list[tuple[float, float]] = []
    for r in routes:
        poly = r.polyline
        n = CORRIDOR_SAMPLES_PER_ROUTE
        for k in range(n + 1):
            mile = poly.total_mi * k / n
            p, _ = poly.locate(mile)
            ahead, _ = poly.locate(min(poly.total_mi, mile + 2))
            behind, _ = poly.locate(max(0.0, mile - 2))
            brg = bearing_deg(behind, ahead)
            pts.append(p)
            pts.append(offset_point(p, brg + 90, CORRIDOR_OFFSET_MI))
            pts.append(offset_point(p, brg - 90, CORRIDOR_OFFSET_MI))
    kept: list[tuple[float, float]] = []
    for p in pts:
        if all(haversine_mi(p, q) >= CORRIDOR_DEDUP_MI for q in kept):
            kept.append(p)
    return [[round(a, 3), round(b, 3)] for a, b in kept]


def _departure_advice(routes, checkpoint_sets, series_by_key, req: TripRequest, best_key):
    """If the recommended plan has Severe/No Travel miles, look for a better start time."""
    if best_key[0] == 0 and best_key[1] == 0:
        return None
    best = None
    for hours in range(1, ADVICE_SEARCH_HOURS + 1):
        shift = timedelta(hours=hours)
        for rid, route, cps in zip(ROUTE_IDS, routes, checkpoint_sets):
            shifted = [Checkpoint(c.index, c.mile, c.lat, c.lon, c.eta) for c in cps]
            _, key = _evaluate(route, shifted, series_by_key, req.load_lb, shift)
            if any(not c.weather.available for c in shifted):
                continue  # don't recommend a time we have no forecast for
            cand = (key[:3], hours, key, rid)
            if best is None or cand[:2] < best[:2]:
                best = cand
    if best is None or best[0] >= best_key[:3]:
        return None
    _, hours, key, rid = best
    return {
        "suggested_departure": (req.departure + timedelta(hours=hours)).isoformat(),
        "delay_hours": hours,
        "route_id": rid,
        "no_travel_miles": key[0],
        "severe_miles": key[1],
        "high_miles": key[2],
        "message": (
            f"Leaving {hours} h later on Route {rid} reduces exposure to "
            f"{key[0]:.0f} No Travel, {key[1]:.0f} Severe and {key[2]:.0f} High miles "
            f"(now {best_key[0]:.0f} / {best_key[1]:.0f} / {best_key[2]:.0f})."
        ),
    }


def plan_trip(req: TripRequest, routes_fn: Callable, weather_fn: Callable) -> dict:
    origin = (req.origin["lat"], req.origin["lon"])
    dest = (req.destination["lat"], req.destination["lon"])
    routes = routes_fn(origin, dest)

    checkpoint_sets = [place_checkpoints(r.polyline, req.departure, req.interval_mi) for r in routes]
    unique_keys = sorted({_key(c) for cps in checkpoint_sets for c in cps})
    longest = max(r.duration_s for r in routes)
    series = weather_fn(
        list(unique_keys),
        req.departure,
        req.departure + timedelta(seconds=longest) + timedelta(hours=ADVICE_SEARCH_HOURS),
    )
    series_by_key = dict(zip(unique_keys, series))

    results = []
    for rid, route, cps in zip(ROUTE_IDS, routes, checkpoint_sets):
        risk, key = _evaluate(route, cps, series_by_key, req.load_lb)
        results.append({
            "id": rid,
            "label": f"Route {rid}",
            "summary": route.summary or "",
            "source": route.source,
            "distance_mi": round(route.polyline.total_mi, 1),
            "duration_s": round(route.duration_s),
            "arrival": (req.departure + timedelta(seconds=route.duration_s)).isoformat(),
            "geometry": thin(route.polyline),
            "checkpoints": [c.to_dict() for c in cps],
            "risk": risk.to_dict(),
            "_key": key,
        })

    ordered = sorted(results, key=lambda r: r["_key"])
    for rank, r in enumerate(ordered, start=1):
        r["rank"] = rank
        r["recommended"] = rank == 1
    best = ordered[0]
    reason = explain(best, ordered[1:])
    advice = _departure_advice(routes, checkpoint_sets, series_by_key, req, best["_key"])

    warnings = []
    if best["_key"][0] > 0:
        warnings.append("Every route has No Travel conditions at the planned time. Consider delaying departure.")
    if any(not c["weather"]["available"] for r in results for c in r["checkpoints"]):
        warnings.append("Some checkpoints are beyond the forecast window and were treated as Low risk.")
    if len(results) < 3:
        warnings.append(f"Only {len(results)} distinct route(s) were found between these points.")

    for r in results:
        r.pop("_key")

    return {
        "request": {
            "origin": req.origin,
            "destination": req.destination,
            "departure": req.departure.isoformat(),
            "load_lb": req.load_lb,
            "interval_mi": req.interval_mi,
        },
        "routes": results,
        "recommended_route_id": best["id"],
        "recommendation_reason": reason,
        "departure_advice": advice,
        "corridor": corridor_points(routes),
        "warnings": warnings,
        "risk_levels": [{"level": int(l), "key": l.key, "name": l.label} for l in RiskLevel],
    }


def build_heatmap(points: list[list[float]], start: datetime, hours: int, load_lb: float, weather_fn: Callable) -> dict:
    """Risk intensity for every corridor point and every hour in [start, start+hours]."""
    coords = [(p[0], p[1]) for p in points]
    series = weather_fn(coords, start, start + timedelta(hours=hours))
    base = start.replace(minute=0, second=0, microsecond=0)
    times, intensity, levels = [], [], []
    for h in range(hours + 1):
        t = base + timedelta(hours=h)
        times.append(t.isoformat())
        row_i, row_l = [], []
        for s in series:
            w = s.at(t)
            row_i.append(heat_intensity(w, load_lb))
            row_l.append(int(assess(w, load_lb).level))
        intensity.append(row_i)
        levels.append(row_l)
    return {"points": points, "times": times, "intensity": intensity, "levels": levels}
