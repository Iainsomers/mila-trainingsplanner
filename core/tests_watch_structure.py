from copy import deepcopy
from unittest.mock import patch

from django.test import SimpleTestCase

from core.watch_structure import short_sets_and_continuous
from core.views.polar_raw import _model_b_ai_description, type_b_description


def workout(with_cooldown=False):
    # Anonymous numeric regression cases: short GPS laps, series recoveries,
    # automatic kilometre splits followed by manual loop boundaries.
    pairs = [(82, 23, 92, 39), (92, 21, 94, 42), (95, 21, 95, 44),
             (95, 21, 94, 42), (94, 20, 91, 270), (63, 12, 80, 45),
             (96, 21, 98, 43), (96, 20, 102, 43), (96, 21, 94, 42),
             (91, 20, 100, 160)] if with_cooldown else [
             (91, 21, 91, 41), (88, 20, 97, 43), (88, 20, 99, 46),
             (83, 19, 98, 43), (91, 19, 99, 264), (84, 18, 97, 46),
             (86, 20, 99, 45), (87, 19, 98, 44), (86, 19, 96, 44),
             (89, 20, 129, 159)]
    values = [value for a, b, c, d in pairs for value in [(a, b), (c, d)]]
    values += [(1002, 296), (255, 74), (1002, 301), (273, 80), (1002, 295), (271, 76)]
    if with_cooldown:
        values += [(1001, 414), (1000, 308), (29, 12)]
    return [{"distanceMeters": m, "durationMillis": s * 1000} for m, s in values]


class ShortSetsStructureTests(SimpleTestCase):
    def test_saved_segment_times_and_processed_reps_use_their_own_laps(self):
        from types import SimpleNamespace
        from core.watch_processing import processed_main_reps
        from core.views.calendar import _watch_segment_loads, _watch_actual_time_label, _annotate_slot_segment_display_times
        for cooldown in (False, True):
            laps = workout(cooldown)
            loads = [{"segment": "CD" if index >= 26 else "CORE",
                      "meters": lap["distanceMeters"], "seconds": lap["durationMillis"] / 1000,
                      "zone": "4" if index < 20 and index % 2 == 0 else "2"}
                     for index, lap in enumerate(laps)]
            slot = SimpleNamespace(source="watch_c", watch_loads=loads)
            short = SimpleNamespace(slot=slot, type="CORE", text="2*(5*100m z4) p45",
                                    reps=10, distance_m=100, zone="4", order=1, id=1)
            continuous = SimpleNamespace(slot=slot, type="CORE", text="3750m z2",
                                         reps=1, distance_m=3750, zone="2", order=2, id=2)
            slot.segments = SimpleNamespace(all=lambda: [short, continuous])
            short_loads = _watch_segment_loads(short)
            long_loads = _watch_segment_loads(continuous)
            self.assertEqual(len(short_loads), 10)
            self.assertEqual([load["seconds"] for load in short_loads],
                             [lap["durationMillis"] / 1000 for lap in laps[:20:2]])
            self.assertEqual(len(long_loads), 1)
            self.assertEqual(long_loads[0]["seconds"], 1122)
            self.assertIn("18:42", _watch_actual_time_label(long_loads, continuous))
            self.assertNotIn("44:30", _watch_actual_time_label(long_loads, continuous))
            processed = processed_main_reps(slot)
            self.assertEqual(len(processed), 11)
            self.assertEqual([rep["distance_m"] for rep in processed], [100] * 10 + [3750])
            self.assertEqual(processed[-1]["seconds"], 1122)
            slot.watch_main_reps = []
            _annotate_slot_segment_display_times(slot, None)
            self.assertEqual(len(slot.watch_main_reps), 11)
            self.assertIn("18:42", continuous.display_text)
            if cooldown:
                self.assertIn("0:12", short.display_text)  # Keep the GPS-shortened work rep.
            self.assertEqual(slot.watch_loads, loads)

    def test_both_recording_styles_preserve_facts_and_recognize_same_main(self):
        for cooldown in (False, True):
            laps = workout(cooldown)
            before = deepcopy(laps)
            result = short_sets_and_continuous(laps, lambda lap: "Z2")
            self.assertEqual(result["main"], "2*(5*100m z2) p45//3750m z2")
            self.assertEqual(result["cd"], "2000m" if cooldown else "")
            self.assertEqual(result["cooldown_start"], 26)
            self.assertEqual(laps, before)

    def test_does_not_invent_zone_without_athlete_settings(self):
        result = short_sets_and_continuous(workout(), lambda lap: "NA")
        self.assertEqual(result["main"], "2*(5*100m) p45//3750m")

    def test_short_rep_zone_range_excludes_recoveries_and_continuous_block(self):
        laps = workout()
        for index, lap in enumerate(laps):
            lap["test_zone"] = ("Z4" if index < 8 else "Z5") if index < 20 and index % 2 == 0 else ("Z1" if index < 20 else "Z2")
        result = short_sets_and_continuous(laps, lambda lap: lap["test_zone"])
        self.assertEqual(result["main"], "2*(5*100m z4>z5) p45//3750m z2")

    def test_single_known_work_zone_and_unknown_laps(self):
        laps = workout(True)
        for index, lap in enumerate(laps):
            lap["test_zone"] = "Z4" if index in (2, 4, 6) else "NA"
        result = short_sets_and_continuous(laps, lambda lap: lap["test_zone"])
        self.assertEqual(result["main"], "2*(5*100m z4) p45//3750m")

    def test_rejects_continuous_laps_missing_recoveries_and_unequal_sets(self):
        continuous = [{"distanceMeters": 1000, "durationMillis": 300000}] * 10
        missing_recovery = workout()
        missing_recovery[1]["durationMillis"] = 20000
        unequal = workout()
        del unequal[0:2]
        for laps in (continuous, missing_recovery, unequal):
            self.assertIsNone(short_sets_and_continuous(laps, lambda lap: "Z2"))

    def test_does_not_hide_different_work_after_sets_as_cooldown(self):
        laps = workout(True)
        laps[-2]["durationMillis"] = 200000
        self.assertIsNone(short_sets_and_continuous(laps, lambda lap: "Z2"))

    @patch("core.views.polar_raw.urlopen")
    @patch("core.views.polar_raw.lap_zone_paces", return_value=("Z2", "NA"))
    def test_rules_and_ai_path_agree_without_external_ai_call(self, zones, request):
        for cooldown in (False, True):
            fixed = type_b_description(workout(cooldown))
            proposed = _model_b_ai_description(workout(cooldown))
            self.assertEqual(fixed, proposed)
            self.assertIn("Main: 2*(5*100m z2) p45//3750m z2", fixed)
        request.assert_not_called()
