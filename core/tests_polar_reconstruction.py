import math

from django.test import SimpleTestCase

from core.views.coach import _build_alternative_watch_suggestion


def fake_polar_activity(speeds, activity_id="fake-watch"):
    """Build a deterministic Polar-like one-second speed trace."""
    distance_m = sum(speeds) * 1000.0 / 3600.0
    return {
        "id": activity_id,
        "distance_m": distance_m,
        "duration_seconds": len(speeds),
        "raw": {
            "id": activity_id,
            "distance": distance_m,
            "duration": f"PT{len(speeds)}S",
            "samples": [{
                "sample_type": "1",
                "recording_rate": 1,
                "data": speeds,
            }],
        },
    }


def repeated_session(reps, easy_seconds, fast_seconds, easy_speed=10.0, fast_speed=16.0):
    speeds = [easy_speed] * 90
    for _index in range(reps):
        speeds.extend([fast_speed] * fast_seconds)
        speeds.extend([easy_speed] * easy_seconds)
    speeds.extend([easy_speed] * 90)
    return speeds


class PolarSyntheticReconstructionTests(SimpleTestCase):
    def reconstruct(self, speeds):
        return _build_alternative_watch_suggestion([fake_polar_activity(speeds)])

    def assert_continuous(self, speeds):
        suggestion = self.reconstruct(speeds)
        self.assertEqual(suggestion["mode"], "alternative_reconstruction")
        self.assertEqual(len(suggestion["splits"]), 1)
        self.assertEqual(suggestion["splits"][0]["label"], "Continuous block")

    def assert_pattern(self, speeds, reps):
        suggestion = self.reconstruct(speeds)
        self.assertEqual(suggestion["mode"], "alternative_pace_pattern")
        self.assertEqual(len(suggestion["splits"]), reps)
        self.assertGreaterEqual(suggestion["confidence"], 0.6)

    def test_even_endurance_run_stays_continuous(self):
        speeds = [11.5 + math.sin(index / 45) * 0.25 for index in range(3600)]
        self.assert_continuous(speeds)

    def test_progressive_run_is_not_misread_as_intervals(self):
        speeds = [9.0 + (index / 3600) * 5.0 for index in range(3600)]
        self.assert_continuous(speeds)

    def test_brief_gps_spikes_are_ignored(self):
        speeds = [11.0] * 2400
        for index in range(200, 2200, 200):
            speeds[index:index + 3] = [24.0, 25.0, 23.0]
        self.assert_continuous(speeds)

    def test_short_stops_do_not_create_fast_blocks(self):
        speeds = [12.0] * 2400
        for index in range(300, 2100, 450):
            speeds[index:index + 20] = [0.0] * 20
        self.assert_continuous(speeds)

    def test_ten_short_accelerations_are_reconstructed(self):
        self.assert_pattern(repeated_session(10, easy_seconds=110, fast_seconds=25), 10)

    def test_six_two_minute_intervals_are_reconstructed(self):
        self.assert_pattern(repeated_session(6, easy_seconds=60, fast_seconds=120), 6)

    def test_three_long_intervals_are_reconstructed(self):
        self.assert_pattern(repeated_session(3, easy_seconds=120, fast_seconds=300), 3)

    def test_consistent_hill_repeats_are_reconstructed(self):
        self.assert_pattern(
            repeated_session(8, easy_seconds=75, fast_seconds=45, easy_speed=8.5, fast_speed=13.0),
            8,
        )

    def test_irregular_fartlek_is_not_forced_into_repeating_plan(self):
        speeds = [10.0] * 90
        for fast_seconds, easy_seconds in [(15, 35), (30, 100), (95, 30), (20, 160), (180, 45)]:
            speeds.extend([16.0] * fast_seconds)
            speeds.extend([10.0] * easy_seconds)
        speeds.extend([10.0] * 90)
        self.assert_continuous(speeds)

    def test_small_natural_surges_remain_continuous(self):
        speeds = []
        for index in range(3000):
            base = 11.0 + math.sin(index / 150) * 0.7
            speeds.append(base)
        self.assert_continuous(speeds)
