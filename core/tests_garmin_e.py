from copy import deepcopy
from datetime import datetime, timezone
import json
from types import SimpleNamespace
from unittest.mock import patch, MagicMock
from urllib.parse import urlencode

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from core.garmin_e import (
    apply_explicit_zone_labels,
    ask_model,
    checked_proposal,
    complete_partial_running_proposal,
    explicit_alternative_compact_proposal,
    explicit_distance_sets,
    lap_facts,
    prefer_measured_time_groups,
)
from core.models import Athlete, GarminActivitySummary
from core.parser import parse_segment_text
from core.views.garmin import CONSENT_VERSION
from core.watch_processing import processed_main_reps
from core.views.calendar import _virtual_segment_from_text


def fixture():
    values = [(1200,360),(205,38),(95,43),(101,19),(55,43),
              (204,37),(97,42),(99,19),(19,9)]
    part = dict(training_fields={"wu":"1200 m Z1","main":"old","cd":""},
        watch_loads=[dict(segment="CORE",meters=m,seconds=s,zone="4" if i in (1,3,5,7) else "1",
                         average_hr=132,average_hr_last_15=140) for i,(m,s) in enumerate(values)])
    proposal = dict(warmup_laps=[1],cooldown_laps=[],recovery_laps=[3,5,7,9],
        reps=[dict(laps=[i],target_meters=m) for i,m in ((2,200),(4,100),(6,200),(8,100))])
    return part,proposal


