import json
from datetime import datetime, timezone as dt_timezone
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from core.models import Athlete, GarminConnection, GarminActivitySummary
from core.views.garmin import receiver_key


@override_settings(GARMIN_CLIENT_ID="test-id", GARMIN_CLIENT_SECRET="test-secret", GARMIN_REDIRECT_URI="https://example.org/callback/")
class GarminCPushTests(TestCase):
    def setUp(self):
        self.coach = get_user_model().objects.create_user(username="garmin-c-coach", is_staff=True)
        self.athlete = Athlete.objects.create(owner=self.coach, name="Garmin C runner", birth_year=2000,
            gender="X", garmin_connection_enabled=True)
        GarminConnection.objects.create(athlete=self.athlete, garmin_user_id="runner-id", access_token="private-token", data_consent_at=timezone.now())
        self.start = int(datetime(2026, 10, 31, 10, tzinfo=dt_timezone.utc).timestamp())
        self.summary = {"userId": "runner-id", "activityId": 456, "summaryId": "summary-456",
            "startTimeInSeconds": self.start, "distanceInMeters": 1000, "durationInSeconds": 300}
        self.push_url = reverse("garmin_activity_push", args=[receiver_key()])

    def send(self, payload):
        return self.client.post(self.push_url, json.dumps(payload), content_type="application/json")

    def read_c(self, **query):
        self.client.force_login(self.coach)
        return self.client.get(reverse("garmin_type_c_ayc"), {"athlete": self.athlete.pk, "date": "2026-10-31", **query})

    def details(self):
        return {"userId": "runner-id", "activityId": 456, "summaryId": "summary-456-detail",
            "summary": self.summary,
            "samples": [{"startTimeInSeconds": self.start + t, "totalDistanceInMeters": meters,
                "heartRate": hr, "latitudeInDegree": 52.0} for t, meters, hr in (
                    (0, 0, 100), (100, 400, 140), (150, 500, 150), (200, 600, 160), (290, 980, 170), (300, 1000, 170))],
            "laps": [{"startTimeInSeconds": self.start}, {"startTimeInSeconds": self.start + 150}]}

    @patch("core.views.polar_raw.translate_model_b", return_value=[])
    def test_timer_pause_facts_survive_push_and_reach_recognition(self, translate):
        details = self.details()
        for sample, timer in zip(details["samples"], (0, 100, 120, 170, 260, 270)):
            sample["clockDurationInSeconds"] = sample["startTimeInSeconds"] - self.start
            sample["timerDurationInSeconds"] = timer
            sample["movingDurationInSeconds"] = timer
        self.assertEqual(self.send({"activityDetails": [details]}).status_code, 200)
        saved = GarminActivitySummary.objects.get().analysis_data
        self.assertEqual(saved["laps"][0]["timer_time"], 120)
        self.assertEqual(saved["laps"][0]["paused_time"], 30)
        self.assertEqual(saved["laps"][1]["paused_time"], 0)
        self.assertNotIn("latitudeInDegree", json.dumps(saved))
        self.read_c()
        laps = translate.call_args.args[0][0]["laps"]["laps"]
        self.assertEqual(laps[0]["pausedDurationMillis"], 30000)
        self.assertEqual(laps[0]["timerDurationMillis"], 120000)

    def test_unknown_or_reset_timer_is_not_reported_as_zero_pause(self):
        for reset in (False, True):
            details = self.details()
            if reset:
                for sample, timer in zip(details["samples"], (0, 100, 20, 70, 160, 170)):
                    sample["timerDurationInSeconds"] = timer
            self.send({"activityDetails": [details]})
            for lap in GarminActivitySummary.objects.get().analysis_data["laps"]:
                self.assertNotIn("paused_time", lap)

    @patch("core.views.polar_raw.lap_zone_paces", return_value=("Z1", "NA"))
    def test_long_run_with_two_slow_kilometres_is_one_block_in_garmin_c(self, zones):
        laps = [{"distance": 1000, "elapsed_time": 600 if index in (9, 18) else 260} for index in range(27)]
        laps.append({"distance": 300, "elapsed_time": 80})
        GarminActivitySummary.objects.create(athlete=self.athlete, activity_id="long-run",
            activity_start=datetime.fromtimestamp(self.start, dt_timezone.utc), activity_date="2026-10-31",
            distance_m=27300, analysis_data={"laps": laps})
        result = self.read_c().json()["results"][0]["parts"][0]
        self.assertEqual(result["training_fields"]["main"], "27300 m Z1")
        self.assertEqual(len(result["manual"]), 28)

    @patch("core.views.polar_raw._model_b_ai_description")
    def test_old_received_summary_is_visible_without_invented_laps_or_use_actions(self, ai):
        GarminActivitySummary.objects.create(athlete=self.athlete, activity_id="short-test",
            activity_start=datetime.fromtimestamp(self.start, dt_timezone.utc), activity_date="2026-10-31", distance_m=60)
        data = self.read_c().json()
        self.assertTrue(data["ok"])
        self.assertEqual(data["results"][0]["distance"], "60")
        self.assertEqual(data["results"][0]["parts"][0]["manual"], [])
        self.assertNotIn("training_fields", data["results"][0]["parts"][0])
        ai.assert_not_called()

    @patch("core.views.polar_raw._model_b_ai_description")
    def test_detail_push_flows_into_garmin_c_measured_laps_and_hr(self, ai):
        self.assertEqual(self.send({"activityDetails": [self.details()]}).status_code, 200)
        saved = GarminActivitySummary.objects.get()
        self.assertEqual(saved.duration_s, 300)
        self.assertEqual([lap["distance"] for lap in saved.analysis_data["laps"]], [500, 500])
        self.assertNotIn("latitudeInDegree", json.dumps(saved.analysis_data))
        data = self.read_c().json()
        self.assertTrue(data["ok"])
        self.assertEqual(len(data["results"]), 1)
        self.assertEqual(len(data["results"][0]["parts"][0]["manual"]), 2)
        self.assertEqual(data["results"][0]["parts"][0]["manual"][0]["distance"], "500")
        ai.assert_not_called()  # Data consent alone never enables OpenAI.

    def test_summary_retry_does_not_erase_already_received_lap_details(self):
        self.send({"activityDetails": [self.details()]})
        before = GarminActivitySummary.objects.get().analysis_data
        self.send({"activities": [self.summary]})
        self.send({"activityDetails": [self.details()]})
        self.assertEqual(GarminActivitySummary.objects.count(), 1)
        self.assertEqual(GarminActivitySummary.objects.get().analysis_data["laps"], before["laps"])

    @patch("core.views.polar_raw.lap_zone_paces", return_value=("Z2", "NA"))
    def test_short_sets_continuous_block_and_cooldown_reach_c_with_measured_loads(self, zones):
        from core.tests_watch_structure import workout
        for cooldown in (False, True):
            rows = workout(cooldown)
            GarminActivitySummary.objects.update_or_create(athlete=self.athlete, activity_id="structure",
                defaults={"activity_start": datetime.fromtimestamp(self.start, dt_timezone.utc),
                    "activity_date": "2026-10-31", "distance_m": sum(row["distanceMeters"] for row in rows),
                    "analysis_data": {"laps": [{"distance": row["distanceMeters"],
                        "elapsed_time": row["durationMillis"] / 1000} for row in rows]}})
            part = self.read_c().json()["results"][0]["parts"][0]
            self.assertEqual(part["training_fields"]["main"], "2*(5*100m z2) p45//3750m z2")
            self.assertEqual(part["training_fields"]["cd"], "2000m" if cooldown else "")
            self.assertEqual(len(part["manual"]), len(rows))
            loads = part["watch_loads"]
            self.assertEqual(sum(load["meters"] for load in loads), sum(row["distanceMeters"] for row in rows))
            self.assertTrue(all(load["segment"] == "CORE" for load in loads[:26]))
            self.assertTrue(all(load["segment"] == "CD" for load in loads[26:]))

    def test_missing_sample_coverage_does_not_invent_intermediate_laps(self):
        details = self.details()
        details["samples"] = []
        self.assertEqual(self.send({"activityDetails": [details]}).status_code, 200)
        self.assertEqual(GarminActivitySummary.objects.get().analysis_data["laps"], [])

    def test_garmin_c_respects_day_and_athlete_access(self):
        self.send({"activityDetails": [self.details()]})
        self.assertEqual(self.read_c(date="2026-10-30").json()["results"], [])
        other = get_user_model().objects.create_user(username="other-c-coach", is_staff=True)
        self.client.force_login(other)
        response = self.client.get(reverse("garmin_type_c_ayc"), {"athlete": self.athlete.pk, "date": "2026-10-31"})
        self.assertEqual(response.status_code, 404)

    def test_invalid_details_do_not_save_partial_summary(self):
        details = self.details()
        details["summary"]["durationInSeconds"] = -1
        self.assertEqual(self.send({"activityDetails": [details]}).status_code, 400)
        self.assertFalse(GarminActivitySummary.objects.exists())

    @patch("core.views.polar_raw._model_b_ai_description")
    def test_uploaded_fit_still_works_and_is_not_duplicated_by_matching_push(self, ai):
        from core.models import GarminActivity
        self.send({"activities": [self.summary]})
        GarminActivity.objects.create(athlete=self.athlete,
            activity_start=datetime.fromtimestamp(self.start, dt_timezone.utc),
            original_filename="run.fit", file_hash="fit-test", raw_file=b"",
            parsed_data={"total_distance_m": 1000, "total_elapsed_s": 300,
                "laps": [{"distance": 500, "elapsed_time": 150}, {"distance": 500, "elapsed_time": 150}]})
        results = self.read_c().json()["results"]
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["name"], "run.fit")
        self.assertEqual(len(results[0]["parts"][0]["manual"]), 2)

    def test_details_without_laps_are_not_misreported_as_missing_delivery(self):
        details = self.details()
        details["laps"] = []
        self.send({"activityDetails": [details]})
        result = self.read_c().json()["results"][0]
        self.assertEqual(result["detail_status"], "details_without_usable_laps")
        description = result["parts"][0]["description"]
        self.assertIn("have been received", description)
        self.assertIn("no recorded lap boundaries", description)
        self.assertNotIn("enable Activity Details", description)
        self.assertIn("Last detail delivery:", description)

    def test_resend_replaces_summary_status_and_keeps_all_three_runs_in_time_order(self):
        first = {**self.summary, "activityId": 111, "startTimeInSeconds": self.start - 600}
        self.send({"activities": [first]})
        self.send({"activityDetails": [self.details()]})
        third = {**self.summary, "activityId": 999, "startTimeInSeconds": self.start + 600}
        self.send({"activities": [third]})
        results = self.read_c().json()["results"]
        self.assertEqual([r["name"] for r in results], ["Garmin activity 111", "Garmin activity 456", "Garmin activity 999"])
        self.assertEqual(results[0]["detail_status"], "summary_only")
        details = self.details()
        details["activityId"] = 111
        details["summary"] = {**self.summary, "startTimeInSeconds": self.start - 600}
        details["laps"] = []
        self.send({"activityDetails": [details]})
        results = self.read_c().json()["results"]
        self.assertEqual(len(results), 3)
        self.assertEqual(results[0]["detail_status"], "details_without_usable_laps")

    def test_rejected_detail_logs_safe_schema_not_personal_values(self):
        details = self.details()
        details["summary"].pop("durationInSeconds")
        details["summary"]["activityName"] = "PRIVATE TRAINING NAME"
        details["userAccessToken"] = "PRIVATE TOKEN"
        with self.assertLogs("core.views.garmin", level="WARNING") as logs:
            self.assertEqual(self.send({"activityDetails": [details]}).status_code, 400)
        output = " ".join(logs.output)
        self.assertIn("kind=activityDetails", output)
        self.assertIn("reason=Missing activity totals", output)
        self.assertIn("durationInSeconds=missing", output)
        for secret in ("PRIVATE TRAINING NAME", "PRIVATE TOKEN", "runner-id", receiver_key()):
            self.assertNotIn(secret, output)
        self.assertFalse(GarminActivitySummary.objects.exists())

    def test_detail_without_distance_does_not_block_other_activities_in_batch(self):
        from copy import deepcopy
        stationary = deepcopy(self.details())
        stationary["activityId"] = 111
        stationary["summary"].pop("distanceInMeters")
        response = self.send({"activityDetails": [stationary, self.details()]})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(GarminActivitySummary.objects.count(), 2)
        missing = GarminActivitySummary.objects.get(activity_id="111")
        self.assertIsNone(missing.distance_m)
        self.assertEqual(missing.analysis_data["lap_data_status"], "missing_distance")
        self.assertEqual(missing.analysis_data["laps"], [])
        self.assertTrue(missing.analysis_data["details_received_at"])
        usable = GarminActivitySummary.objects.get(activity_id="456")
        self.assertEqual([lap["distance"] for lap in usable.analysis_data["laps"]], [500, 500])
        results = self.read_c().json()["results"]
        self.assertTrue(any("no total distance" in result["parts"][0]["description"] for result in results if result.get("detail_status")))

    def test_missing_distance_detail_preserves_existing_summary_distance(self):
        self.send({"activities": [self.summary]})
        details = self.details()
        details["summary"].pop("distanceInMeters")
        self.assertEqual(self.send({"activityDetails": [details]}).status_code, 200)
        saved = GarminActivitySummary.objects.get()
        self.assertEqual(saved.distance_m, 1000)
        self.assertEqual(saved.analysis_data["laps"], [])

    def test_successful_details_receipt_reports_laps_with_private_reference(self):
        import hashlib
        with self.assertLogs("core.views.garmin", level="INFO") as logs:
            response = self.send({"activityDetails": [self.details()]})
        self.assertEqual(response.status_code, 200)
        output = " ".join(logs.output)
        self.assertIn("activity_ref=" + hashlib.sha256(b"456").hexdigest()[:12], output)
        self.assertIn("outcome=details_stored usable_laps=2 supplied_laps=2", output)
        self.assertNotIn("runner-id", output)
        self.assertNotIn("private-token", output)
        self.assertNotIn(receiver_key(), output)
