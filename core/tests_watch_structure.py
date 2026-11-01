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
    def test_both_recording_styles_preserve_facts_and_recognize_same_main(self):
        for cooldown in (False, True):
            laps = workout(cooldown)
            before = deepcopy(laps)
            result = short_sets_and_continuous(laps, lambda lap: "Z2")
            self.assertEqual(result["main"], "2*(5*100m) p45//3750m z2")
            self.assertEqual(result["cd"], "2000m" if cooldown else "")
            self.assertEqual(result["cooldown_start"], 26)
            self.assertEqual(laps, before)

    def test_does_not_invent_zone_without_athlete_settings(self):
        result = short_sets_and_continuous(workout(), lambda lap: "NA")
        self.assertTrue(result["main"].endswith("//3750m"))

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
            self.assertIn("Main: 2*(5*100m) p45//3750m z2", fixed)
        request.assert_not_called()
