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

from core.garmin_e import checked_proposal, ask_model, lap_facts
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
        self.assertEqual(body["response_format"],{"type":"json_object"})


@override_settings(GARMIN_CLIENT_ID="test",GARMIN_CLIENT_SECRET="test",GARMIN_REDIRECT_URI="https://example.org/callback/")
class GarminEEndpointTests(TestCase):
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
    def test_question_does_not_produce_usable_training(self, model):
        model.return_value = {"reply":"Was het eerste blok een warming-up of al een werkblok?","proposal":None}
        result = self.chat("Dit was geen warming-up").json()["results"][0]["parts"][0]
        self.assertFalse(result["e_usable"])
        self.assertIn("werkblok",result["chat_reply"])

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