class GarminEValidationTests(SimpleTestCase):
    def test_watch_clock_keeps_all_e_reps_in_mixed_sets(self):
        distances = [1800, 1300, 800] * 2 + [800, 800]
        loads = [{"segment": "CORE", "work_rep": True, "ai_rep": i,
                  "ai_nominal_m": distance, "meters": distance + 10, "seconds": distance / 4}
                 for i, distance in enumerate(distances, 1)]
        loads.insert(1, {"segment": "CORE", "work_rep": False, "meters": 200, "seconds": 120})
        rows = processed_main_reps(SimpleNamespace(source="watch_e", watch_loads=loads))
        self.assertEqual([row["distance_m"] for row in rows], distances)
        self.assertEqual([row["rep"] for row in rows], list(range(1, 9)))

    def test_explicit_mixed_sets_split_equal_distance_tail(self):
        distances = [120, 1800, 1300, 800, 1500, 1300, 800, 800, 800]
        loads = [{"meters": distance, "seconds": distance / 4, "zone": "2", "segment": "CORE"}
                 for distance in distances]
        proposal = {"reps": [{"laps": [i], "target_meters": distance}
                             for i, distance in enumerate(distances, 1)]}
        updated = explicit_distance_sets(proposal, "maak er 3 sets van 1*(1800m-1300m-800m)//1*(1500m-1300m-800m)//2*800m")
        checked = checked_proposal({"watch_loads": loads}, updated, zone_basis="pace")
        main = checked["training_fields"]["main"]
        self.assertEqual(main, "120 m Z2 // 1×(1800 m Z2 - 1300 m Z2 - 800 m Z2) // 1×(1500 m Z2 - 1300 m Z2 - 800 m Z2) // 2×800 m Z2")
        self.assertTrue(parse_segment_text(main).ok)

    def test_retarget_short_reps_in_mixed_main(self):
        proposal = {"reps": [{"laps": [lap], "target_meters": 50} for lap in (3, 5, 7, 9)]
                    + [{"laps": [11], "target_meters": 1500}], "recovery_laps": [4, 6, 8, 10]}
        for message in ("de 4*50m is 4*70m in z6", "lap 3-5-7-9 zijn 4*70m z6"):
            with self.subTest(message=message):
                updated, changed = apply_explicit_zone_labels(proposal, message)
                self.assertTrue(changed)
                self.assertEqual([rep["target_meters"] for rep in updated["reps"]], [70]*4 + [1500])
                self.assertEqual(updated["explicit_lap_zones"], dict.fromkeys(("3", "5", "7", "9"), "6"))
                self.assertEqual(updated["recovery_laps"], proposal["recovery_laps"])

    def test_general_explicit_alternative_compact_notation_is_measured_and_checked(self):
        athlete = SimpleNamespace(zone_hr_bpm={"1":"200"}, alternative_hr_correction=10)
        examples = [
            ([600, 45, 30, 45, 30, 45, 300],
             'WU-2*(45" Z2-30" Z1)-45" Z2-CD',
             "Elliptical 10' Z1 // Elliptical 2×(45s Z2 - 30s Z1) // Elliptical 45s Z2 // Elliptical 5' Z1"),
            ([300, 120, 60, 120, 60, 120, 60, 240, 180],
             "warmup / 3×(2 min Z3 / 1 min Z1) / 4 min Z2 / cooldown",
             "Elliptical 5' Z1 // Elliptical 3×(2' Z3 - 1' Z1) // Elliptical 4' Z2 // Elliptical 3' Z1"),
        ]
        for durations, notation, expected in examples:
            with self.subTest(notation=notation):
                part = {"training_fields": {"alt": "Elliptical"}, "alternative_label": "Elliptical",
                        "alternative_laps": [{"seconds": value, "average_hr": 100, "end_hr": 100}
                                             for value in durations]}
                proposal = explicit_alternative_compact_proposal(lap_facts(part), notation)
                self.assertIsNotNone(proposal)
                checked = checked_proposal(part, proposal, athlete=athlete, zone_basis="hr")
                self.assertEqual(checked["training_fields"]["alt"], expected)
                self.assertEqual(sum(load["seconds"] for load in checked["watch_loads"]), sum(durations))

                changed = deepcopy(durations)
                changed[2] += 10
                facts = lap_facts({**part, "alternative_laps": [
                    {"seconds": value, "average_hr": 100, "end_hr": 100} for value in changed
                ]})
                self.assertIsNone(explicit_alternative_compact_proposal(facts, notation))

    def test_explicit_alternative_duration_zones_override_summary_without_changing_laps(self):
        athlete = SimpleNamespace(zone_hr_bpm={"1":"145","2":"146-160"}, alternative_hr_correction=10)
        durations = [600, 45, 30, 45, 30, 45, 300]
        part = {
            "training_fields": {"alt": "Elliptical 18' Z1"},
            "alternative_label": "Elliptical",
            "alternative_laps": [
                {"seconds": seconds, "average_hr": 110, "end_hr": 110}
                for seconds in durations
            ],
        }
        proposal = {
            "warmup_laps": [1], "cooldown_laps": [7], "recovery_laps": [3, 5],
            "ignored_laps": [],
            "reps": [{"laps": [lap], "target_seconds": 45} for lap in (2, 4, 6)],
            "format": "compact",
            "presentation": {"warmup_seconds": 600, "cooldown_seconds": 300,
                             "work_zone": "1", "recovery_zone": "2"},
        }
        proposal, changed = apply_explicit_zone_labels(proposal, '45"=z1 en 30 seconden: z2')
        self.assertTrue(changed)
        self.assertEqual(proposal["explicit_duration_zones"], {"45": "1", "30": "2"})
        self.assertEqual(proposal["warmup_laps"], [1])
        checked = checked_proposal(part, proposal, athlete=athlete, zone_basis="hr")
        self.assertEqual(
            checked["training_fields"]["alt"],
            "Elliptical 10' Z1 // Elliptical 2×(45s Z1 - 30s Z2) // "
            "Elliptical 45s Z1 // Elliptical 5' Z1",
        )
        measured = [lap for load in checked["watch_loads"] for lap in load["alt_laps"]]
        self.assertEqual(len(measured), 7)
        self.assertEqual(sum(lap["seconds"] for lap in measured), sum(durations))
        self.assertEqual(measured[1]["zone_source"], "user")
        self.assertEqual(measured[2]["zone"], "2")

    def test_progressive_work_and_high_zone_recovery_remain_one_rep_series(self):
        loads = [{"segment":"CORE", "meters":1200, "seconds":360, "zone":"1"}]
        reps, recovery = [], []
        for index, seconds in enumerate((240, 235, 230, 225)):
            reps.append({"laps":[len(loads)+1], "target_meters":1000})
            loads.append({"segment":"CORE", "meters":1000, "seconds":seconds, "zone":str(index+1)})
            if index < 3:
                recovery.append(len(loads)+1)
                loads.append({"segment":"CORE", "meters":200, "seconds":75, "zone":"3"})
        proposal = {"warmup_laps":[1], "reps":reps, "recovery_laps":recovery}
        result = checked_proposal({"watch_loads":loads}, proposal, zone_basis="pace")
        self.assertIn("4×1000 m", result["training_fields"]["main"])
        self.assertEqual(sum(load["work_rep"] for load in result["watch_loads"]), 4)
        self.assertEqual([(load["meters"], load["seconds"], load["zone"]) for load in result["watch_loads"]],
                         [(load["meters"], load["seconds"], load["zone"]) for load in loads])
        # Alternation alone is insufficient: recovery nearly as fast as work
        # must still be rejected, even if its absolute zone says Z1.
        invalid = deepcopy(loads)
        invalid[2].update(seconds=50, zone="1")
        with self.assertRaisesRegex(ValueError, "not clearly slower"):
            checked_proposal({"watch_loads":invalid}, proposal, zone_basis="pace")

    def test_long_walking_boundary_is_rest_without_blocking_proposal(self):
        part, proposal = fixture()
        part["watch_loads"].append(dict(segment="CORE", meters=1361.94, seconds=1747.75, zone="1"))
        proposal["cooldown_laps"] = [10]
        result = checked_proposal(part, proposal, zone_basis="pace")
        self.assertEqual(result["training_fields"]["cd"], "")
        self.assertEqual(result["watch_loads"][-1]["segment"], "CORE")
        self.assertFalse(result["watch_loads"][-1]["work_rep"])
        self.assertEqual(result["watch_loads"][-1]["seconds"], 1747.75)

    def test_unassigned_standing_lap_is_rest(self):
        part, proposal = fixture()
        part["watch_loads"].append(dict(segment="CORE", meters=0, seconds=90, zone="1"))
        result = checked_proposal(part, proposal, zone_basis="pace")
        self.assertFalse(result["watch_loads"][-1]["work_rep"])

    def test_explicit_lap_zone_allows_corrected_cooldown(self):
        part, proposal = fixture()
        part["watch_loads"].append(dict(segment="CORE", meters=1000, seconds=190, zone="5"))
        proposal["cooldown_laps"] = [10]
        with self.assertRaisesRegex(ValueError, "Lap 10 is not supported"):
            checked_proposal(part, proposal, zone_basis="pace")
        updated, changed = apply_explicit_zone_labels(proposal, "maak van lap 10 een z1 en dan valt hij in de cd")
        self.assertTrue(changed)
        checked = checked_proposal(part, updated, zone_basis="pace")
        self.assertEqual(checked["watch_loads"][-1]["zone"], "1")
        self.assertEqual(checked["watch_loads"][-1]["segment"], "CD")
        self.assertEqual(checked["watch_loads"][-1]["seconds"], 190)

    def test_explicit_warmup_zone_is_taken_from_user_message(self):
        proposal = {"warmup_laps":[1], "reps":[{"laps":[2], "target_seconds":360}]}
        updated, changed = apply_explicit_zone_labels(proposal, "je moet die 1e 20' wel z1 noemen")
        self.assertTrue(changed)
        self.assertEqual(updated["explicit_role_zones"], {"Warmup":"1"})
        self.assertNotIn("explicit_role_zones", proposal)

    def test_explicit_user_zone_ranges_update_checked_preview_labels(self):
        loads = [
            {"meters":1000, "seconds":320, "zone":"1", "segment":"CORE"},
            {"meters":1000, "seconds":315, "zone":"1", "segment":"CORE"},
            {"meters":900, "seconds":700, "zone":"1", "segment":"CORE"},
        ]
        reps, recovery = [], []
        for index in range(6):
            reps.append({"laps":[len(loads) + 1], "target_meters":250})
            loads.append({"meters":250, "seconds":55 - index, "zone":"3", "segment":"CORE"})
            recovery.append(len(loads) + 1)
            loads.append({"meters":50, "seconds":60, "zone":"1", "segment":"CORE"})
        reps.append({"laps":[len(loads) + 1], "target_meters":800})
        loads.append({"meters":800, "seconds":250, "zone":"2", "segment":"CORE"})
        reps.append({"laps":[len(loads) + 1], "target_meters":1300})
        loads.append({"meters":1300, "seconds":360, "zone":"3", "segment":"CORE"})
        loads.append({"meters":1200, "seconds":420, "zone":"1", "segment":"CORE"})
        proposal = {
            "warmup_laps":[1, 2], "ignored_laps":[3], "recovery_laps":recovery,
            "cooldown_laps":[len(loads)], "reps":reps,
        }

        updated, changed = apply_explicit_zone_labels(
            proposal, "Die 6*250m was Z3>Z5, die 800m was Z1-Z3",
        )
        checked = checked_proposal({"watch_loads":loads}, updated, zone_basis="pace")

        self.assertTrue(changed)
        self.assertIn("6×250 m Z3>Z5", checked["training_fields"]["main"])
        self.assertIn("800 m Z1>Z3", checked["training_fields"]["main"])
        self.assertIn("Explicit zone ranges stated by the user", checked["e_zone_note"])
        self.assertEqual([load["zone"] for load in checked["watch_loads"]],
                         [load["zone"] for load in loads])

    def test_explicit_short_sprint_sequence_can_raise_mixed_reps_to_z6(self):
        loads = [{"meters":1000, "seconds":300, "zone":"1", "segment":"WU"}]
        reps, recovery = [], []
        for index, meters in enumerate((60, 70, 80, 70, 60)):
            lap = len(loads) + 1
            loads.append({
                "meters": meters, "seconds": 10 + index % 2,
                "zone": "6" if index in {1, 3} else "4", "segment": "CORE",
            })
            reps.append({"laps":[lap], "target_meters":meters})
            if index < 4:
                recovery.append(len(loads) + 1)
                loads.append({"meters":100, "seconds":60, "zone":"1", "segment":"CORE"})
        loads.append({"meters":800, "seconds":300, "zone":"1", "segment":"CD"})
        proposal = {
            "warmup_laps":[1], "recovery_laps":recovery,
            "cooldown_laps":[len(loads)], "reps":reps,
        }

        updated, changed = apply_explicit_zone_labels(
            proposal, "maak er 1*(60m//70m//80m//70m//60m) z6 van",
        )
        checked = checked_proposal({"watch_loads":loads}, updated, zone_basis="pace")

        self.assertTrue(changed)
        self.assertEqual(updated["explicit_lap_zones"], {
            str(rep["laps"][0]): "6" for rep in reps
        })
        self.assertTrue(all(
            checked["watch_loads"][rep["laps"][0] - 1]["zone"] == "6" for rep in reps
        ))
        self.assertEqual(checked["training_fields"]["main"], "1×(60 m // 70 m // 80 m // 70 m // 60 m) Z6")
        self.assertEqual(checked["watch_loads"][recovery[0] - 1]["segment"], "CORE")
        self.assertFalse(checked["watch_loads"][recovery[0] - 1]["work_rep"])
        hyphenated, hyphenated_changed = apply_explicit_zone_labels(
            proposal, "maak er 1*(60m-70m-80m-70m-60m) z6 van",
        )
        self.assertTrue(hyphenated_changed)
        self.assertEqual(hyphenated["explicit_sprint_sequences"], updated["explicit_sprint_sequences"])

        from core.parser import parse_segment_text
        parsed = parse_segment_text(checked["training_fields"]["main"])
        self.assertTrue(parsed.ok, parsed.message)
        self.assertEqual(parsed.distance_m, 340)

    def test_explicit_short_repeated_group_can_raise_partly_correct_reps_to_z6(self):
        proposal = {
            "reps":[
                {"laps":[1], "target_meters":60},
                {"laps":[2], "target_meters":60},
                {"laps":[3], "target_meters":60},
            ],
        }

        updated, changed = apply_explicit_zone_labels(proposal, "maak de 3x60m z6")

        self.assertTrue(changed)
        self.assertEqual(updated["explicit_lap_zones"], {"1":"6", "2":"6", "3":"6"})
        self.assertEqual(updated["zone_labels"], [])

    def test_follow_up_can_raise_entire_checked_short_set_to_z6(self):
        loads = []
        reps = []
        recovery = []
        for index in range(16):
            work_lap = len(loads) + 1
            loads.append({
                "meters": 85,
                "seconds": 14,
                "zone": "3" if index in {0, 6} else "4",
                "segment": "CORE",
            })
            reps.append({"laps": [work_lap], "target_meters": 85})
            if index < 15:
                recovery.append(len(loads) + 1)
                loads.append({
                    "meters": 135,
                    "seconds": 283 if index == 7 else 42,
                    "zone": "1",
                    "segment": "CORE",
                })
        proposal = {
            "recovery_laps": recovery,
            "set_start_laps": [1, 17],
            "reps": reps,
            "zone_labels": [{"target_meters": 85, "count": 16, "label": "Z3>Z4"}],
        }

        updated, changed = apply_explicit_zone_labels(
            proposal, "maak er z6 van ipv z3>z4",
        )
        checked = checked_proposal({"watch_loads": loads}, updated, zone_basis="pace")

        self.assertTrue(changed)
        self.assertEqual(updated["zone_labels"], [])
        self.assertEqual(
            updated["explicit_lap_zones"],
            {str(rep["laps"][0]): "6" for rep in reps},
        )
        self.assertEqual(
            checked["training_fields"]["main"],
            "2×(8×85 m Z6 p42) sp283",
        )
        self.assertTrue(all(
            checked["watch_loads"][rep["laps"][0] - 1]["zone"] == "6"
            for rep in reps
        ))
        self.assertTrue(all(
            not checked["watch_loads"][lap - 1]["work_rep"]
            for lap in recovery
        ))

    def test_follow_up_can_set_all_timed_work_blocks_to_z2(self):
        loads = [
            {"meters": 1000, "seconds": 301, "zone": "1", "segment": "WU"},
            {"meters": 1000, "seconds": 290, "zone": "1", "segment": "WU"},
            {"meters": 43, "seconds": 14, "zone": "1", "segment": "WU"},
        ]
        reps = []
        recovery = []
        for index in range(12):
            work_lap = len(loads) + 1
            loads.append({
                "meters": 620,
                "seconds": 120,
                "zone": "2" if index in {0, 4, 8, 10, 11} else "3",
                "segment": "CORE",
            })
            reps.append({"laps": [work_lap], "target_seconds": 120})
            if index < 11:
                recovery_lap = len(loads) + 1
                recovery.append(recovery_lap)
                loads.append({
                    "meters": 60 if index == 7 else 330,
                    "seconds": 215 if index == 7 else 90,
                    "zone": "1",
                    "segment": "CORE",
                })
        recovery.append(len(loads) + 1)
        loads.append({"meters": 74, "seconds": 140, "zone": "1", "segment": "CORE"})
        loads.append({"meters": 935, "seconds": 301, "zone": "1", "segment": "CD"})
        proposal = {
            "warmup_laps": [1, 2, 3],
            "cooldown_laps": [len(loads)],
            "recovery_laps": recovery,
            "reps": reps,
            "zone_labels": [{"target_seconds": 120, "count": 12, "label": "Z1>Z2"}],
        }

        updated, changed = apply_explicit_zone_labels(
            proposal, "maak van de werkblokken z2",
        )
        checked = checked_proposal({"watch_loads": loads}, updated, zone_basis="pace")

        self.assertTrue(changed)
        self.assertEqual(updated["zone_labels"], [])
        self.assertEqual(
            updated["explicit_lap_zones"],
            {str(rep["laps"][0]): "2" for rep in reps},
        )
        self.assertEqual(checked["training_fields"]["main"], "12×2' Z2 p90")
        self.assertTrue(all(
            checked["watch_loads"][rep["laps"][0] - 1]["zone"] == "2"
            for rep in reps
        ))
        self.assertTrue(all(
            checked["watch_loads"][lap - 1]["zone"] == "1"
            for lap in [1, 2, 3, *recovery, len(loads)]
        ))

    def test_equal_three_minute_reps_override_variable_distance_targets(self):
        work_distances = [746.9, 767.8, 775.67, 783.19, 763.08, 753.62, 765.641, 786.32]
        loads = [{"meters":1783.44, "seconds":572, "zone":"1", "segment":"WU"}]
        reps = []
        for position, meters in enumerate(work_distances):
            lap_id = len(loads) + 1
            loads.append({"meters":meters, "seconds":180, "zone":"2", "segment":"CORE"})
            reps.append({"laps":[lap_id], "target_meters":750 if position % 2 == 0 else 800})
            if position < len(work_distances) - 1:
                loads.append({"meters":195, "seconds":75, "zone":"1", "segment":"CORE"})
        part = {"training_fields":{"wu":"1800 m Z1", "main":"Measured", "cd":""}, "watch_loads":loads}
        proposal = {"warmup_laps":[1], "recovery_laps":list(range(3, 17, 2)), "reps":reps}

        adjusted, changed = prefer_measured_time_groups(part, proposal)
        checked = checked_proposal(part, adjusted, zone_basis="pace")

        self.assertTrue(changed)
        self.assertTrue(all(rep.get("target_seconds") == 180 for rep in adjusted["reps"]))
        self.assertTrue(all("target_meters" not in rep for rep in adjusted["reps"]))
        self.assertIn("8×3' Z2 p75", checked["training_fields"]["main"])
        self.assertTrue(all("target_meters" in rep for rep in proposal["reps"]))

    def test_explicitly_ignored_transition_laps_do_not_need_recovery_speed(self):
        measurements = [
            (1004.47, 285), (1000.42, 291), (1001.09, 285), (5.24658, 3),
            (52.21, 12), (76.1702, 16), (343.36, 279), (105.47, 85),
            (69.3401, 13), (111.98, 85), (67.1499, 13), (130.28, 151),
            (131.62, 27), (143.51, 128), (120.26, 21), (153.12, 326),
            (1717.95, 391), (35.2598, 134), (856.49, 184), (381.05, 182),
            (1729.08, 379), (56.0508, 125), (832.21, 177), (45.1494, 208),
            (821.971, 174), (51.9395, 150), (845.88, 166), (33.2002, 195),
            (824.78, 156), (74.8594, 228), (3020.12, 977),
        ]
        zones = ["1", "1", "1", "1", "2", "3", "1", "1", "4", "1", "4", "1", "3", "1", "5", "1",
                 "2", "1", "3", "1", "2", "1", "3", "1", "3", "1", "4", "1", "4", "1", "1"]
        part = {
            "training_fields":{"wu":"", "main":"Measured", "cd":""},
            "watch_loads":[
                {"meters":meters, "seconds":seconds, "zone":zone, "segment":"CORE"}
                for (meters, seconds), zone in zip(measurements, zones)
            ],
        }
        proposal = {
            "warmup_laps":[1, 2, 3],
            "ignored_laps":list(range(4, 17)),
            "recovery_laps":[18, 20, 22, 24, 26, 28, 30],
            "cooldown_laps":[31],
            "reps":[
                {"laps":[lap], "target_meters":target}
                for lap, target in ((17, 1750), (19, 850), (21, 1750), (23, 850),
                                    (25, 850), (27, 850), (29, 850))
            ],
        }

        checked = checked_proposal(part, proposal, zone_basis="pace")

        self.assertTrue(checked["e_usable"])
        self.assertEqual(checked["training_fields"]["wu"], "3000 m Z1")
        self.assertIn("2×(1750 m Z2 - 850 m Z3)", checked["training_fields"]["main"])
        self.assertIn("3×850 m Z3>Z4", checked["training_fields"]["main"])
        self.assertNotIn("4×850", checked["training_fields"]["main"])
        self.assertEqual(checked["watch_loads"][4]["segment"], "IGNORE")
        self.assertFalse(checked["watch_loads"][4]["work_rep"])
        from core.stats import _watch_loads_for_slot
        counted = _watch_loads_for_slot(SimpleNamespace(source="watch_e", watch_loads=checked["watch_loads"]))
        self.assertNotIn(52.21, [load["meters"] for load in counted])

    def test_partial_warmup_correction_preserves_measured_preview_work_reps(self):
        measurements = [
            (1004.47, 285), (1000.42, 291), (1001.09, 285), (5.24658, 3),
            (52.21, 12), (76.1702, 16), (343.36, 279), (105.47, 85),
            (69.3401, 13), (111.98, 85), (67.1499, 13), (130.28, 151),
            (131.62, 27), (143.51, 128), (120.26, 21), (153.12, 326),
            (1717.95, 391), (35.2598, 134), (856.49, 184), (381.05, 182),
            (1729.08, 379), (56.0508, 125), (832.21, 177), (45.1494, 208),
            (821.971, 174), (51.9395, 150), (845.88, 166), (33.2002, 195),
            (824.78, 156), (74.8594, 228), (3020.12, 977),
        ]
        work_laps = {1:1000, 2:1000, 3:1000, 17:1700, 19:850, 21:1750,
                     23:850, 25:800, 27:850, 29:800, 31:3000}
        loads = []
        for index, (meters, seconds) in enumerate(measurements, 1):
            load = {"meters":meters, "seconds":seconds, "zone":"1", "segment":"CORE",
                    "work_rep":index in work_laps}
            if index in work_laps:
                load["nominal_rep_m"] = work_laps[index]
            loads.append(load)
        part = {"training_fields":{"wu":"", "main":"Measured", "cd":""}, "watch_loads":loads}

        completed = complete_partial_running_proposal(
            part, {"warmup_laps":[1, 2, 3], "cooldown_laps":[], "recovery_laps":[]},
        )

        self.assertEqual(completed["warmup_laps"], [1, 2, 3])
        self.assertEqual([rep["laps"] for rep in completed["reps"]],
                         [[5], [6], [9], [11], [13], [15], [17], [19], [21], [23], [25], [27], [29], [31]])
        self.assertIn(4, completed["recovery_laps"])
        checked = checked_proposal(part, completed, zone_basis="pace")
        self.assertEqual(checked["training_fields"]["wu"], "3000 m Z1")
        self.assertNotIn("3×1000", checked["training_fields"]["main"])
        self.assertTrue(checked["e_usable"])
    def test_compact_alternative_notation_preserves_measured_zone_times(self):
        from core.watch_alternative import alternative_part
        from core.alternative import expand_time_notation
        athlete = SimpleNamespace(zone_hr_bpm={"1":"157","2":"158-175"},alternative_hr_correction=10)
        seconds = [930,604,300,601,300,601,323,601,307,388]
        hrs = [111,146,113,148,104,152,108,156,109,155]
        part = alternative_part(athlete,{"sport":"ELLIPTICAL","average_hr":132},sum(seconds),
            [dict(elapsed_time=s,avg_heart_rate=hr,hr_tail=hr) for s,hr in zip(seconds,hrs)])
        proposal = dict(warmup_laps=[1],recovery_laps=[3,5,7,9],reps=[
            dict(laps=[i],target_seconds=target) for i,target in ((2,600),(4,600),(6,600),(8,600),(10,388))],
            format="compact",presentation=dict(warmup_seconds=900,recovery_seconds=300,work_zone="2",recovery_zone="1"))
        checked = checked_proposal(part,proposal,athlete=athlete,zone_basis="hr")
        text = checked["training_fields"]["alt"]
        self.assertEqual(text,"Elliptical 15' Z1 // Elliptical 4×(10' Z2 - 5' Z1) // Elliptical 6'28 Z2")
        self.assertEqual(sum(s for _,s in expand_time_notation(text)),4888)
        self.assertEqual(sum(lap["seconds"] for load in checked["watch_loads"] for lap in load["alt_laps"]),4955)
        self.assertEqual(checked["watch_loads"][1]["alt_laps"][0]["zone"],"1")
        bad = deepcopy(proposal)
        bad["presentation"]["work_zone"] = "5"
        with self.assertRaises(ValueError):
            checked_proposal(part,bad,athlete=athlete)
        bad = deepcopy(proposal)
        bad["presentation"]["recovery_seconds"] = 60
        with self.assertRaises(ValueError):
            checked_proposal(part,bad,athlete=athlete)

    def test_compact_descending_alternative_sequence_uses_one_main_summary(self):
        from core.watch_alternative import alternative_part
        from core.alternative import parse_alternative_text
        athlete = SimpleNamespace(
            zone_hr_bpm={"1":"120", "2":"121-155", "3":"156-175"},
            alternative_hr_correction=0,
        )
        work_seconds = [720, 600, 480, 360, 300, 240, 180, 120, 60]
        work_hr = [140, 145, 150, 152, 158, 160, 162, 164, 155]
        seconds, hrs = [900], [100]
        for index, (duration, hr) in enumerate(zip(work_seconds, work_hr)):
            seconds.append(duration); hrs.append(hr)
            if index < len(work_seconds)-1:
                seconds.append(60); hrs.append(110)
        seconds.append(720); hrs.append(105)
        part = alternative_part(
            athlete, {"sport":"ELLIPTICAL", "average_hr":137}, sum(seconds),
            [dict(elapsed_time=duration, avg_heart_rate=hr, hr_tail=hr)
             for duration, hr in zip(seconds, hrs)],
        )
        proposal = {
            "warmup_laps":[1], "cooldown_laps":[len(seconds)],
            "recovery_laps":list(range(3, 18, 2)),
            "reps":[{"laps":[lap], "target_seconds":duration}
                    for lap, duration in zip(range(2, 19, 2), work_seconds)],
            "format":"compact",
            "presentation":{"warmup_seconds":900, "cooldown_seconds":720,
                            "recovery_seconds":60, "work_zone":"2>3"},
        }
        checked = checked_proposal(part, proposal, athlete=athlete, zone_basis="hr")
        expected_main = "Elliptical 1×(12' - 10' - 8' - 6' - 5' - 4' - 3' - 2' - 1') Z2>Z3 p1"
        self.assertEqual(
            checked["training_fields"]["alt"],
            "Elliptical 15' Z1 // " + expected_main + " // Elliptical 12' Z1",
        )
        self.assertEqual(len(checked["watch_loads"]), 3)
        self.assertTrue(parse_alternative_text(expected_main).ok)
        self.assertEqual(
            sum(lap["seconds"] for load in checked["watch_loads"] for lap in load["alt_laps"]),
            sum(seconds),
        )
    def test_alternative_uses_all_time_only_laps_and_corrected_hr(self):
        from core.watch_alternative import alternative_part
        athlete = SimpleNamespace(zone_hr_bpm={"1":"145","2":"146-160","3":"161-175"},alternative_hr_correction=10)
        seconds = [930,604,300,601,300,601,323,601,307,388]
        laps = [dict(elapsed_time=s,avg_heart_rate=hr,hr_tail=end) for s,hr,end in
                zip(seconds,[111,133,119,138,109,140,114,138,118,141],
                    [None,146,113,148,104,152,108,156,109,155])]
        part = alternative_part(athlete,{"sport":"ELLIPTICAL","average_hr":132},sum(seconds),laps)
        proposal = dict(warmup_laps=[1],cooldown_laps=[10],recovery_laps=[3,5,7,9],
            reps=[dict(laps=[i],target_seconds=600) for i in (2,4,6,8)])
        checked = checked_proposal(part,proposal,athlete=athlete)
        self.assertTrue(checked["e_usable"])
        self.assertNotIn("main",checked["training_fields"])
        self.assertEqual(checked["watch_loads"],[])
        self.assertIn("Elliptical Work 604s Z2",checked["training_fields"]["alt"])
        self.assertIn("Elliptical Work 601s Z3",checked["training_fields"]["alt"])
        self.assertEqual(sum(l["seconds"] for l in checked["alternative_laps"]),sum(seconds))
        from core.parser import parse_segment_text
        from core.alternative import split_alternative_segments
        texts = split_alternative_segments(checked["training_fields"]["alt"])
        self.assertEqual(sum(parse_segment_text(text,zone_required=False).duration_s for text in texts),sum(seconds))
        with self.assertRaises(ValueError):
            checked_proposal(part,proposal,athlete=athlete,zone_basis="pace")
        with self.assertRaises(ValueError):
            checked_proposal(part,dict(proposal,recovery_laps=[3,5,7]),athlete=athlete)

    def test_save_digest_accepts_browser_number_spelling_but_no_measurement_change(self):
        from core.views.garmin_e import preview_digest
        fields = {"wu":"","main":"2×200 m Z4","cd":""}
        integer = [dict(meters=200,seconds=38,hr_samples=[[0,140]])]
        floats = [dict(meters=200.0,seconds=38.0,hr_samples=[[0.0,140.0]])]
        self.assertEqual(preview_digest(fields,integer),preview_digest(fields,floats))
        changed = deepcopy(floats)
        changed[0]["seconds"] += .000000001
        self.assertNotEqual(preview_digest(fields,floats),preview_digest(fields,changed))

    def test_longer_time_rep_requires_explicit_bounded_confirmation(self):
        part = dict(watch_loads=[dict(segment='CORE',zone='1',meters=m,seconds=s)
            for m,s in [(1315,362),(60,45),(1301,360),(60,45),(1275,361),(60,45),
                        (1427,405),(60,45),(1292,360),(60,45),(1296,361)]])
        proposal = dict(recovery_laps=[2,4,6,8,10],
            reps=[dict(laps=[i],target_seconds=360) for i in (1,3,5,7,9,11)])
        with self.assertRaises(ValueError):
            checked_proposal(part,proposal)
        result = checked_proposal(part,proposal,confirmed_overrun=True)
        self.assertIn("6×6'",result['training_fields']['main'])
        self.assertEqual(result['watch_loads'][6]['seconds'],405)
        part['watch_loads'][0]['seconds'] = 405
        with self.assertRaises(ValueError):
            checked_proposal(part,proposal,confirmed_overrun=True)
    def test_progressive_mixed_sets_and_homogeneous_sets(self):
        values = [(1700,350),(60,90),(1180,233),(60,90),(843,158),(150,240),
                  (1684,334),(60,90),(1157,220),(60,90),(847,144)]
        part = dict(watch_loads=[dict(segment='CORE',zone='1' if i%2 else '3',meters=m,seconds=s)
                                for i,(m,s) in enumerate(values)])
        proposal = dict(recovery_laps=[2,4,6,8,10],reps=[
            dict(laps=[i],target_meters=target) for i,target in zip((1,3,5,7,9,11),(1700,1200,850)*2)])
        result = checked_proposal(part,proposal,zone_basis='pace')
        self.assertIn('2×(1700 m - 1200 m - 850 m)',result['training_fields']['main'])
        loads = []
        for i in range(16):
            if i:
                loads.append(dict(segment='CORE',zone='1',meters=60,seconds=210 if i==8 else 60))
            loads.append(dict(segment='CORE',zone='3',meters=498,seconds=100-i))
        part = dict(watch_loads=loads)
        proposal = dict(recovery_laps=list(range(2,32,2)),set_start_laps=[1,17],
            reps=[dict(laps=[i],target_meters=500) for i in range(1,32,2)])
        result = checked_proposal(part,proposal,zone_basis='pace')
        self.assertIn('2×(8×500 m Z3 p60) sp210',result['training_fields']['main'])

    def test_mixed_pattern_and_clock_preserve_all_measured_facts(self):
        part,proposal = fixture()
        before = deepcopy(part)
        result = checked_proposal(part,proposal,zone_basis="pace")
        self.assertIn("2×(200 m - 100 m)",result["training_fields"]["main"])
        self.assertEqual(part,before)
        self.assertEqual([(l["meters"],l["seconds"]) for l in result["watch_loads"]],
                         [(l["meters"],l["seconds"]) for l in part["watch_loads"]])
        slot = SimpleNamespace(source="watch_e",watch_loads=result["watch_loads"],
            segments=SimpleNamespace(all=lambda:[_virtual_segment_from_text("CORE",result["training_fields"]["main"])]))
        self.assertEqual([r["measured_seconds"] for r in processed_main_reps(slot)],[38,19,37,19])

    def test_invalid_and_invented_assignments_rejected(self):
        part,proposal = fixture()
        for changed in (
            dict(proposal,recovery_laps=[3,5,7]), # omitted last lap
            dict(proposal,recovery_laps=[3,5,7,9,2]), # duplicate work
            dict(proposal,reps=proposal["reps"]+[dict(laps=[10],target_meters=100)]),
            dict(proposal,reps=[dict(laps=[2,3],target_meters=300)]+proposal["reps"][1:]),
            dict(proposal,reps=[dict(laps=[2],target_meters=500)]+proposal["reps"][1:]),
            dict(proposal,recovery_laps=[5,7,9],reps=[dict(laps=[2,3],target_meters=300)]+proposal["reps"][1:]),
        ):
            with self.assertRaises(ValueError):
                checked_proposal(part,changed)

    def test_hr_and_pace_can_be_switched_without_changing_membership(self):
        part,proposal = fixture()
        athlete = SimpleNamespace(zone_hr_bpm={"1":"145","2":"146-160"})
        hr = checked_proposal(part,proposal,athlete=athlete,zone_basis="hr")
        pace = checked_proposal(part,proposal,athlete=athlete,zone_basis="pace")
        self.assertIn("Z1",hr["training_fields"]["main"])
        self.assertIn("Z4",pace["training_fields"]["main"])
        for left,right in zip(hr["watch_loads"],pace["watch_loads"]):
            self.assertEqual(left.get("ai_rep"),right.get("ai_rep"))
            self.assertEqual(left["seconds"],right["seconds"])
        part["watch_loads"][1].pop("average_hr_last_15")
        missing = checked_proposal(part,proposal,athlete=athlete,zone_basis="hr")
        self.assertIn("lack usable HR",missing["e_zone_note"])

    @patch.dict("os.environ",{"OPENAI_API_KEY":"private-test-key"},clear=False)
    @patch("core.garmin_e.urlopen")
    def test_model_receives_real_conversation_and_no_identity(self, urlopen):
        response = MagicMock()
        response.__enter__.return_value.read.return_value = json.dumps({
            "choices":[{"message":{"content":json.dumps({"reply":"Wat bedoel je met het tweede blok?","proposal":None})}}]}).encode()
        urlopen.return_value = response
        part,_ = fixture()
        history = [{"role":"user","content":"Leg uit waarom die 100m herstel is."}]
        automatic = {"role": "user", "content": "Analyze the whole recording", "automatic": True}
        answer = ask_model(lap_facts(part),history + [automatic],{"zone_basis":"pace"})
        self.assertIn("tweede blok",answer["reply"])
        body = json.loads(urlopen.call_args.args[0].data)
        self.assertEqual(body["messages"][-1],history[-1])
        self.assertIn("Use English if no actual user message is available", body["messages"][0]["content"])
        self.assertFalse(body["store"])
        self.assertEqual(body["reasoning_effort"], "low")
        self.assertEqual(body["response_format"],{"type":"json_object"})

    @patch("core.garmin_e.ask_model", return_value={"reply": "La proposition a été mise à jour."})
    def test_fixed_notice_uses_latest_message_and_english_for_training_notation(self, model):
        from core.garmin_e import localize_garmin_e_notice
        notice = "The proposal has been updated."
        self.assertEqual(localize_garmin_e_notice(notice, None), notice)
        self.assertEqual(localize_garmin_e_notice(notice, "WU 6×400 m Z3 CD"), notice)
        model.assert_not_called()
        self.assertEqual(localize_garmin_e_notice(notice, "Corrige les zones, s'il te plaît."),
                         "La proposition a été mise à jour.")
        self.assertEqual(model.call_args.args[2]["latest_user_message"], "Corrige les zones, s'il te plaît.")


