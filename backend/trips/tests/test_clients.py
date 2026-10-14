"""Parsing of OSRM and Open-Meteo responses (HTTP mocked with realistic payloads)."""
import unittest
from datetime import datetime, timedelta, timezone
from unittest import mock

from trips.clients import geocoding, osrm, weather


def osrm_route(coords, seconds_per_seg=60.0):
    """A minimal OSRM route object in GeoJSON form."""
    geo = [[lon, lat] for lat, lon in coords]
    n = len(coords) - 1
    return {
        "geometry": {"type": "LineString", "coordinates": geo},
        "legs": [{"summary": "I 80", "annotation": {"duration": [seconds_per_seg] * n}}],
        "distance": 100000.0,
        "duration": seconds_per_seg * n,
    }


def line(a, b, n=30):
    return [(a[0] + (b[0] - a[0]) * i / n, a[1] + (b[1] - a[1]) * i / n) for i in range(n + 1)]


class OsrmTests(unittest.TestCase):
    def test_parses_route_and_caps_truck_speed(self):
        pts = line((40, -100), (40, -99))  # ~53 mi
        opt = osrm._to_option(osrm_route(pts, seconds_per_seg=1.0), "osrm")  # absurdly fast car timing
        self.assertAlmostEqual(opt.polyline.total_mi, 53, delta=1)
        self.assertAlmostEqual(opt.duration_s / 3600, opt.polyline.total_mi / osrm.TRUCK_MAX_SPEED_MPH, places=3)
        self.assertEqual(opt.summary, "I 80")

    def test_adds_distinct_detours_when_osrm_returns_one_route(self):
        main = osrm_route(line((40, -100), (40, -96)), 120)

        def fake_request(coords, alternatives):
            if len(coords) == 2:
                return [main]
            via = coords[1]
            # Detour through the via point.
            return [osrm_route(line((40, -100), via, 15) + line(via, (40, -96), 15)[1:], 120)]

        with mock.patch.object(osrm, "_request", side_effect=fake_request):
            routes = osrm.get_routes((40, -100), (40, -96))
        self.assertEqual(len(routes), 3)
        self.assertEqual(routes[0].source, "osrm")
        self.assertTrue(all(r.source == "via-point" for r in routes[1:]))
        durations = [r.duration_s for r in routes]
        self.assertEqual(durations, sorted(durations))

    def test_identical_alternatives_are_dropped(self):
        same = osrm_route(line((40, -100), (40, -96)), 120)
        with mock.patch.object(osrm, "_request", return_value=[same]):
            routes = osrm.get_routes((40, -100), (40, -96))
        # Detours are the same line too, so only one distinct route survives.
        self.assertEqual(len(routes), 1)


class WeatherTests(unittest.TestCase):
    def payload(self, start, hours, wind_unit="mp/h", rain_unit="inch", snow_unit="inch", wind=10.0):
        times = [(start + timedelta(hours=h)).strftime("%Y-%m-%dT%H:%M") for h in range(hours)]
        return {
            "hourly_units": {"wind_speed_10m": wind_unit, "wind_gusts_10m": wind_unit, "rain": rain_unit, "snowfall": snow_unit},
            "hourly": {
                "time": times,
                "wind_speed_10m": [wind + h for h in range(hours)],
                "wind_gusts_10m": [wind + 10 + h for h in range(hours)],
                "rain": [0.0] * hours,
                "snowfall": [2.54] * hours,
                "temperature_2m": [30.0] * hours,
                "weather_code": [71] * hours,
            },
        }

    def test_picks_hour_nearest_eta(self):
        start = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
        series = weather._parse(self.payload(start, 24))
        w = series.at(start + timedelta(hours=5, minutes=40))  # nearest is +6 h
        self.assertEqual(w.wind_mph, 16.0)

    def test_converts_metric_units(self):
        start = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
        series = weather._parse(self.payload(start, 3, wind_unit="km/h", snow_unit="cm", wind=100.0))
        w = series.at(start)
        self.assertAlmostEqual(w.wind_mph, 62.14, places=1)
        self.assertAlmostEqual(w.snow_in_hr, 1.0, places=3)

    def test_outside_window_is_unavailable(self):
        start = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
        series = weather._parse(self.payload(start, 3))
        self.assertFalse(series.at(start + timedelta(hours=10)).available)

    def test_batches_locations(self):
        start = datetime.now(timezone.utc) + timedelta(hours=1)
        calls = []

        def fake_get_json(service, url, params):
            n = len(params["latitude"].split(","))
            calls.append(n)
            item = self.payload(start.replace(minute=0, second=0, microsecond=0), 30)
            return [item] * n if n > 1 else item

        coords = [(40 + i * 0.1, -100.0) for i in range(120)]
        with mock.patch.object(weather, "get_json", side_effect=fake_get_json):
            out = weather.forecast_hourly(coords, start, start + timedelta(hours=10))
        self.assertEqual(len(out), 120)
        self.assertEqual(sorted(calls), [20, 50, 50])


class GeocodingTests(unittest.TestCase):
    def test_raw_coordinates_skip_network(self):
        with mock.patch.object(geocoding, "get_json") as gj:
            res = geocoding.search("41.88, -87.63")
        gj.assert_not_called()
        self.assertAlmostEqual(res[0].lat, 41.88)

    def test_photon_labels(self):
        data = {"features": [{"geometry": {"coordinates": [-87.62, 41.88]}, "properties": {"name": "Chicago", "state": "Illinois", "country": "United States"}}]}
        with mock.patch.object(geocoding, "get_json", return_value=data):
            res = geocoding.search("chicago")
        self.assertEqual(res[0].label, "Chicago, Illinois, United States")


if __name__ == "__main__":
    unittest.main()
