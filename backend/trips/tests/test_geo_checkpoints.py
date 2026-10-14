import unittest
from datetime import timedelta

from trips.core.checkpoints import place_checkpoints
from trips.core.geo import build_polyline, haversine_mi, offset_point, overlap_ratio, thin

from .fixtures import FakeRoute, future, straight_line


class GeoTests(unittest.TestCase):
    def test_haversine_known_distance(self):
        # Chicago -> St. Louis great-circle distance is about 262 miles.
        self.assertAlmostEqual(haversine_mi((41.8781, -87.6298), (38.627, -90.1994)), 262, delta=2)

    def test_offset_point_round_trip_distance(self):
        p = offset_point((40.0, -100.0), 90, 30)
        self.assertAlmostEqual(haversine_mi((40.0, -100.0), p), 30, delta=0.05)

    def test_truck_speed_cap_slows_fast_segments(self):
        pts = straight_line((40, -100), (40, -99), n=10)
        fast = [10.0] * 10  # absurdly fast engine timing
        poly = build_polyline(pts, fast, max_speed_mph=60)
        self.assertAlmostEqual(poly.total_s / 3600, poly.total_mi / 60, places=3)

    def test_locate_interpolates_distance_and_time(self):
        route = FakeRoute(straight_line((40, -100), (40, -98)), mph=50)
        (lat, lon), secs = route.polyline.locate(route.polyline.total_mi / 2)
        self.assertAlmostEqual(lon, -99.0, places=2)
        self.assertAlmostEqual(secs, route.duration_s / 2, delta=1)

    def test_overlap_ratio_identical_and_disjoint(self):
        a = FakeRoute(straight_line((40, -100), (40, -98)), 50).polyline
        b = FakeRoute(straight_line((43, -100), (43, -98)), 50).polyline
        self.assertGreater(overlap_ratio(a, a), 0.99)
        self.assertLess(overlap_ratio(a, b), 0.05)

    def test_thin_keeps_endpoints(self):
        poly = FakeRoute(straight_line((40, -100), (41, -95), n=500), 50).polyline
        out = thin(poly, min_gap_mi=5)
        self.assertEqual(out[0][2], 0.0)
        self.assertAlmostEqual(out[-1][2], poly.total_mi, places=1)
        self.assertLess(len(out), 501)


class CheckpointTests(unittest.TestCase):
    def setUp(self):
        self.route = FakeRoute(straight_line((40, -100), (40, -97.6)), mph=50)  # ~127 miles
        self.dep = future()

    def test_spacing_and_endpoints(self):
        for interval in (10, 25, 50):
            with self.subTest(interval=interval):
                cps = place_checkpoints(self.route.polyline, self.dep, interval)
                self.assertEqual(cps[0].mile, 0)
                self.assertAlmostEqual(cps[-1].mile, self.route.polyline.total_mi, places=6)
                gaps = [b.mile - a.mile for a, b in zip(cps, cps[1:])]
                # Every gap is the interval except possibly the last, which may absorb a short remainder.
                self.assertTrue(all(abs(g - interval) < 1e-6 for g in gaps[:-1]))
                self.assertLessEqual(gaps[-1], interval * 1.2 + 1e-6)

    def test_eta_follows_travel_time(self):
        cps = place_checkpoints(self.route.polyline, self.dep, 25)
        second = cps[1]
        self.assertAlmostEqual((second.eta - self.dep).total_seconds(), 25 / 50 * 3600, delta=2)
        self.assertEqual(cps[-1].eta, self.dep + timedelta(seconds=self.route.duration_s))

    def test_no_tiny_final_leg(self):
        route = FakeRoute(straight_line((40, -100), (40, -99.06)), mph=50)  # ~50.0x miles
        cps = place_checkpoints(route.polyline, self.dep, 25)
        gaps = [b.mile - a.mile for a, b in zip(cps, cps[1:])]
        self.assertTrue(all(g >= 25 * 0.2 for g in gaps))


if __name__ == "__main__":
    unittest.main()
