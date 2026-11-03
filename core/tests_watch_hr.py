from django.test import SimpleTestCase

from core.watch_hr import lap_hr_load, tail_hr


class WatchEndHrTests(SimpleTestCase):
    def load(self, seconds, change, before=140, after=180):
        return {'seconds': seconds, 'average_hr': 150,
                'hr_samples': [[t, before if t < change else after] for t in range(seconds)]}

    def test_last_ten_percent_instead_of_last_fifteen(self):
        self.assertEqual(tail_hr([self.load(300, 285)]), 160)

    def test_minimum_fifteen_seconds_and_short_rep_average(self):
        self.assertEqual(tail_hr([self.load(100, 90)]), 167)
        self.assertEqual(tail_hr([self.load(12, 0)]), 150)
        self.assertEqual(tail_hr([{'seconds': 12, 'average_hr': 123}]), 123)

    def test_complete_rep_window_spans_lap_boundaries(self):
        loads = [self.load(200, 200), self.load(270, 270), self.load(10, 0)]
        self.assertEqual(tail_hr(loads), 148)  # 38s at 140 + 10s at 180

    def test_missing_samples_do_not_invent_long_window(self):
        self.assertIsNone(tail_hr([{'seconds': 300, 'average_hr_last_15': 180}]))
        self.assertEqual(tail_hr([{'seconds': 100, 'average_hr_last_15': 180}]), 180)

    def test_lap_samples_keep_measured_offsets(self):
        lap = {'heartRateSamples': [{'timeMillis': t*1000, 'heartRate': 160} for t in range(100, 400)]}
        load = lap_hr_load(lap, 100000, 400000, None, 150)
        self.assertEqual(load['hr_samples'][0], [0, 160])
        self.assertEqual(load['hr_tail'], 160)
