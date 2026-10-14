"""End-to-end planning with fake routing and weather."""
import unittest
from datetime import timedelta

from trips.core.checkpoints import Checkpoint
from trips.core.planner import TripRequest, build_heatmap, plan_trip
from trips.core.recommend import ranking_key, summarize
from trips.core.risk import RiskLevel, Weather, assess

from .fixtures import FakeRoute, flat_series, future, make_weather_fn, straight_line

ORIGIN = {"label": "A", "lat": 40.0, "lon": -100.0}
DEST = {"label": "B", "lat": 40.0, "lon": -97.0}


def three_routes(_o, _d):
    # North (fast), middle (slow), south (medium). All ~160 mi.
    north = FakeRoute(straight_line((40, -100), (41, -98.5)) + straight_line((41, -98.5), (40, -97))[1:], mph=60)
    middle = FakeRoute(straight_line((40, -100), (40, -97)), mph=45)
    south = FakeRoute(straight_line((40, -100), (39, -98.5)) + straight_line((39, -98.5), (40, -97))[1:], mph=55)
    return [north, middle, south]


def request(load=35_000, interval=25):
    return TripRequest(ORIGIN, DEST, future(), load, interval)


class SummaryTests(unittest.TestCase):
    def _cps(self, levels, step=10):
        dep = future()
        cps = []
        for i, lvl in enumerate(levels):
            c = Checkpoint(i, i * step, 0, 0, dep)
            c.risk = assess(Weather(wind_mph={0: 0, 1: 30, 2: 40, 3: 50, 4: 60}[lvl]), 1)
            cps.append(c)
        return cps

    def test_segment_takes_worse_end(self):
        risk = summarize(self._cps([0, 2, 0]))
        self.assertEqual(risk.miles_by_level["high"], 20)
        self.assertEqual(risk.miles_by_level["low"], 0)
        self.assertEqual(risk.max_level, RiskLevel.HIGH)
        self.assertAlmostEqual(risk.avg_risk, 2.0)

    def test_ranking_order_follows_brief(self):
        a = summarize(self._cps([3, 0, 0]))  # 10 severe miles, fast
        b = summarize(self._cps([2, 2, 2]))  # 20 high miles, slow
        self.assertLess(ranking_key(b, 9999), ranking_key(a, 1))  # fewer severe beats speed

    def test_time_breaks_ties(self):
        a = summarize(self._cps([0, 0, 0]))
        self.assertLess(ranking_key(a, 100), ranking_key(a, 200))


class PlanTripTests(unittest.TestCase):
    def test_calm_weather_picks_fastest(self):
        calm = make_weather_fn(lambda lat, lon, start: flat_series(start, 300))
        result = plan_trip(request(), three_routes, calm)
        self.assertEqual(len(result["routes"]), 3)
        fastest = min(result["routes"], key=lambda r: r["duration_s"])
        self.assertEqual(result["recommended_route_id"], fastest["id"])
        self.assertIn("faster route wins", result["recommendation_reason"])
        self.assertIsNone(result["departure_advice"])

    def test_storm_on_north_route_shifts_recommendation(self):
        def rule(lat, lon, start):
            return flat_series(start, 300, wind=50 if lat > 40.3 else 5)  # severe/no-travel band up north

        result = plan_trip(request(load=20_000), three_routes, make_weather_fn(rule))
        north = next(r for r in result["routes"] if r["id"] == "A")
        self.assertGreater(north["risk"]["miles_by_level"]["severe"], 0)
        self.assertNotEqual(result["recommended_route_id"], "A")
        self.assertIn("Severe", result["recommendation_reason"])

    def test_heavy_load_turns_severe_wind_into_no_travel(self):
        storm = make_weather_fn(lambda lat, lon, start: flat_series(start, 300, wind=48))
        light = plan_trip(request(load=20_000), three_routes, storm)
        heavy = plan_trip(request(load=35_000), three_routes, storm)
        self.assertEqual(light["routes"][0]["risk"]["max_level_name"], "Severe")
        self.assertEqual(heavy["routes"][0]["risk"]["max_level_name"], "No Travel")
        self.assertTrue(any("No Travel" in w for w in heavy["warnings"]))

    def test_departure_advice_when_storm_passes(self):
        def rule(lat, lon, start):
            s = flat_series(start, 300, wind=5)
            for h in range(0, 8):  # storm for the first 8 hours, everywhere
                s.wind[h] = 60
            return s

        result = plan_trip(request(), three_routes, make_weather_fn(rule))
        advice = result["departure_advice"]
        self.assertIsNotNone(advice)
        self.assertEqual(advice["no_travel_miles"], 0)
        self.assertGreaterEqual(advice["delay_hours"], 5)

    def test_checkpoints_use_eta_hour(self):
        # Wind ramps by 10 mph every hour; later checkpoints must see stronger wind.
        def rule(lat, lon, start):
            s = flat_series(start, 300)
            s.wind = [min(70, 10 * h) for h in range(300)]
            return s

        result = plan_trip(request(interval=50), three_routes, make_weather_fn(rule))
        winds = [c["weather"]["wind_mph"] for c in result["routes"][0]["checkpoints"]]
        self.assertEqual(winds, sorted(winds))
        self.assertGreater(winds[-1], winds[0])

    def test_response_shape(self):
        calm = make_weather_fn(lambda lat, lon, start: flat_series(start, 300))
        result = plan_trip(request(), three_routes, calm)
        r = result["routes"][0]
        for key in ("id", "geometry", "checkpoints", "risk", "rank", "recommended", "arrival"):
            self.assertIn(key, r)
        self.assertEqual(sum(1 for x in result["routes"] if x["recommended"]), 1)
        self.assertTrue(result["corridor"])


class HeatmapTests(unittest.TestCase):
    def test_grid_dimensions(self):
        calm = make_weather_fn(lambda lat, lon, start: flat_series(start, 100, wind=40))
        hm = build_heatmap([[40, -100], [41, -99]], future(), 48, 45_000, calm)
        self.assertEqual(len(hm["times"]), 49)
        self.assertEqual(len(hm["intensity"]), 49)
        self.assertEqual(len(hm["intensity"][0]), 2)
        self.assertEqual(hm["levels"][0][0], int(RiskLevel.SEVERE))  # 40 mph + 45k lb


if __name__ == "__main__":
    unittest.main()
