from copy import deepcopy
from unittest.mock import patch
from types import SimpleNamespace
from django.http import HttpResponse
from django.template.loader import render_to_string
from django.test import SimpleTestCase, RequestFactory

from core.views.polar_raw import sample_rows, translate, polar_raw_view
from core.views.polar_processing import processed_rows


def recording(speeds, rate=1):
    values = [0]
    for speed in speeds:
        values.append(values[-1] + speed * rate)
    return {"durationMillis": len(speeds) * rate * 1000,
            "samples": {"samples": [{"type": "DISTANCE", "intervalMillis": rate * 1000, "values": values}]}}


def process(exercise, interval=5):
    return processed_rows(exercise, sample_rows(exercise, interval)[0])


class PolarProcessingTests(SimpleTestCase):
    def test_thousand_five_second_blocks_remain_steady_with_measurement_spikes(self):
        speeds = [3] * 5000
        for start in range(100, 4900, 100):
            speeds[start:start + 5] = [7] * 5
        rows, _ = process(recording(speeds))
        self.assertEqual(len(rows), 1001)
        self.assertTrue(all(row["processed"] == "5:33" for row in rows[1:]))

    def test_single_distance_glitch_and_rebound_are_repaired_together(self):
        exercise = recording([3] * 60)
        exercise["samples"]["samples"][0]["values"][25] += 100
        original = deepcopy(exercise)
        rows, _ = process(exercise, 1)
        self.assertEqual(exercise, original)
        self.assertEqual(rows[25]["processed"], "5:33")
        self.assertEqual(rows[26]["processed"], "5:33")
        self.assertEqual(rows[26]["pace"], "NA")
        self.assertEqual(rows[26]["status"], "Possible measurement spike")

    def test_steady_run_removes_isolated_peak_without_mutating_raw_data(self):
        exercise = recording([3] * 20 + [7] * 5 + [3] * 35)
        original = deepcopy(exercise)
        rows, _ = process(exercise)
        self.assertEqual(exercise, original)
        peak = next(row for row in rows if row["time"] == "25")
        self.assertEqual(peak["pace"], "2:23")
        self.assertEqual(peak["processed"], "5:33")
        self.assertEqual(peak["status"], "Possible measurement spike")
        self.assertTrue(all(row["processed"] == "5:33" for row in rows[1:]))

    def test_sustained_and_short_intervals_survive(self):
        for seconds in [10, 30]:
            rows, _ = process(recording([3] * 30 + [6] * seconds + [3] * 30))
            fast = next(row for row in rows if row["time"] == "35")
            self.assertNotEqual(fast["processed"], "5:33")
            self.assertFalse(any("correction" in row["status"] or row["status"] == "Possible measurement spike" for row in rows))

    def test_progression_is_not_classified_as_measurement_error(self):
        rows, _ = process(recording([3 + index / 100 for index in range(100)]))
        self.assertTrue(all(row["status"] == "Running" for row in rows[1:]))

    def test_stop_splits_window_and_preserves_restart(self):
        rows, _ = process(recording([3] * 20 + [0] * 10 + [5] * 30))
        lookup = {row["time"]: row for row in rows}
        self.assertEqual(lookup["25"]["status"], "Possible stop")
        self.assertEqual(lookup["25"]["processed"], "NA")
        self.assertEqual(lookup["20"]["processed"], "5:33")
        self.assertEqual(lookup["35"]["processed"], "3:20")

    def test_manual_lap_boundary_prevents_smoothing_between_intervals(self):
        exercise = recording([3] * 20 + [6] * 20)
        exercise["laps"] = {"laps": [{"splitTimeMillis": 20000}]}
        rows, _ = process(exercise)
        lookup = {row["time"]: row for row in rows}
        self.assertEqual(lookup["20"]["processed"], "5:33")
        self.assertEqual(lookup["25"]["processed"], "2:47")
        self.assertLess(float(lookup["20"]["window"]), 15)

    def test_missing_and_reset_distances_are_not_bridged(self):
        exercise = recording([3] * 40)
        exercise["samples"]["samples"][0]["values"][20] = None
        rows, _ = process(exercise)
        lookup = {row["time"]: row for row in rows}
        self.assertEqual(lookup["20"]["status"], "Missing data")
        self.assertLess(float(lookup["25"]["window"]), 15)
        exercise = recording([3] * 40)
        values = exercise["samples"]["samples"][0]["values"]
        for index in range(20, len(values)):
            values[index] -= 60
        lookup = {row["time"]: row for row in process(exercise)[0]}
        self.assertEqual(lookup["20"]["processed"], "NA")
        self.assertEqual(lookup["25"]["processed"], "5:33")

    def test_explicit_pause_elapsed_and_active_clocks(self):
        for active in [False, True]:
            exercise = recording([3] * 60)
            exercise.update(startTime="2026-10-10T10:00:00", stopTime="2026-10-10T10:01:10" if active else "2026-10-10T10:01:00",
                            pauseTimes=[{"startTime": "2026-10-10T10:00:20", "endTime": "2026-10-10T10:00:30"}])
            rows, notes = process(exercise)
            lookup = {row["time"]: row for row in rows}
            if active:
                self.assertEqual(lookup["25"]["status"], "Running")
                self.assertIn("active recording time", notes[0])
                self.assertLess(float(lookup["20"]["window"]), 15)
            else:
                self.assertEqual(lookup["25"]["status"], "Polar pause")
                self.assertEqual(lookup["25"]["processed"], "NA")
                self.assertEqual(lookup["35"]["processed"], "5:33")

    def test_uncertain_pause_clock_warns_instead_of_inventing_pause(self):
        exercise = recording([3] * 60)
        exercise.update(startTime="2026-10-10T10:00:00", pauseTimes=[{"startTime": "2026-10-10T10:00:20", "endTime": "2026-10-10T10:00:30"}])
        rows, notes = process(exercise)
        self.assertIn("uncertain", notes[0])
        self.assertFalse(any(row["status"] == "Polar pause" for row in rows))

    def test_unaligned_lap_does_not_cross_native_segment(self):
        exercise = recording([3] * 20, rate=2)
        exercise["laps"] = {"laps": [{"splitTimeMillis": 19000}]}
        rows, _ = process(exercise, 2)
        lookup = {row["time"]: row for row in rows}
        self.assertEqual(lookup["20"]["status"], "Boundary")
        self.assertEqual(lookup["20"]["processed"], "NA")

    @patch("core.views.polar_raw._polar_targets_for_user")
    @patch("core.views.polar_raw._polar_json_request")
    def test_type_c_view_renders_processed_and_raw_columns(self, fetch, targets):
        user = SimpleNamespace(is_authenticated=True)
        targets.return_value = [{"key": "self", "user": user, "connection": SimpleNamespace(v4_access_token="secret"), "label": "Runner"}]
        fetch.return_value = (200, [{"exercises": [recording([3] * 20)]}])
        request = RequestFactory().post("/", {"date": "2026-10-10", "interval": "5", "mode": "C"})
        request.user, request.session = user, {}
        with patch("core.views.polar_raw.render", side_effect=lambda request, template, context: HttpResponse(render_to_string(template, context))):
            response = polar_raw_view(request)
        for text in [b"Raw min/km", b"Processed min/km", b"5:33", b"Type C"]:
            self.assertIn(text, response.content)
        self.assertNotIn(b"secret", response.content)

    def test_processing_is_opt_in_and_exercises_are_separate(self):
        payload = [{"exercises": [recording([3] * 20), recording([6] * 20)]}]
        self.assertEqual(translate(payload, 5, "B")[0]["parts"][0]["processed"], [])
        parts = translate(payload, 5, "C")[0]["parts"]
        self.assertEqual(parts[0]["processed"][1]["processed"], "5:33")
        self.assertEqual(parts[1]["processed"][1]["processed"], "2:47")
