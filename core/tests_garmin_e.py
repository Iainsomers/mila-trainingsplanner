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
    lap_facts,
    prefer_measured_time_groups,
)
from core.models import Athlete, GarminActivitySummary
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
        answer = ask_model(lap_facts(part),history,{"zone_basis":"pace"})
        self.assertIn("tweede blok",answer["reply"])
        body = json.loads(urlopen.call_args.args[0].data)
        self.assertEqual(body["messages"][-1],history[-1])
        self.assertFalse(body["store"])
        self.assertEqual(body["reasoning_effort"], "low")
        self.assertEqual(body["response_format"],{"type":"json_object"})


@override_settings(GARMIN_CLIENT_ID="test",GARMIN_CLIENT_SECRET="test",GARMIN_REDIRECT_URI="https://example.org/callback/")
class GarminEEndpointTests(TestCase):
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
        self.assertEqual(part["training_fields"]["alt"],"Elliptical 60' Z1")
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
        self.assertIn("3603s",part["training_fields"]["alt"])
        self.assertIn("no usable HR",part["e_zone_note"])
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
        response = self.client.post(self.url+"?"+urlencode(self.query),{"combine":json.dumps(selection)})
        self.assertEqual(response.status_code,200,response.json())
        combined = response.json()["results"][0]
        part = combined["parts"][0]
        self.assertEqual(model.call_count,calls)
        self.assertTrue(part["e_usable"],part)
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
            garmin_model_e_enabled=True,garmin_connection_enabled=True,
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
        self.assertIn("bijgewerkt",part["e_update_note"])
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
        self.assertIn("bijgewerkt", part["e_update_note"])
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
        self.assertIn("bijgewerkt", part["e_update_note"])

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
        self.assertIn("daarom toont", part["chat_reply"])

    @patch("core.views.garmin_e.ask_model")
    def test_question_does_not_produce_usable_training(self, model):
        model.return_value = {"reply":"Was het eerste blok een warming-up of al een werkblok?","proposal":None}
        result = self.chat("Dit was geen warming-up").json()["results"][0]["parts"][0]
        self.assertFalse(result["e_usable"])
        self.assertIn("werkblok",result["chat_reply"])

    @patch("core.views.garmin_e.ask_model")
    def test_unfulfilled_update_request_cannot_silently_look_applied(self, model):
        model.return_value = {"reply":"Dit past.","proposal":self.proposal}
        initial = self.chat("Bekijk deze training").json()["results"][0]["parts"][0]
        model.return_value = {"reply":"Ja, zo houden we het als voorstel.","proposal":None,"intent":"update"}
        result = self.chat("Ik wil het gecorrigeerde voorstel gebruiken").json()["results"][0]["parts"][0]
        self.assertEqual(result["training_fields"],initial["training_fields"])
        self.assertIn("nog niet bijgewerkt",result["chat_reply"])
        self.assertIn("ongewijzigd",result["e_update_note"])

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
        self.assertIn("Voorstel bijgewerkt", result["e_update_note"])

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
        self.assertIn("niet toepassen",rejected["chat_reply"])
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
    def test_repeated_model_timeout_reports_time_limit_and_keeps_conversation(self, model):
        model.side_effect = TimeoutError("still timed out")

        part = self.chat("Analyseer deze opname.").json()["results"][0]["parts"][0]

        self.assertFalse(part["e_usable"])
        self.assertEqual(model.call_count, 2)
        self.assertIn("niet op tijd antwoord", part["chat_reply"])

    @patch("core.views.garmin_e.ask_model")
    def test_opt_in_access_and_consent(self, model):
        self.athlete.garmin_model_e_enabled = False
        self.athlete.save()
        self.assertEqual(self.client.get(self.url,self.query).status_code,403)
        diary = reverse("athlete_year_calendar")+"?"+urlencode({"athlete":self.athlete.pk,"year":2026})
        self.assertNotContains(self.client.get(diary),'id="suggestInputBtnE"')
        self.athlete.garmin_model_e_enabled = True
        self.athlete.garmin_ai_consent_at = None
        self.athlete.save()
        self.assertContains(self.client.get(diary),'id="suggestInputBtnE"')
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
        self.athlete.garmin_model_e_enabled = False
        self.athlete.save()
        self.assertEqual(self.client.post(url,payload).status_code,403)
