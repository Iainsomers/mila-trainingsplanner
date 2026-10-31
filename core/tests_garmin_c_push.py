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
        self.assertEqual(GarminActivitySummary.objects.get().analysis_data, before)

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
