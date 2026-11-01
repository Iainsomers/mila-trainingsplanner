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
    @patch("core.views.polar_raw.lap_zone_paces", return_value=("Z1", "NA"))
    def test_regular_half_kilometre_laps_form_one_run_with_split_details(self, zones):
        from types import SimpleNamespace
        from core.watch_processing import processed_main_reps
        from core.watch_structure import continuous_kilometre_run
        values = [(506.91, 163), (499.463, 164), (500.077, 164), (497.228, 169),
                  (501.802, 172), (500.362, 169), (498.847, 164), (500.225, 171),
                  (500.478, 174), (498.662, 164), (22.3851, 11)]
        laps = [{"distanceMeters": m, "durationMillis": s * 1000} for m, s in values]
        description = type_b_description(laps)
        self.assertEqual(description, "WU: none · Main: 5050 m Z1 · CD: none")
        self.assertEqual(description, _model_b_ai_description(laps))
        segment = SimpleNamespace(type="CORE", text="5050 m Z1", distance_m=5050, reps=1, order=1)
        slot = SimpleNamespace(source="watch_c", segments=SimpleNamespace(all=lambda: [segment]),
            watch_loads=[{"segment": "CORE", "zone": "1", "meters": m, "seconds": s} for m, s in values])
        result = processed_main_reps(slot)
        self.assertEqual(len(result), 1)
        self.assertEqual(len(result[0]["splits"]), 11)
        self.assertEqual(result[0]["splits"][0]["distance_m"], 500)
        self.assertEqual(result[0]["splits"][0]["seconds"], round(163 * 500 / 506.91, 2))
        self.assertEqual(result[0]["splits"][-1]["seconds"], 11)
        self.assertIsNone(result[0]["splits"][0]["average_hr_last_15"])
        slot.watch_loads[0]["average_hr_last_15"] = 122
        slot.watch_loads[-1]["average_hr_last_15"] = 141
        hr_result = processed_main_reps(slot)[0]["splits"]
        self.assertEqual(hr_result[0]["average_hr_last_15"], 122)
        self.assertEqual(hr_result[-1]["average_hr_last_15"], 141)
        for index in (1, 3, 5, 7, 9):
            laps[index]["durationMillis"] *= 2
        self.assertIsNone(continuous_kilometre_run(laps, lambda lap: "Z1"))

    def test_kilometre_splits_alone_are_a_continuous_run(self):
        from core.watch_structure import continuous_kilometre_run
        laps = [{"distanceMeters": 1000, "durationMillis": 600000 if index in (9, 18) else 260000}
                for index in range(27)]
        laps.append({"distanceMeters": 300, "durationMillis": 80000})
        self.assertEqual(continuous_kilometre_run(laps, lambda lap: "Z1"),
                         "WU: none · Main: 27300 m Z1 · CD: none")
        self.assertEqual(continuous_kilometre_run(laps, lambda lap: "NA"),
                         "WU: none · Main: 27300 m · CD: none")
        from types import SimpleNamespace
        from core.views.calendar import _watch_segment_loads, _watch_actual_time_label
        slot = SimpleNamespace(source="watch_c", watch_loads=[
            {"segment": "CORE", "zone": "1", "meters": lap["distanceMeters"],
             "seconds": lap["durationMillis"] / 1000} for lap in laps])
        segment = SimpleNamespace(slot=slot, type="CORE", text="27300 m Z1", reps=1, distance_m=27300)
        loads = _watch_segment_loads(segment)
        self.assertEqual(len(loads), 1)
        self.assertEqual(loads[0]["seconds"], sum(lap["durationMillis"] for lap in laps) / 1000)
        self.assertNotIn("-->", _watch_actual_time_label(loads, segment))
        from core.watch_processing import processed_main_reps
        slot.segments = SimpleNamespace(all=lambda: [segment])
        processed = processed_main_reps(slot)
        self.assertEqual(len(processed), 1)  # One continuous block in the calendar.
        self.assertEqual(len(processed[0]["splits"]), 28)
        self.assertEqual(processed[0]["splits"][9]["seconds"], 600)
        self.assertEqual(processed[0]["splits"][-1]["distance_m"], 300)
        self.assertEqual(processed[0]["splits"][-1]["seconds"], 80)
        slot.watch_loads[0]["meters"] = 1007.71
        updated = processed_main_reps(slot)[0]["splits"][0]
        self.assertEqual(updated["seconds"], round(260 * 1000 / 1007.71, 2))

    def test_repeated_pauses_recovery_laps_or_explicit_intervals_block_continuous_rule(self):
        from core.watch_structure import continuous_kilometre_run
        paused = [{"distanceMeters": 1000, "durationMillis": 300000, "pausedDurationMillis": 60000}] * 6
        alternating = [{"distanceMeters": 1000, "durationMillis": seconds * 1000} for seconds in (240, 480) * 4]
        short_recovery = [{"distanceMeters": meters, "durationMillis": seconds * 1000}
                          for meters, seconds in ((1000, 240), (100, 60)) * 5]
        explicit = [{"distanceMeters": 1000, "durationMillis": 300000, "lapIntensity": 5}] * 6
        for laps in (paused, alternating, short_recovery, explicit):
            self.assertIsNone(continuous_kilometre_run(laps, lambda lap: "Z1"))

    @patch("core.views.polar_raw.urlopen")
    @patch("core.views.polar_raw.lap_zone_paces", return_value=("Z1", "NA"))
    def test_ai_cannot_replace_clear_continuous_kilometres_with_reps(self, zones, request):
        laps = [{"distanceMeters": 1000, "durationMillis": 300000}] * 10
        self.assertEqual(type_b_description(laps), _model_b_ai_description(laps))
        self.assertIn("Main: 10000 m Z1", _model_b_ai_description(laps))
        request.assert_not_called()

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
                self.assertNotIn("0:12", short.display_text)
                self.assertEqual(processed[5]["measured_seconds"], 12)
                self.assertEqual(processed[5]["seconds"], round(12 * 100 / 63, 2))
            self.assertEqual(slot.watch_loads, loads)

    def test_continuous_block_uses_tail_hr_of_last_source_lap(self):
        from types import SimpleNamespace
        from core.watch_processing import processed_main_reps
        laps = workout(True)
        loads = [{"segment": "CD" if index >= 26 else "CORE", "zone": "2",
                  "meters": lap["distanceMeters"], "seconds": lap["durationMillis"] / 1000,
                  "average_hr_last_15": 110 if index == 10 else 150}
                 for index, lap in enumerate(laps)]
        loads[25]["average_hr_last_15"] = 184
        for index in range(20, 26):
            loads[index]["average_hr"] = 160 if index < 25 else 175
        loads[10]["average_hr"] = 108
        short = SimpleNamespace(type="CORE", text="2*(5*100m z2) p45", reps=10, distance_m=100, order=1)
        continuous = SimpleNamespace(type="CORE", text="3750m z2", reps=1, distance_m=3750, order=2)
        slot = SimpleNamespace(source="watch_c", watch_loads=loads,
                               segments=SimpleNamespace(all=lambda: [short, continuous]))
        result = processed_main_reps(slot)
        self.assertEqual(result[5]["average_hr_last_15"], 110)
        self.assertEqual(result[5]["average_hr"], 108)
        self.assertEqual(result[-1]["average_hr_last_15"], 184)
        expected_hr = round(sum(load["average_hr"] * load["seconds"] for load in loads[20:26]) / sum(load["seconds"] for load in loads[20:26]))
        self.assertEqual(result[-1]["average_hr"], expected_hr)
        loads[25].pop("average_hr_last_15")
        self.assertIsNone(processed_main_reps(slot)[-1]["average_hr_last_15"])
        loads[20].pop("average_hr")
        self.assertIsNone(processed_main_reps(slot)[-1]["average_hr"])

    def test_rep_time_is_scaled_using_exact_measured_distance_after_import(self):
        from types import SimpleNamespace
        from core.watch_processing import processed_main_reps
        from core.views.calendar import _watch_segment_loads, _watch_actual_time_label
        laps = workout(True)
        laps[10]["distanceMeters"] = 62.95
        loads = [{"segment": "CD" if index >= 26 else "CORE", "zone": "4",
                  "meters": lap["distanceMeters"], "seconds": lap["durationMillis"] / 1000}
                 for index, lap in enumerate(laps)]
        before = deepcopy(loads)
        slot = SimpleNamespace(source="watch_c", watch_loads=loads)
        segment = SimpleNamespace(slot=slot, type="CORE", text="2*(5*100m z4) p45",
                                  distance_m=100, reps=10, zone="4", order=1, id=1)
        slot.segments = SimpleNamespace(all=lambda: [segment])
        output = processed_main_reps(slot)
        self.assertEqual(output[5]["seconds"], 19.06)
        self.assertEqual(output[5]["measured_seconds"], 12)
        self.assertEqual(output[5]["measured_distance_m"], 62.95)
        self.assertEqual(output[0]["seconds"], round(23 * 100 / 82, 2))
        self.assertEqual(output[5]["pace_seconds_per_km"], round(12 * 1000 / 62.95, 2))
        label = _watch_actual_time_label(_watch_segment_loads(segment), segment)
        self.assertNotIn("0:12", label)
        self.assertIn("0:19", label)
        self.assertEqual(loads, before)

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
