"""API tests. Run with `python manage.py test` (external services are mocked)."""
from unittest import mock

from django.test import SimpleTestCase

from trips.clients.http import UpstreamError

from .fixtures import flat_series, future, make_weather_fn
from .test_planner import three_routes

CALM = make_weather_fn(lambda lat, lon, start: flat_series(start, 300))


class PlanApiTests(SimpleTestCase):
    def body(self, **overrides):
        data = {
            "origin": {"label": "A", "lat": 40.0, "lon": -100.0},
            "destination": {"label": "B", "lat": 40.0, "lon": -97.0},
            "departure": future().isoformat(),
            "load_lb": 35000,
            "interval_mi": 25,
        }
        data.update(overrides)
        return data

    @mock.patch("trips.views.weather.forecast_hourly", CALM)
    @mock.patch("trips.views.osrm.get_routes", three_routes)
    def test_plan_returns_three_ranked_routes(self):
        res = self.client.post("/api/plan/", self.body(), content_type="application/json")
        self.assertEqual(res.status_code, 200, res.content)
        data = res.json()
        self.assertEqual(len(data["routes"]), 3)
        self.assertEqual(sorted(r["rank"] for r in data["routes"]), [1, 2, 3])

    def test_rejects_bad_interval(self):
        res = self.client.post("/api/plan/", self.body(interval_mi=30), content_type="application/json")
        self.assertEqual(res.status_code, 400)
        self.assertIn("interval_mi", res.json())

    def test_rejects_past_departure(self):
        res = self.client.post("/api/plan/", self.body(departure="2020-01-01T00:00:00Z"), content_type="application/json")
        self.assertEqual(res.status_code, 400)

    @mock.patch("trips.views.osrm.get_routes", side_effect=UpstreamError("routing", "no route found", 422))
    def test_upstream_error_is_reported_cleanly(self, _):
        res = self.client.post("/api/plan/", self.body(), content_type="application/json")
        self.assertEqual(res.status_code, 422)
        self.assertEqual(res.json()["service"], "routing")


class HeatmapApiTests(SimpleTestCase):
    @mock.patch("trips.views.weather.forecast_hourly", CALM)
    def test_heatmap_grid(self):
        res = self.client.post(
            "/api/heatmap/",
            {"points": [[40, -100], [41, -99]], "start": future().isoformat(), "hours": 48, "load_lb": 20000},
            content_type="application/json",
        )
        self.assertEqual(res.status_code, 200, res.content)
        self.assertEqual(len(res.json()["times"]), 49)
