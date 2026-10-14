import unittest

from trips.core.risk import (
    RiskLevel,
    Weather,
    assess,
    classify_rain,
    classify_snow,
    classify_wind,
    heat_intensity,
)

L, M, H, S, N = RiskLevel.LOW, RiskLevel.MODERATE, RiskLevel.HIGH, RiskLevel.SEVERE, RiskLevel.NO_TRAVEL


class ThresholdTests(unittest.TestCase):
    def test_wind_bands_and_boundaries(self):
        cases = [(0, L), (24.9, L), (25, M), (34.9, M), (35, H), (44.9, H), (45, S), (54.9, S), (55, N), (80, N)]
        for value, expected in cases:
            with self.subTest(wind=value):
                self.assertEqual(classify_wind(value), expected)

    def test_rain_bands_and_boundaries(self):
        cases = [(0, L), (0.09, L), (0.10, M), (0.24, M), (0.25, H), (0.49, H), (0.50, S), (1.00, S), (1.01, N)]
        for value, expected in cases:
            with self.subTest(rain=value):
                self.assertEqual(classify_rain(value), expected)

    def test_snow_bands_and_boundaries(self):
        cases = [(0, L), (0.49, L), (0.5, M), (0.99, M), (1.0, H), (1.99, H), (2.0, S), (3.0, S), (3.01, N)]
        for value, expected in cases:
            with self.subTest(snow=value):
                self.assertEqual(classify_snow(value), expected)


class LoadRuleTests(unittest.TestCase):
    def test_55_mph_is_no_travel_for_any_load(self):
        self.assertEqual(assess(Weather(wind_mph=55), load_lb=1).level, N)

    def test_45_to_54_mph_heavy_load_is_no_travel(self):
        self.assertEqual(assess(Weather(wind_mph=48), load_lb=30_001).level, N)
        self.assertEqual(assess(Weather(wind_mph=48), load_lb=30_000).level, S)  # not over 30,000

    def test_35_to_44_mph_very_heavy_load_is_severe(self):
        self.assertEqual(assess(Weather(wind_mph=40), load_lb=40_001).level, S)
        self.assertEqual(assess(Weather(wind_mph=40), load_lb=40_000).level, H)
        self.assertEqual(assess(Weather(wind_mph=40), load_lb=10_000).level, H)

    def test_load_rule_does_not_apply_below_35_mph(self):
        self.assertEqual(assess(Weather(wind_mph=34), load_lb=80_000).level, M)

    def test_load_reason_is_reported(self):
        a = assess(Weather(wind_mph=50), load_lb=35_000)
        self.assertTrue(any("30,000" in r for r in a.reasons))


class CombinedAssessmentTests(unittest.TestCase):
    def test_worst_component_wins(self):
        a = assess(Weather(wind_mph=20, rain_in_hr=0.3, snow_in_hr=0.6), load_lb=20_000)
        self.assertEqual(a.level, H)
        self.assertEqual((a.wind_level, a.rain_level, a.snow_level), (L, H, M))

    def test_calm_weather_is_low_with_no_reasons(self):
        a = assess(Weather(wind_mph=5), load_lb=20_000)
        self.assertEqual(a.level, L)
        self.assertEqual(a.reasons, [])

    def test_missing_forecast_is_low_and_flagged(self):
        a = assess(Weather(available=False), load_lb=20_000)
        self.assertEqual(a.level, L)
        self.assertIn("not available", a.reasons[0])


class HeatIntensityTests(unittest.TestCase):
    def test_intensity_is_monotonic_with_wind(self):
        values = [heat_intensity(Weather(wind_mph=w), 10_000) for w in range(0, 60, 2)]
        self.assertEqual(values, sorted(values))
        self.assertEqual(values[-1], 1.0)

    def test_intensity_matches_level_band(self):
        for w in (10, 30, 40, 50):
            lvl = int(assess(Weather(wind_mph=w), 10_000).level)
            v = heat_intensity(Weather(wind_mph=w), 10_000)
            self.assertGreaterEqual(v, lvl / 4)
            self.assertLess(v, (lvl + 1) / 4)


if __name__ == "__main__":
    unittest.main()