@override_settings(GARMIN_CLIENT_ID="test",GARMIN_CLIENT_SECRET="test",GARMIN_REDIRECT_URI="https://example.org/callback/")
class GarminEEndpointTests(TestCase):
    @patch("core.views.garmin_e.ask_model")
    def test_strength_activity_imports_only_into_strength(self, model):
        from core.models import TrainingSlot
        from core.strength import strength_duration_s
        self.record.distance_m = None
        self.record.duration_s = 3293
        self.record.analysis_data = {"activity_metrics": {"sport": "STRENGTH_TRAINING", "average_hr": 88}}
        self.record.save()
        part = self.client.get(self.url, {**self.query, "preview": "measured"}).json()["results"][0]["parts"][0]
        self.assertTrue(part["e_usable"])
        self.assertEqual(part["training_fields"], {"strength": "Strength Training 54'53\""})
        url = reverse("slot_modal", args=[2026, 11, 14, 2]) + "?" + urlencode({
            "athlete": self.athlete.pk, "source": "athlete_year",
        })
        self.assertEqual(self.client.post(url, {"core_text": "2000m Z1", "alt_text": "Bike 30' Z1"}).status_code, 200)
        response = self.client.post(url, {
            "watch_origin": "watch_e", "watch_strength_text": part["training_fields"]["strength"],
            "watch_validation": part["e_validation"], "watch_loads": "[]",
        })
        self.assertEqual(response.status_code, 204, response.content[:500])
        slot = TrainingSlot.objects.get(athlete=self.athlete, date="2026-11-14", slot_index=2)
        self.assertEqual(strength_duration_s(slot.segments.get(type="CORE2").text), 3293)
        self.assertEqual(slot.segments.get(type="ALT").text, "Bike 30' Z1")
        self.assertEqual(slot.core_text(), "2000m Z1")
        model.assert_not_called()

    def test_compact_alternative_sequence_counts_every_between_rep_pause_in_z1(self):
        from core.alternative import parse_alternative_text, segment_zone_durations
        text = "Elliptical 1×(12' - 10' - 8' - 6' - 5' - 4' - 3' - 2' - 1') Z2>Z3 p1"
        segment = SimpleNamespace(text=text, duration_s=12 * 60)
        self.assertEqual(parse_alternative_text(text).duration_s, 59 * 60)
        self.assertEqual(segment_zone_durations(segment, lambda _: 0),
                         [("2", 1530), ("3", 1530), ("1", 480)])
        self.assertEqual(parse_alternative_text("Elliptical 6×6' Z2 p1'").duration_s, 41 * 60)

    def test_preview_formats_only_pauses_over_ninety_seconds(self):
        from core.watch_ai_structure import description
        preview = description({"main": '2×(10×400 m Z3 p135") sp359 // 3×200 m p90 // 2×200 m p135m'})
        self.assertIn('p2\'15") sp5\'59"', preview)
        self.assertIn("p90 // 2×200 m p135m", preview)

    @patch("core.views.garmin_e.ask_model")
    def test_literal_warmup_sprints_and_long_reps_follow_measured_order(self, model):
        laps = [
            (1004.77, 311), (1001.54, 294), (265.32, 74), (6.68, 7),
            (95.75, 15), (20.77, 6), (101.99, 16), (16.81, 4),
            (1018.06, 209), (68.24, 60), (1008.02, 211), (59.54, 60),
            (1006.50, 207), (78.15, 59), (1005.36, 210), (21.84, 85),
            (1003.20, 202), (77.95, 60), (1004.18, 206), (45.61, 65),
            (1008.84, 204), (78.94, 59), (1005.35, 208), (14.32, 58),
        ]
        self.record.analysis_data = {"laps": [{"distance": meters, "elapsed_time": seconds}
                                              for meters, seconds in laps]}
        self.record.distance_m = sum(meters for meters, _ in laps)
        self.record.duration_s = sum(seconds for _, seconds in laps)
        self.record.save()
        response = self.chat("2250m wu//2*100m z6//8*1000m z2")
        self.assertEqual(response.status_code, 200, response.json())
        part = response.json()["results"][0]["parts"][0]
        self.assertTrue(part["e_usable"], part["chat_reply"])
        self.assertIn("2250 m", part["training_fields"]["wu"])
        self.assertIn("2×100 m Z6", part["training_fields"]["main"])
        self.assertIn("8×1000 m Z2", part["training_fields"]["main"])
        self.assertEqual([idx for idx, load in enumerate(part["watch_loads"], 1) if load["work_rep"]],
                         [5, 7, *range(9, 24, 2)])
        self.assertEqual(len(part["watch_loads"]), len(laps))
        model.assert_not_called()

    def test_checked_mixed_sprint_sequence_can_be_used_as_pm_training(self):
        from django.core import signing
        from core.models import TrainingSlot
        from core.views.garmin_e import preview_digest

        loads = [{"meters":1000, "seconds":300, "zone":"1", "segment":"WU"}]
        reps, recovery = [], []
        for index, meters in enumerate((60, 70, 80, 70, 60)):
            lap = len(loads) + 1
            loads.append({"meters":meters, "seconds":10, "zone":"4", "segment":"CORE"})
            reps.append({"laps":[lap], "target_meters":meters})
            if index < 4:
                recovery.append(len(loads) + 1)
                loads.append({"meters":100, "seconds":60, "zone":"1", "segment":"CORE"})
        loads.append({"meters":800, "seconds":300, "zone":"1", "segment":"CD"})
        proposal = {"warmup_laps":[1], "recovery_laps":recovery,
                    "cooldown_laps":[len(loads)], "reps":reps}
        proposal, changed = apply_explicit_zone_labels(
            proposal, "maak er 1*(60m//70m//80m//70m//60m) z6 van",
        )
        self.assertTrue(changed)
        checked = checked_proposal({"watch_loads":loads}, proposal, zone_basis="pace")
        fields = checked["training_fields"]
        validation = signing.dumps(
            [self.coach.pk, self.athlete.pk, "2026-11-14",
             preview_digest(fields, checked["watch_loads"])],
            salt="garmin-e-save",
        )
        url = reverse("slot_modal", args=[2026, 11, 14, 2]) + "?" + urlencode({
            "athlete":self.athlete.pk, "source":"athlete_year",
        })
        response = self.client.post(url, {
            "watch_origin":"watch_e", "watch_validation":validation,
            "watch_loads":json.dumps(checked["watch_loads"]),
            "wu_text":fields["wu"], "core_text":fields["main"], "cd_text":fields["cd"],
        })
        self.assertEqual(response.status_code, 200, response.content.decode())
        slot = TrainingSlot.objects.get(athlete=self.athlete, date="2026-11-14", slot_index=2)
        self.assertEqual(slot.source, "watch_e")
        sprint = slot.segments.get(type="CORE", text=fields["main"])
        self.assertEqual(sprint.distance_m, 340)

    @patch("core.views.garmin_e.ask_model")
    def test_explicit_compact_alternative_chat_updates_preview_without_model_prose(self, model):
        durations = [600, 45, 30, 45, 30, 45, 300]
        self.record.distance_m = None
        self.record.duration_s = sum(durations)
        self.record.analysis_data = {
            "activity_metrics": {"sport": "ELLIPTICAL", "average_hr": 110},
            "laps": [{"elapsed_time": value, "avg_heart_rate": 100, "hr_tail": 100}
                     for value in durations],
        }
        self.record.save()
        preview = self.client.get(
            self.url, {**self.query, "preview": "measured"},
        ).json()["results"][0]
        chat_url = self.url + "?" + urlencode({
            **self.query, "suggestion_session": preview["start"],
        })

        result = self.client.post(chat_url, {"chat": json.dumps([{
            "role": "user", "content": 'WU-2*(45" Z2-30" Z1)-45" Z2-CD',
        }])}).json()["results"][0]["parts"][0]

        self.assertTrue(result["e_usable"], result)
        self.assertEqual(
            result["training_fields"]["alt"],
            "Elliptical 10' // Elliptical 2×(45s Z2 - 30s Z1) // "
            "Elliptical 45s Z2 // Elliptical 5'",
        )
        self.assertIn(result["training_fields"]["alt"], result["chat_reply"])
        model.assert_not_called()

    @patch("core.views.garmin_e.localize_garmin_e_notice", side_effect=lambda text, message: text)
    @patch("core.views.garmin_e.ask_model")
    def test_alternative_literal_pause_and_explicit_cooldown_transfer(self, model, translate):
        durations = [900, 360, 60, 367, 61, 360, 60, 361, 61, 360, 60, 361, 601]
        self.record.distance_m = None
        self.record.duration_s = sum(durations)
        self.record.analysis_data = {
            "activity_metrics": {"sport": "ELLIPTICAL", "average_hr": 110},
            "laps": [{"elapsed_time": value, "avg_heart_rate": 100, "hr_tail": 100} for value in durations],
        }
        self.record.save()
        initial = self.chat("15' wu//6*6'z2 p1//10'cd").json()["results"][0]["parts"][0]
        self.assertIn("6×6' Z2 p1'", initial["training_fields"]["alt"])
        self.assertIn("first minute of the cooldown", initial["chat_reply"])
        self.assertTrue(initial["e_final_recovery_pending"])
        declined = self.chat("nee").json()["results"][0]["parts"][0]
        self.assertFalse(declined["e_final_recovery_pending"])
        self.assertEqual(declined["training_fields"], initial["training_fields"])
        rejected = self.chat("15'wu// 6*6'z2 p1//9'cd").json()["results"][0]["parts"][0]
        self.assertEqual(rejected["training_fields"], initial["training_fields"])
        self.assertIn("601s", rejected["chat_reply"])
        pending = self.chat("ik pak er 1'van die 10' om van de main een kloppende set te maken").json()["results"][0]["parts"][0]
        self.assertEqual(pending["training_fields"], initial["training_fields"])
        updated = self.chat("ja doe dat").json()["results"][0]["parts"][0]
        self.assertFalse(updated["e_final_recovery_pending"])
        self.assertIn("6×(6' Z2 - 1'", updated["training_fields"]["alt"])
        self.assertIn("Elliptical 9'", updated["training_fields"]["alt"])
        self.assertIn(updated["training_fields"]["alt"], updated["chat_reply"])
        self.assertEqual([load["seconds"] for load in updated["watch_loads"]][-1], 541)
        self.assertEqual(sum(load["seconds"] for load in updated["watch_loads"]), sum(durations))
        self.assertEqual(sum(lap["seconds"] for load in updated["watch_loads"] for lap in load["alt_laps"]), sum(durations))
        model.assert_not_called()

    @patch("core.views.garmin_e.localize_garmin_e_notice", side_effect=lambda text, message: text)
    @patch("core.views.garmin_e.ask_model")
    def test_alternative_descending_set_suggests_first_cooldown_minute(self, model, translate):
        work = [720, 600, 480, 360, 300, 240, 180, 120, 60]
        durations = [900, *[seconds for target in work[:-1] for seconds in (target, 60)], work[-1], 721]
        self.record.distance_m = None
        self.record.duration_s = sum(durations)
        self.record.analysis_data = {
            "activity_metrics": {"sport": "ELLIPTICAL", "average_hr": 110},
            "laps": [{"elapsed_time": value, "avg_heart_rate": 100, "hr_tail": 100} for value in durations],
        }
        self.record.save()
        model.return_value = {"reply": "Descending set.", "intent": "update", "zone_basis": "hr",
                              "proposal": {"warmup_laps": [1], "cooldown_laps": [len(durations)],
                                           "recovery_laps": list(range(3, len(durations) - 1, 2)),
                                           "reps": [{"laps": [2 + 2 * index], "target_seconds": target}
                                                    for index, target in enumerate(work)]}}
        initial = self.chat("Analyze the descending intervals.").json()["results"][0]["parts"][0]
        self.assertTrue(initial["e_usable"], initial["chat_reply"])
        self.assertIn("first minute of the cooldown", initial["chat_reply"])
        updated = self.chat("yes").json()["results"][0]["parts"][0]
        self.assertNotEqual(updated["training_fields"], initial["training_fields"])
        self.assertIn(" - 1' Z1)", updated["training_fields"]["alt"])
        self.assertEqual(updated["watch_loads"][-1]["seconds"], 661)
        self.assertEqual(sum(load["seconds"] for load in updated["watch_loads"]), sum(durations))
        model.assert_called_once()

    @patch("core.views.garmin_e.ask_model")
    def test_running_laps_without_recognized_main_still_offer_chat(self, model):
        self.record.distance_m = 349
        self.record.duration_s = 133
        self.record.analysis_data = {"laps": [
            {"distance": 172, "elapsed_time": 60},
            {"distance": 24, "elapsed_time": 20},
            {"distance": 153, "elapsed_time": 53},
        ]}
        self.record.save()

        part = self.client.get(
            self.url, {**self.query, "preview": "measured"},
        ).json()["results"][0]["parts"][0]

        self.assertEqual(part["training_fields"]["main"], "")
        self.assertEqual(part["description"], "No clear main section detected.")
        self.assertTrue(part["e_auto_analyze"])
        self.assertFalse(part["e_usable"])
        self.assertEqual(len(part["watch_loads"]), 3)
        model.assert_not_called()

    @patch("core.views.garmin_e.ask_model")
    def test_single_alternative_lap_is_immediately_usable_and_saves_actual_seconds(self, model):
        from core.models import GarminEConversation, TrainingSlot
        from core.stats import _alt_zone_durations
        self.record.distance_m = None
        self.record.duration_s = 3603
        self.record.analysis_data = {"activity_metrics":{"sport":"ELLIPTICAL","average_hr":148},
            "laps":[dict(elapsed_time=3603,avg_heart_rate=146,hr_tail=160)]}
        self.record.save()
        self.athlete.zone_hr_bpm = {"1":"175","2":"176-185"}
        self.athlete.save()
        part = self.client.get(self.url,{**self.query,"preview":"measured"}).json()["results"][0]["parts"][0]
        self.assertTrue(part["e_usable"],part)
        self.assertEqual(part["training_fields"]["alt"],'Elliptical 60\'03" Z1')
        self.assertTrue(part["e_validation"])
        self.assertEqual(part["watch_loads"][0]["seconds"],3603)
        self.assertEqual(part["watch_loads"][0]["alt_laps"][0]["average_hr"],146)
        self.assertEqual(part["watch_loads"][0]["alt_laps"][0]["end_hr"],160)
        model.assert_not_called()
        payload = dict(watch_origin="watch_e",watch_loads=json.dumps(part["watch_loads"]),
            watch_validation=part["e_validation"],alt_text=part["training_fields"]["alt"],watch_fields="alternative_replace")
        save = reverse("slot_modal",args=[2026,11,14,1])+"?"+urlencode({"athlete":self.athlete.pk,"source":"athlete_year"})
        self.assertEqual(self.client.post(save,payload).status_code,200)
        alt = TrainingSlot.objects.get(athlete=self.athlete,date="2026-11-14",slot_index=1).segments.get(type="ALT")
        self.assertEqual(alt.duration_s,3603)
        self.assertEqual(sum(s for _,s in _alt_zone_durations(alt)),3603)
        self.assertEqual(self.client.post(save,dict(payload,alt_text="Elliptical 80' Z1")).status_code,400)
        # A prior discussion-only conversation must also recover on reopening.
        conversation = GarminEConversation.objects.get(athlete=self.athlete)
        state = deepcopy(conversation.state)
        state["part"]["e_usable"] = False
        state["proposal"] = None
        state["history"] = [{"role":"user","content":"why i cannot use it?"},
                            {"role":"assistant","content":"Only one lap, no proposal."}]
        conversation.state = state
        conversation.save()
        recovered = self.client.get(self.url,{**self.query,"preview":"measured"}).json()["results"][0]["parts"][0]
        self.assertTrue(recovered["e_usable"])
        self.assertEqual(recovered["e_history"][0]["content"],"why i cannot use it?")
        model.assert_not_called()

    @patch("core.views.garmin_e.ask_model")
    def test_single_alternative_missing_hr_has_no_invented_zone(self, model):
        self.record.distance_m = None
        self.record.duration_s = 3603
        self.record.analysis_data = {"activity_metrics":{"sport":"ELLIPTICAL"},
                                   "laps":[dict(elapsed_time=3603)]}
        self.record.save()
        part = self.client.get(self.url,{**self.query,"preview":"measured"}).json()["results"][0]["parts"][0]
        self.assertTrue(part["e_usable"],part)
        self.assertNotIn(" Z",part["training_fields"]["alt"])
        self.assertEqual(part["training_fields"]["alt"], 'Elliptical 60\'03"')
        self.assertIn("no usable HR",part["e_zone_note"])
        model.assert_not_called()

    @patch("core.views.garmin_e.ask_model")
    def test_single_elliptical_displays_minutes_and_seconds_without_lap_hr(self, model):
        self.record.distance_m = None
        self.record.duration_s = 1154
        self.record.analysis_data = {"activity_metrics": {"sport": "ELLIPTICAL", "average_hr": 127},
                                     "laps": [dict(elapsed_time=1154)]}
        self.record.save()
        part = self.client.get(self.url, {**self.query, "preview": "measured"}).json()["results"][0]["parts"][0]
        self.assertEqual(part["training_fields"]["alt"], 'Elliptical 19\'14"')
        self.assertEqual(part["watch_loads"][0]["seconds"], 1154)
        self.assertIsNone(part["watch_loads"][0]["alt_laps"][0]["zone"])
        model.assert_not_called()

    @patch("core.views.garmin_e.ask_model")
    def test_first_analysis_makes_supported_result_usable_without_chat(self, model):
        preview = self.client.get(self.url,{**self.query,"preview":"measured"}).json()["results"][0]
        self.assertTrue(preview["parts"][0]["e_auto_analyze"])
        model.assert_not_called()
        model.side_effect = [
            {"reply":"Ik zie twee 200–100-paren. Zal ik er een voorstel van maken?","proposal":None},
            {"reply":"De twee gemeten paren staan klaar.","proposal":self.proposal,"zone_basis":"pace"}]
        url = self.url+"?"+urlencode({**self.query,"suggestion_session":preview["start"]})
        result = self.client.post(url,{"analyze":"auto"}).json()["results"][0]["parts"][0]
        self.assertTrue(result["e_usable"],result)
        self.assertTrue(result["e_validation"])
        self.assertIn("2×(200 m - 100 m)",result["training_fields"]["main"])
        self.assertTrue(all(m["role"]=="assistant" for m in result["e_history"]))
        self.assertTrue(model.call_args.args[2]["initial_analysis"])
        self.assertEqual(model.call_count,2)
        repeated = self.client.post(url,{"analyze":"auto"}).json()["results"][0]["parts"][0]
        self.assertTrue(repeated["e_usable"])
        self.assertEqual(model.call_count,2)
        # The Analyze button can explicitly rerun analysis without a chat message.
        model.side_effect = None
        model.return_value = {"reply":"Opnieuw gecontroleerd.","proposal":self.proposal,"zone_basis":"pace"}
        refreshed = self.client.post(url,{"analyze":"1"}).json()["results"][0]["parts"][0]
        self.assertTrue(refreshed["e_usable"])
        self.assertEqual(model.call_count,3)
        self.assertTrue(all(m["role"]=="assistant" for m in refreshed["e_history"]))

    def combine_example(self):
        self.record.analysis_data = {"laps":[dict(distance=m,elapsed_time=s) for m,s in
                                             [(500,100),(60,60),(500,100)]]}
        self.record.distance_m = 1060
        self.record.duration_s = 260
        self.record.save()
        for activity,hour,minute,meters,seconds in (("outer-wu",9,50,800,260),("outer-cd",10,20,1000,340)):
            GarminActivitySummary.objects.create(athlete=self.athlete,activity_id=activity,
                activity_start=datetime(2026,11,14,hour,minute,tzinfo=timezone.utc),activity_date="2026-11-14",
                distance_m=meters,duration_s=seconds,analysis_data={"laps":[dict(distance=meters,elapsed_time=seconds)]})
        sessions = self.client.get(self.url,{**self.query,"preview":"measured"}).json()["results"]
        return [{"start":s["start"],"role":role} for s,role in zip(sessions,("wu","main","cd"))]

    @patch("core.views.garmin_e.ask_model")
    def test_combine_checked_main_and_outer_recordings_saves_all_laps(self, model):
        selection = self.combine_example()
        main_url = self.url+"?"+urlencode({**self.query,"suggestion_session":selection[1]["start"]})
        main_proposal = dict(recovery_laps=[2],reps=[dict(laps=[i],target_meters=500) for i in (1,3)])
        model.return_value = {"reply":"Twee gemeten 500m-reps.","proposal":main_proposal,"zone_basis":"pace"}
        self.assertTrue(self.client.post(main_url,{"chat":json.dumps([{"role":"user","content":"Analyseer Main"}])}).json()["ok"])
        calls = model.call_count
        with patch("core.views.garmin_e.checked_proposal", side_effect=AssertionError("Do not reinterpret checked Main")) as recheck:
            response = self.client.post(self.url+"?"+urlencode(self.query),{"combine":json.dumps(selection)})
            recheck.assert_not_called()
        self.assertEqual(response.status_code,200,response.json())
        combined = response.json()["results"][0]
        part = combined["parts"][0]
        self.assertEqual(model.call_count,calls)
        self.assertTrue(part["e_usable"],part)
        self.assertEqual(part["training_fields"]["main"], "2×500 m Z4 p60")
        self.assertEqual(part["training_fields"]["wu"],"800 m Z1")
        self.assertEqual(part["training_fields"]["cd"],"1000 m Z1")
        self.assertEqual([(l["meters"],l["seconds"]) for l in part["watch_loads"]],
                         [(800,260),(500,100),(60,60),(500,100),(1000,340)])
        token = combined["e_combine_token"]
        model.return_value = {"reply":"De gekozen eerste opname is je WU.","proposal":None,"zone_basis":"pace"}
        chat_url = self.url+"?"+urlencode({**self.query,"suggestion_session":combined["start"]})
        answered = self.client.post(chat_url,{"combine_token":token,
            "chat":json.dumps([{"role":"user","content":"Waarom is die eerste opname WU?"}])}).json()
        part = answered["results"][0]["parts"][0]
        self.assertTrue(part["e_usable"])
        self.assertEqual([row.get("recording_role") for row in model.call_args.args[0]],["wu","main","main","main","cd"])
        fields = part["training_fields"]
        payload = dict(watch_origin="watch_e",watch_loads=json.dumps(part["watch_loads"]),
            watch_validation=part["e_validation"],wu_text=fields["wu"],core_text=fields["main"],cd_text=fields["cd"])
        save = reverse("slot_modal",args=[2026,11,14,1])+"?"+urlencode({"athlete":self.athlete.pk,"source":"athlete_year"})
        self.assertEqual(self.client.post(save,payload).status_code,200)
        from core.models import TrainingSlot
        slot = TrainingSlot.objects.get(athlete=self.athlete,date="2026-11-14",slot_index=1)
        self.assertEqual(len(slot.watch_loads),5)
        self.assertEqual([rep["measured_seconds"] for rep in slot.watch_main_reps],[100,100])
        bad = self.client.post(chat_url,{"combine_token":token+"invalid",
            "chat":json.dumps([{"role":"user","content":"Analyseer"}])})
        self.assertEqual(bad.status_code,400)

    @patch("core.views.garmin_e.ask_model")
    def test_two_checked_main_recordings_can_be_combined_or_appended(self, model):
        recordings = self.combine_example()
        selection = recordings[:2]
        parts = []
        for item, reps, recovery in zip(selection, ([800], [500, 500]), ([], [2])):
            item["role"] = "main"
            model.return_value = {
                "reply": "Gemeten Main.",
                "proposal": dict(recovery_laps=recovery, reps=[
                    dict(laps=[2 * i + 1], target_meters=meters)
                    for i, meters in enumerate(reps)
                ]),
                "zone_basis": "pace",
            }
            url = self.url + "?" + urlencode({**self.query, "suggestion_session": item["start"]})
            part = self.client.post(url, {
                "chat": json.dumps([{"role": "user", "content": "Analyseer Main"}]),
            }).json()["results"][0]["parts"][0]
            self.assertTrue(part["e_usable"], part)
            parts.append(part)

        calls = model.call_count
        response = self.client.post(self.url + "?" + urlencode(self.query), {
            "combine": json.dumps(selection[::-1]),
        })
        self.assertEqual(response.status_code, 200, response.json())
        combined = response.json()["results"][0]["parts"][0]
        self.assertTrue(combined["e_usable"], combined)
        expected = " // ".join(part["training_fields"]["main"] for part in parts)
        self.assertEqual(combined["training_fields"]["main"], expected)
        self.assertEqual(model.call_count, calls)

        GarminActivitySummary.objects.create(
            athlete=self.athlete, activity_id="extra-wu",
            activity_start=datetime(2026, 11, 14, 9, 30, tzinfo=timezone.utc),
            activity_date="2026-11-14", distance_m=600, duration_s=200,
            analysis_data={"laps": [{"distance": 600, "elapsed_time": 200}]},
        )
        sessions = self.client.get(self.url, {**self.query, "preview": "measured"}).json()["results"]
        self.assertEqual(len(sessions), 4)
        response = self.client.post(self.url + "?" + urlencode(self.query), {
            "combine": json.dumps([{"start": sessions[0]["start"], "role": "wu"}, *recordings]),
        })
        self.assertEqual(response.status_code, 200, response.json())
        full = response.json()["results"][0]["parts"][0]
        self.assertTrue(full["e_usable"])
        self.assertEqual(full["training_fields"], {"wu": "600 m Z1", "main": expected, "cd": "1000 m Z1"})
        self.assertEqual(model.call_count, calls)

        sprint_selection = [{"start": recordings[0]["start"], "role": "sprint"}, *recordings[1:]]
        response = self.client.post(self.url + "?" + urlencode(self.query), {
            "combine": json.dumps(sprint_selection),
        })
        self.assertEqual(response.status_code, 200, response.json())
        sprint = response.json()["results"][0]["parts"][0]
        self.assertTrue(sprint["e_usable"])
        self.assertEqual(sprint["training_fields"]["sprint"], parts[0]["training_fields"]["main"])
        self.assertEqual(sprint["watch_loads"][0]["segment"], "SPR")

        from core.models import TrainingSlot
        for slot_index, imports in ((1, parts), (2, [combined])):
            save = reverse("slot_modal", args=[2026, 11, 14, slot_index]) + "?" + urlencode({
                "athlete": self.athlete.pk, "source": "athlete_year",
            })
            for part in imports:
                fields = part["training_fields"]
                response = self.client.post(save, dict(
                    watch_fields="running_add", watch_origin="watch_e",
                    watch_loads=json.dumps(part["watch_loads"]), watch_validation=part["e_validation"],
                    wu_text=fields["wu"], core_text=fields["main"], cd_text=fields["cd"],
                ))
                self.assertEqual(response.status_code, 200, response.content[:500])
            slot = TrainingSlot.objects.get(athlete=self.athlete, date="2026-11-14", slot_index=slot_index)
            self.assertEqual(slot.core_text(), expected)
            self.assertEqual([rep["measured_seconds"] for rep in slot.watch_main_reps], [260, 100, 100])

        slot.segments.create(type="SPR", text="5×60 m Z6", order=2)
        fields = sprint["training_fields"]
        response = self.client.post(save, dict(
            watch_origin="watch_e", watch_loads=json.dumps(sprint["watch_loads"]),
            watch_validation=sprint["e_validation"], sprint_text=fields["sprint"],
            wu_text=fields["wu"], core_text=fields["main"], cd_text=fields["cd"],
        ))
        self.assertEqual(response.status_code, 200, response.content[:500])
        slot.refresh_from_db()
        self.assertEqual(slot.segments.get(type="SPR").text, fields["sprint"])
        self.assertEqual(slot.core_text(), fields["main"])
        self.assertEqual([rep["measured_seconds"] for rep in slot.watch_main_reps], [100, 100])
        from core.views.calendar import _ayc_slot_loads_for_totals, _ayc_slot_session_zones
        sprint_loads = [load for load in _ayc_slot_loads_for_totals(slot) if load.get("segment") == "SPR"]
        self.assertEqual([(load["zone"], load["meters"]) for load in sprint_loads], [("6", 800)])
        self.assertIn({"zone": "6", "km": "0.8"}, _ayc_slot_session_zones(slot))

    def test_combine_sprint_with_its_own_warmup_and_cooldown(self):
        from core.garmin_e_combine import combine_recordings

        def part(wu, main, cd, segments):
            return {
                "e_usable": True, "training_fields": {"wu": wu, "main": main, "cd": cd},
                "watch_loads": [
                    {"segment": segment, "meters": 100, "seconds": 30,
                     "work_rep": segment == "CORE", "zone": "1"}
                    for segment in segments
                ],
            }

        recordings = [
            {"start": "09:00", "parts": [part("100 m Z1", "100 m Z6", "100 m Z1", ["WU", "CORE", "CD"])]},
            {"start": "09:10", "parts": [part("100 m Z1", "100 m Z3", "100 m Z1", ["WU", "CORE", "CD"])]},
        ]
        selection = [{"start": "09:00", "role": "sprint"}, {"start": "09:10", "role": "main"}]
        combined, _, _ = combine_recordings(recordings, selection)
        preview = combined["parts"][0]
        self.assertEqual(preview["training_fields"],
                         {"wu": "100 m Z1", "sprint": "100 m Z6", "main": "100 m Z3", "cd": "100 m Z1"})
        self.assertEqual([(load["segment"], load["work_rep"]) for load in preview["watch_loads"]],
                         [("WU", False), ("SPR", True), ("SPR", False), ("CORE", False), ("CORE", True), ("CD", False)])

    @patch("core.views.garmin_e.ask_model")
    def test_combine_uses_checked_main_when_fresh_measured_description_is_empty(self, model):
        selection = self.combine_example()
        main_url = self.url+"?"+urlencode({**self.query,"suggestion_session":selection[1]["start"]})
        main_proposal = dict(
            recovery_laps=[2],
            reps=[dict(laps=[i],target_meters=500) for i in (1,3)],
        )
        model.return_value = {
            "reply":"Twee gemeten 500m-reps.",
            "proposal":main_proposal,
            "zone_basis":"pace",
        }
        analyzed = self.client.post(main_url,{
            "chat":json.dumps([{"role":"user","content":"Analyseer Main"}]),
        }).json()
        self.assertTrue(analyzed["results"][0]["parts"][0]["e_usable"])

        from django.http import JsonResponse
        from core.views.coach import garmin_type_c_ayc_view as measured_reader

        def measured_without_main(request):
            response = measured_reader(request)
            data = json.loads(response.content)
            source = next(item for item in data["results"] if item["start"] == selection[1]["start"])
            source["parts"][0]["training_fields"]["main"] = ""
            return JsonResponse(data, status=response.status_code)

        with patch("core.views.coach.garmin_type_c_ayc_view", side_effect=measured_without_main):
            response = self.client.post(
                self.url+"?"+urlencode(self.query),
                {"combine":json.dumps(selection)},
            )

        self.assertEqual(response.status_code, 200, response.json())
        part = response.json()["results"][0]["parts"][0]
        self.assertTrue(part["e_usable"])
        self.assertEqual(part["training_fields"]["main"], "2×500 m Z4 p60")
        self.assertEqual(part["training_fields"]["wu"], "800 m Z1")
        self.assertEqual(part["training_fields"]["cd"], "1000 m Z1")

    @patch("core.views.garmin_e.ask_model")
    def test_combine_before_analysis_has_one_conversation_and_requires_checked_proposal(self, model):
        selection = self.combine_example()
        response = self.client.post(self.url+"?"+urlencode(self.query),{"combine":json.dumps(selection)})
        self.assertEqual(response.status_code,200,response.json())
        combined = response.json()["results"][0]
        self.assertFalse(combined["parts"][0]["e_usable"])
        model.assert_not_called()
        proposal = dict(warmup_laps=[1],cooldown_laps=[5],recovery_laps=[3],
                        reps=[dict(laps=[i],target_meters=500) for i in (2,4)])
        model.return_value = {"reply":"WU, twee werkreps en CD zijn zichtbaar.","proposal":proposal,"zone_basis":"pace"}
        answer = self.client.post(self.url+"?"+urlencode({**self.query,"suggestion_session":combined["start"]}),{
            "combine_token":combined["e_combine_token"],
            "chat":json.dumps([{"role":"user","content":"Analyseer deze hele combinatie"}])}).json()
        self.assertTrue(answer["results"][0]["parts"][0]["e_usable"],answer)
        for invalid in ([selection[0],selection[0]], [dict(selection[0],role="cd"),selection[1]],
                        [selection[0],dict(selection[1],start="missing")]):
            response = self.client.post(self.url+"?"+urlencode(self.query),{"combine":json.dumps(invalid)})
            self.assertEqual(response.status_code,400)

    @patch("core.views.garmin_e.ask_model")
    def test_compact_alternative_is_the_saved_proposal_and_keeps_actual_totals(self, model):
        seconds = [930,604,300,601,300,601,323,601,307,388]
        hrs = [111,146,113,148,104,152,108,156,109,155]
        self.record.distance_m = None
        self.record.duration_s = sum(seconds)
        self.record.analysis_data = {"activity_metrics":{"sport":"ELLIPTICAL","average_hr":132},
            "laps":[dict(elapsed_time=s,avg_heart_rate=hr,hr_tail=hr) for s,hr in zip(seconds,hrs)]}
        self.record.save()
        self.athlete.zone_hr_bpm = {"1":"157","2":"158-175"}
        self.athlete.save()
        proposal = dict(warmup_laps=[1],recovery_laps=[3,5,7,9],reps=[
            dict(laps=[i],target_seconds=target) for i,target in ((2,600),(4,600),(6,600),(8,600),(10,388))])
        model.return_value = {"reply":"Dit zijn de gemeten blokken.","proposal":proposal}
        old = self.chat("Bekijk de activiteit").json()["results"][0]["parts"][0]
        compact = deepcopy(proposal)
        compact.update(format="compact",presentation=dict(warmup_seconds=900,recovery_seconds=300,
                                                         work_zone="2",recovery_zone="1"))
        model.side_effect = [
            {"reply":"Zeker, ik zet de compacte versie als voorstel neer.","proposal":None,"intent":"update"},
            {"reply":"De compacte notatie staat nu in het voorstel.","proposal":compact,"zone_basis":"hr"}]
        part = self.chat("Zet het zo neer: 15' Z1 // 4*(10' Z2-5' Z1) + 6'28 Z2").json()["results"][0]["parts"][0]
        self.assertNotEqual(part["training_fields"],old["training_fields"])
        self.assertIn("4×(10' Z2 - 5' Z1)",part["training_fields"]["alt"])
        self.assertIn("15' Z1",part["training_fields"]["alt"])
        self.assertIn("6'28 Z2",part["training_fields"]["alt"])
        payload = dict(watch_origin="watch_e",watch_loads=json.dumps(part["watch_loads"]),
            watch_validation=part["e_validation"],alt_text=part["training_fields"]["alt"],watch_fields="alternative_replace")
        url = reverse("slot_modal",args=[2026,11,14,1])+"?"+urlencode({"athlete":self.athlete.pk,"source":"athlete_year"})
        response = self.client.post(url,payload)
        self.assertEqual(response.status_code,200)
        from core.models import TrainingSlot
        from core.stats import _alt_zone_durations
        from core.views.calendar import _ayc_slot_loads_for_totals
        slot = TrainingSlot.objects.get(athlete=self.athlete,date="2026-11-14",slot_index=1)
        alt = list(slot.segments.filter(type="ALT").order_by("order"))
        self.assertEqual(len(alt),3)
        self.assertIn("4×(10' Z2 - 5' Z1)",alt[1].text)
        self.assertEqual(sum(seg.duration_s for seg in alt),4955)
        zone_times = [item for seg in alt for item in _alt_zone_durations(seg)]
        self.assertEqual(sum(s for _,s in zone_times),4955)
        self.assertEqual(sum(s for z,s in zone_times if z=="1"),2764)
        self.assertEqual(sum(s for z,s in zone_times if z=="2"),2191)
        self.assertEqual(sum(load["seconds"] for load in _ayc_slot_loads_for_totals(slot,self.athlete)
                             if load.get("kind")=="alt"),4955)
        pm_url = reverse("slot_modal",args=[2026,11,14,2])+"?"+urlencode({"athlete":self.athlete.pk,"source":"athlete_year"})
        self.assertEqual(self.client.post(pm_url,{"core_text":"5000 m Z1"}).status_code,200)
        self.assertEqual(self.client.post(pm_url,dict(payload,watch_fields="alternative")).status_code,200)
        pm = TrainingSlot.objects.get(athlete=self.athlete,date="2026-11-14",slot_index=2)
        self.assertTrue(pm.segments.filter(type="CORE",text="5000 m Z1").exists())
        self.assertEqual(sum(s for seg in pm.segments.filter(type="ALT") for _,s in _alt_zone_durations(seg)),4955)
        # Editing the text invalidates the attachment to measured source facts.
        alt[1].text = "Elliptical 1' Z1"
        self.assertEqual(_alt_zone_durations(alt[1]),[("1",60)])

    def setUp(self):
        cache.clear()
        self.coach = get_user_model().objects.create_user(username="e-coach",is_staff=True)
        self.athlete = Athlete.objects.create(owner=self.coach,name="E Runner",birth_year=2000,gender="X",
            garmin_connection_enabled=True,
            garmin_ai_consent_at=datetime.now(timezone.utc),garmin_ai_consent_version=CONSENT_VERSION)
        self.part,self.proposal = fixture()
        self.record = GarminActivitySummary.objects.create(athlete=self.athlete,activity_id="e-example",
            activity_start=datetime(2026,11,14,10,tzinfo=timezone.utc),activity_date="2026-11-14",
            distance_m=2070,duration_s=710,analysis_data={"laps":[
                dict(distance=l["meters"],elapsed_time=l["seconds"]) for l in self.part["watch_loads"]]})
        self.client.force_login(self.coach)
        self.query = {"athlete":self.athlete.pk,"date":"2026-11-14"}
        self.url = reverse("garmin_type_e_ayc")
        self.zones = patch("core.views.polar_raw.lap_zone_paces",
            side_effect=lambda m,ms,a:("Z4" if m/(ms/1000)>4 else "Z1","NA"))
        self.zones.start()
        self.addCleanup(self.zones.stop)

    def chat(self, text):
        session = self.client.get(self.url,{**self.query,"preview":"measured"}).json()["results"][0]
        return self.client.post(self.url+"?"+urlencode({**self.query,"suggestion_session":session["start"]}),
            {"chat":json.dumps([{"role":"user","content":text}])})

    @patch("core.views.garmin_e.ask_model")
    def test_alternative_conversation_use_and_add_preserve_running(self, model):
        seconds = [930,604,300,601,300,601,323,601,307,388]
        self.record.distance_m = None
        self.record.duration_s = sum(seconds)
        self.record.analysis_data = {"activity_metrics":{"sport":"ELLIPTICAL","average_hr":132},
            "laps":[dict(elapsed_time=s,avg_heart_rate=140,hr_tail=150) for s in seconds]}
        self.record.save()
        self.athlete.zone_hr_bpm = {"1":"145","2":"146-160","3":"161-175"}
        self.athlete.save()
        model.return_value = {"reply":"Ik zie vier werkblokken van tien minuten. De rust is ongeveer vijf minuten.",
            "proposal":dict(warmup_laps=[1],cooldown_laps=[10],recovery_laps=[3,5,7,9],
                reps=[dict(laps=[i],target_seconds=600) for i in (2,4,6,8)]),"zone_basis":"hr"}
        result = self.chat("Kun je de vier tienminutenblokken met in- en uitlopen meenemen?").json()
        part = result["results"][0]["parts"][0]
        self.assertTrue(part["e_usable"],part)
        self.assertIsNone(model.call_args.args[0][0]["distance_m"])
        old_fields = deepcopy(part["training_fields"])
        corrected = deepcopy(model.return_value["proposal"])
        corrected["cooldown_laps"] = []
        corrected["reps"].append(dict(laps=[10],target_seconds=388))
        model.side_effect = [
            {"reply":"Ja, dit is nu je AM-voorstel met de laatste korte werkrep.","proposal":None},
            {"reply":"De laatste 6:28 staat nu ook als werkblok in de preview.",
             "intent":"update","proposal":corrected,"zone_basis":"hr"}]
        amended = self.chat("Ik zie het nog niet als voorstel. Gebruik lap 10 als laatste werkblok.").json()
        part = amended["results"][0]["parts"][0]
        self.assertNotEqual(part["training_fields"],old_fields)
        self.assertIn("Work 388s",part["training_fields"]["alt"])
        self.assertNotIn("Cooldown",part["training_fields"]["alt"])
        self.assertIn("updated",part["e_update_note"])
        self.assertEqual(model.call_args.args[2]["checked_assignment"]["cooldown_laps"],[10])
        model.side_effect = None
        payload = {"watch_origin":"watch_e","watch_loads":"[]","watch_validation":part["e_validation"],
                   "alt_text":part["training_fields"]["alt"],"watch_fields":"alternative_replace"}
        url = reverse("slot_modal",args=[2026,11,14,1])+"?"+urlencode({"athlete":self.athlete.pk,"source":"athlete_year"})
        self.assertEqual(self.client.post(url,payload).status_code,200)
        from core.models import TrainingSlot
        slot = TrainingSlot.objects.get(athlete=self.athlete,date="2026-11-14",slot_index=1)
        self.assertEqual(slot.source,"watch_e")
        self.assertFalse(slot.segments.filter(type="CORE").exists())
        self.assertEqual(sum(slot.segments.filter(type="ALT").values_list("duration_s",flat=True)),sum(seconds))
        self.assertEqual(self.client.post(url,dict(payload,alt_text="Elliptical 999' Z5")).status_code,400)
        pm_url = reverse("slot_modal",args=[2026,11,14,2])+"?"+urlencode({"athlete":self.athlete.pk,"source":"athlete_year"})
        self.assertEqual(self.client.post(pm_url,{"core_text":"5000 m Z1"}).status_code,200)
        self.assertEqual(self.client.post(pm_url,dict(payload,watch_fields="alternative")).status_code,200)
        pm = TrainingSlot.objects.get(athlete=self.athlete,date="2026-11-14",slot_index=2)
        self.assertTrue(pm.segments.filter(type="CORE",text="5000 m Z1").exists())
        self.assertTrue(pm.segments.filter(type="ALT").exists())

    @patch("core.views.garmin_e.ask_model")
    def test_preview_conversation_valid_proposal_and_server_memory(self, model):
        preview = self.client.get(self.url,{**self.query,"preview":"measured"}).json()
        self.assertFalse(preview["results"][0]["parts"][0]["e_usable"])
        model.assert_not_called()
        model.return_value = {"reply":"Ik zie twee 200–100-paren, met herstel ertussen.",
                              "proposal":self.proposal,"zone_basis":"pace"}
        answer = self.chat("Zie jij ook 2*(200m-100m)?").json()
        part = answer["results"][0]["parts"][0]
        self.assertTrue(part["e_usable"])
        self.assertIn("2×(200 m - 100 m)",part["training_fields"]["main"])
        self.assertTrue(part["e_validation"])
        model.return_value = {"reply":"De 95m in 43s is veel trager dan beide werkreps. Daarom is dat herstel.",
                              "proposal":None,"zone_basis":"pace"}
        second = self.chat("Waarom is lap 3 herstel?").json()["results"][0]["parts"][0]
        self.assertEqual(second["training_fields"],part["training_fields"])
        self.assertTrue(second["e_usable"])
        self.assertEqual(len(second["e_history"]),4)
        self.assertIn("Zie jij",model.call_args.args[1][0]["content"])

    @patch("core.views.garmin_e.ask_model")
    def test_boundary_only_model_update_reuses_measured_preview_reps(self, model):
        model.return_value = {
            "reply":"Lap 1 is de warming-up; de gemeten werkreps blijven behouden.",
            "intent":"update", "zone_basis":"pace",
            "proposal":{"warmup_laps":[1], "cooldown_laps":[], "recovery_laps":[]},
        }

        part = self.chat("Gebruik alleen lap 1 als WU en behoud de rest.").json()["results"][0]["parts"][0]

        self.assertTrue(part["e_usable"], part)
        self.assertEqual(part["training_fields"]["wu"], "1200 m Z1")
        self.assertIn("2×(200 m - 100 m)", part["training_fields"]["main"])
        self.assertIn("updated", part["e_update_note"])
        self.assertEqual(model.call_count, 1)

    @patch("core.views.garmin_e.ask_model")
    def test_chat_can_explicitly_ignore_a_measured_transition_lap(self, model):
        proposal = deepcopy(self.proposal)
        proposal["recovery_laps"] = [3, 7, 9]
        proposal["ignored_laps"] = [5]
        model.return_value = {
            "reply":"Lap 5 blijft zichtbaar als bronmeting maar telt niet mee in de training.",
            "intent":"update", "proposal":proposal, "zone_basis":"pace",
        }

        part = self.chat("Negeer lap 5 in de training.").json()["results"][0]["parts"][0]

        self.assertTrue(part["e_usable"], part)
        self.assertEqual(part["watch_loads"][4]["segment"], "IGNORE")
        self.assertIn("updated", part["e_update_note"])

    @patch("core.views.garmin_e.ask_model")
    def test_endpoint_prefers_eight_three_minute_reps_over_distance_guess(self, model):
        distances = [746.9, 767.8, 775.67, 783.19, 763.08, 753.62, 765.641, 786.32]
        laps = [{"distance":1783.44, "elapsed_time":572}]
        reps, recovery = [], []
        for position, meters in enumerate(distances):
            lap_id = len(laps) + 1
            laps.append({"distance":meters, "elapsed_time":180})
            reps.append({"laps":[lap_id], "target_meters":750 if position % 2 == 0 else 800})
            if position < len(distances) - 1:
                laps.append({"distance":195, "elapsed_time":75})
                recovery.append(len(laps))
        self.record.distance_m = sum(lap["distance"] for lap in laps)
        self.record.duration_s = sum(lap["elapsed_time"] for lap in laps)
        self.record.analysis_data = {"laps":laps}
        self.record.save()
        model.return_value = {
            "reply":"Ik zie afwisselend 750 en 800 meter.", "intent":"update", "zone_basis":"pace",
            "proposal":{"warmup_laps":[1], "recovery_laps":recovery, "reps":reps},
        }

        part = self.chat("Analyseer de training.").json()["results"][0]["parts"][0]

        self.assertTrue(part["e_usable"], part)
        self.assertIn("8×3'", part["training_fields"]["main"])
        self.assertNotIn("750 m", part["training_fields"]["main"])
        self.assertIn("shows timed reps", part["chat_reply"])

    @patch("core.views.garmin_e.ask_model")
    def test_question_does_not_produce_usable_training(self, model):
        model.return_value = {"reply":"Was het eerste blok een warming-up of al een werkblok?","proposal":None}
        result = self.chat("Dit was geen warming-up").json()["results"][0]["parts"][0]
        self.assertFalse(result["e_usable"])
        self.assertIn("werkblok",result["chat_reply"])

    @patch("core.views.garmin_e.ask_model")
    def test_retry_reuses_latest_explicit_set_request(self, model):
        model.return_value = {"reply": "Dit past.", "proposal": self.proposal, "zone_basis": "pace"}
        self.chat("Bekijk deze training")
        first = self.chat("Maak 1*(200m-100m)//1*(200m-100m)").json()["results"][0]["parts"][0]
        self.assertIn(" // 1×(", first["training_fields"]["main"])
        model.reset_mock()
        for message in ("probeer nu", "je zegt het maar je doet het niet"):
            result = self.chat(message).json()["results"][0]["parts"][0]
            self.assertEqual(result["training_fields"], first["training_fields"])
            self.assertIn("set structure", result["chat_reply"])
        model.assert_not_called()

    @patch("core.views.garmin_e.ask_model")
    def test_long_block_hr_request_reuses_checked_assignment(self, model):
        model.return_value = {"reply": "Dit past.", "proposal": self.proposal, "zone_basis": "pace"}
        initial = self.chat("Bekijk deze training").json()["results"][0]["parts"][0]
        self.assertTrue(initial["e_usable"])
        model.reset_mock()
        model.return_value = {"reply": "Eindhartslag voor lange blokken.", "intent": "zone_basis",
                              "zone_basis": "auto", "proposal": {"reps": []}}
        result = self.chat("kijk naar hr voor zones van de lange blokken").json()["results"][0]["parts"][0]
        self.assertEqual(result["e_zone_basis"], "auto")
        self.assertIn("eindhartslag", result["chat_reply"].lower())
        self.assertEqual([lap.get("ai_rep") for lap in result["watch_loads"]],
                         [lap.get("ai_rep") for lap in initial["watch_loads"]])
        model.assert_called_once()

    @patch("core.views.garmin_e.ask_model")
    def test_why_question_keeps_checked_preview_even_if_model_proposes_update(self, model):
        model.return_value = {"reply": "Dit past.", "proposal": self.proposal, "zone_basis": "pace"}
        initial = self.chat("Bekijk deze training").json()["results"][0]["parts"][0]
        self.assertTrue(initial["e_usable"])
        model.reset_mock()
        model.return_value = {"reply": "Deze zones komen uit het tempo.", "intent": "update",
                              "proposal": {"reps": []}, "zone_basis": "hr"}
        result = self.chat("Waarom krijgt 2*1000m Z1>Z3?").json()["results"][0]["parts"][0]
        self.assertEqual(result["chat_reply"], "Deze zones komen uit het tempo.")
        self.assertEqual(result["training_fields"], initial["training_fields"])
        self.assertEqual(result["watch_loads"], initial["watch_loads"])
        model.assert_called_once()

    @patch("core.views.garmin_e.ask_model")
    def test_unfulfilled_update_request_cannot_silently_look_applied(self, model):
        model.return_value = {"reply":"Dit past.","proposal":self.proposal}
        initial = self.chat("Bekijk deze training").json()["results"][0]["parts"][0]
        model.return_value = {"reply":"Ja, zo houden we het als voorstel.","proposal":None,"intent":"update"}
        result = self.chat("Ik wil het gecorrigeerde voorstel gebruiken").json()["results"][0]["parts"][0]
        self.assertEqual(result["training_fields"],initial["training_fields"])
        self.assertIn("unchanged",result["chat_reply"])
        self.assertIn("unchanged",result["e_update_note"])

    @patch("core.views.garmin_e.ask_model")
    def test_chat_zone_basis_switch_preserves_reps(self, model):
        self.athlete.zone_hr_bpm = {"1":"145","2":"146-160"}
        self.athlete.save()
        model.return_value = {"reply":"Ik gebruik snelheid.","proposal":self.proposal,"zone_basis":"pace"}
        initial = self.chat("Kijk naar snelheid").json()["results"][0]["parts"][0]
        model.return_value = {"reply":"Ik kijk nu naar de hartslag, dezelfde reps blijven staan.",
                              "proposal":None,"zone_basis":"hr"}
        changed = self.chat("Liever hartslag").json()["results"][0]["parts"][0]
        self.assertEqual(changed["e_zone_basis"],"hr")
        self.assertEqual([l.get("ai_rep") for l in changed["watch_loads"]],
                         [l.get("ai_rep") for l in initial["watch_loads"]])
        self.assertEqual(model.call_args.args[2]["zone_basis"],"pace")
        model.return_value = {"reply":"Terug naar snelheid.","proposal":None,"zone_basis":"pace"}
        restored = self.chat("Toch weer snelheid").json()["results"][0]["parts"][0]
        self.assertEqual(restored["training_fields"],initial["training_fields"])

    @patch("core.views.garmin_e.ask_model")
    def test_chat_applies_literal_user_zone_range_to_checked_preview(self, model):
        laps = [(1000, 300), (250, 50), (50, 60), (250, 49), (50, 60), (250, 48)]
        self.record.distance_m = sum(meters for meters, _seconds in laps)
        self.record.duration_s = sum(seconds for _meters, seconds in laps)
        self.record.analysis_data = {
            "laps":[{"distance":meters, "elapsed_time":seconds} for meters, seconds in laps],
        }
        self.record.save()
        proposal = {
            "warmup_laps":[1], "recovery_laps":[3, 5],
            "reps":[{"laps":[lap], "target_meters":250} for lap in (2, 4, 6)],
        }
        model.return_value = {
            "reply":"Ik zet de drie 250's op de gevraagde zoneopbouw.",
            "intent":"update", "proposal":proposal, "zone_basis":"pace",
        }

        result = self.chat("Die 3*250m was Z3-Z5").json()["results"][0]["parts"][0]

        self.assertTrue(result["e_usable"], result)
        self.assertIn("3×250 m Z3>Z5", result["training_fields"]["main"])
        self.assertIn("Proposal updated", result["e_update_note"])

    @patch("core.views.garmin_e.ask_model")
    def test_confirmation_keeps_unusable_preview_until_yes(self, model):
        model.return_value = {"reply":"Wil je deze indeling gebruiken?","proposal":self.proposal,
                              "confirmation_required":True,"zone_basis":"pace"}
        pending = self.chat("Is dit twee keer 200-100?").json()["results"][0]["parts"][0]
        self.assertFalse(pending["e_usable"])
        model.return_value = {"reply":"De indeling is bevestigd; de tijden blijven gemeten.",
                              "proposal":None,"zone_basis":"pace"}
        accepted = self.chat("ja").json()["results"][0]["parts"][0]
        self.assertTrue(accepted["e_usable"])
        self.assertIn("2×(200 m - 100 m)",accepted["training_fields"]["main"])

    @patch("core.views.garmin_e.ask_model")
    def test_failed_validation_and_service_leave_checked_preview(self, model):
        model.return_value = {"reply":"Dit past.","proposal":self.proposal}
        good = self.chat("Bekijk de training").json()["results"][0]["parts"][0]
        bad = deepcopy(self.proposal)
        bad["reps"][0]["target_meters"] = 800
        model.return_value = {"reply":"Laten we dit controleren.","proposal":bad}
        rejected = self.chat("Maak die 200 een 800").json()["results"][0]["parts"][0]
        self.assertEqual(rejected["training_fields"],good["training_fields"])
        self.assertIn("could not be applied",rejected["chat_reply"])
        model.side_effect = OSError("unavailable")
        unavailable = self.chat("En nu?").json()["results"][0]["parts"][0]
        self.assertEqual(unavailable["training_fields"],good["training_fields"])
        self.assertTrue(unavailable["e_usable"])

    @patch("core.views.garmin_e.ask_model")
    def test_model_timeout_retries_once_with_shorter_low_budget_request(self, model):
        model.side_effect = [
            TimeoutError("first request timed out"),
            {"reply":"De gemeten indeling is compleet.", "proposal":self.proposal, "zone_basis":"pace"},
        ]

        part = self.chat("Bekijk de hele moeilijke opname opnieuw.").json()["results"][0]["parts"][0]

        self.assertTrue(part["e_usable"], part)
        self.assertEqual(model.call_count, 2)
        self.assertEqual(model.call_args_list[0].kwargs["timeout"], 16)
        self.assertLessEqual(model.call_args_list[1].kwargs["timeout"], 8)
        self.assertIn("previous service request timed out", model.call_args_list[1].args[3])

    @patch("core.views.garmin_e.ask_model")
    @patch("core.views.garmin_e.localize_garmin_e_notice", return_value="Garmin E kreeg niet op tijd antwoord.")
    def test_repeated_model_timeout_reports_time_limit_and_keeps_conversation(self, translate, model):
        model.side_effect = TimeoutError("still timed out")

        part = self.chat("Analyseer deze opname.").json()["results"][0]["parts"][0]

        self.assertFalse(part["e_usable"])
        self.assertEqual(model.call_count, 2)
        self.assertIn("niet op tijd antwoord", part["chat_reply"])
        self.assertEqual(translate.call_args.args[1], "Analyseer deze opname.")

    @patch("core.views.garmin_e.ask_model")
    def test_default_availability_does_not_bypass_access_or_consent(self, model):
        diary = reverse("athlete_year_calendar")+"?"+urlencode({"athlete":self.athlete.pk,"year":2026})
        self.athlete.garmin_ai_consent_at = None
        self.athlete.save()
        diary_response = self.client.get(diary)
        self.assertContains(diary_response,'id="suggestInputBtnE"')
        self.assertContains(
            diary_response,
            'var canDiscussGarminE = model === "E" && (part.watch_loads || []).length;',
            html=False,
        )
        self.assertContains(
            diary_response,
            'if (hasUsableTrainingFields || canDiscussGarminE)',
            html=False,
        )
        result = self.client.get(self.url,self.query).json()["results"][0]["parts"][0]
        self.assertFalse(result["e_usable"])
        model.assert_not_called()
        other = get_user_model().objects.create_user(username="other-e-coach",is_staff=True)
        self.client.force_login(other)
        self.assertEqual(self.client.get(self.url,self.query).status_code,404)

    @patch("core.views.garmin_e.ask_model")
    def test_save_checked_e_preview_and_reject_tampering(self, model):
        model.return_value = {"reply":"Dit zijn twee paren.","proposal":self.proposal,"zone_basis":"pace"}
        part = self.chat("Bekijk dit").json()["results"][0]["parts"][0]
        fields = part["training_fields"]
        payload = {"watch_origin":"watch_e","watch_loads":json.dumps(part["watch_loads"]),
                   "watch_validation":part["e_validation"],"wu_text":fields["wu"],
                   "core_text":fields["main"],"cd_text":fields["cd"]}
        # JSON.stringify in the browser serializes 38.0 as 38, recursively.
        def browser_numbers(value):
            if isinstance(value,list):
                return [browser_numbers(v) for v in value]
            if isinstance(value,dict):
                return {k:browser_numbers(v) for k,v in value.items()}
            if isinstance(value,float) and value.is_integer():
                return int(value)
            return value
        payload["watch_loads"] = json.dumps(browser_numbers(part["watch_loads"]))
        url = reverse("slot_modal",args=[2026,11,14,1])+"?"+urlencode({"athlete":self.athlete.pk,"source":"athlete_year"})
        self.assertEqual(self.client.post(url,dict(payload,core_text="99×1000 m Z5")).status_code,400)
        self.assertEqual(self.client.post(url,payload).status_code,200)
        from core.models import TrainingSlot
        slot = TrainingSlot.objects.filter(athlete=self.athlete,source="watch_e").first()
        self.assertIsNotNone(slot)
        self.assertEqual(len(slot.watch_main_reps),4)
        pm_url = reverse("slot_modal",args=[2026,11,14,2])+"?"+urlencode({"athlete":self.athlete.pk,"source":"athlete_year"})
        self.assertEqual(self.client.post(pm_url,{"alt_text":"Bike 60' Z1"}).status_code,200)
        self.assertEqual(self.client.post(pm_url,dict(payload,watch_fields="running_add")).status_code,200)
        pm = TrainingSlot.objects.filter(athlete=self.athlete,date="2026-11-14",slot_index=2,source="watch_e").first()
        self.assertIsNotNone(pm)
        self.assertTrue(pm.segments.filter(type="ALT",text__contains="Bike").exists())
        self.assertEqual(len(pm.watch_main_reps),4)
