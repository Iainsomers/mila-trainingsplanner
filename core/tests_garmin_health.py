import json

from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from core.models import Athlete, AthleteDailyVital, GarminConnection
from core.views.garmin import health_receiver_key, receiver_key


@override_settings(
    GARMIN_CLIENT_ID="test-client",
    GARMIN_CLIENT_SECRET="test-secret",
    GARMIN_REDIRECT_URI="https://example.org/callback/",
)
class GarminHealthPushTests(TestCase):
    def setUp(self):
        self.coach = get_user_model().objects.create_user(
            username="health-coach", is_staff=True,
        )
        self.athlete = Athlete.objects.create(
            owner=self.coach, name="Health Runner", birth_year=2000,
            gender="X", garmin_connection_enabled=True,
        )
        GarminConnection.objects.create(
            athlete=self.athlete, garmin_user_id="health-user-1",
            access_token="private-access", data_consent_at=timezone.now(),
        )
        self.url = reverse("garmin_health_push", args=[health_receiver_key()])

    def push(self, payload, url=None):
        return self.client.post(
            url or self.url, json.dumps(payload), content_type="application/json",
        )

    def test_three_health_feeds_fill_the_four_vitals(self):
        payload = {
            "sleeps": [{
                "userId": "health-user-1", "calendarDate": "2026-11-10",
                "durationInSeconds": 27_090, "overallSleepScore": {"value": 83, "qualifierKey": "GOOD"},
            }],
            "hrv": [{
                "userId": "health-user-1", "calendarDate": "2026-11-10",
                "lastNightAvg": 58.6, "lastNight5MinHigh": 82,
            }],
            "dailies": [{
                "userId": "health-user-1", "calendarDate": "2026-11-10",
                "restingHeartRateInBeatsPerMinute": 41,
            }],
        }
        self.assertEqual(self.push(payload).status_code, 200)
        vital = AthleteDailyVital.objects.get(athlete=self.athlete, date="2026-11-10")
        self.assertEqual(vital.sleep_hours, 7.53)
        self.assertEqual(float(vital.sleep_quality), 8.3)
        self.assertEqual(vital.morning_hr, 41)
        self.assertEqual(vital.hrv, 59)
        self.assertIsNone(vital.updated_by)

    def test_retries_and_later_feeds_preserve_existing_values(self):
        AthleteDailyVital.objects.create(
            athlete=self.athlete, date="2026-11-10", sleep_hours=6.25, hrv=70,
        )
        payload = {
            "sleeps": [{
                "userId": "health-user-1", "calendarDate": "2026-11-10",
                "durationInSeconds": 28_800, "overallSleepScore": {"value": 91},
            }],
            "hrv": [{
                "userId": "health-user-1", "calendarDate": "2026-11-10", "lastNightAvg": 44,
            }],
        }
        self.assertEqual(self.push(payload).status_code, 200)
        self.assertEqual(self.push(payload).status_code, 200)
        vital = AthleteDailyVital.objects.get(athlete=self.athlete, date="2026-11-10")
        self.assertEqual(vital.sleep_hours, 6.25)
        self.assertEqual(float(vital.sleep_quality), 9.1)
        self.assertEqual(vital.hrv, 70)
        self.assertEqual(AthleteDailyVital.objects.count(), 1)

    def test_unknown_or_disabled_athlete_is_ignored(self):
        payload = {"dailies": [{
            "userId": "unknown", "calendarDate": "2026-11-10",
            "restingHeartRateInBeatsPerMinute": 45,
        }]}
        self.assertEqual(self.push(payload).status_code, 200)
        self.athlete.garmin_connection_enabled = False
        self.athlete.save(update_fields=["garmin_connection_enabled"])
        payload["dailies"][0]["userId"] = "health-user-1"
        self.assertEqual(self.push(payload).status_code, 200)
        self.assertFalse(AthleteDailyVital.objects.exists())

    def test_private_health_key_validation_and_payload_limits(self):
        wrong = reverse("garmin_health_push", args=["wrong-key"])
        payload = {"dailies": []}
        self.assertEqual(self.push(payload, wrong).status_code, 403)
        self.assertNotEqual(health_receiver_key(), receiver_key())
        secure_client = Client(enforce_csrf_checks=True)
        self.assertEqual(secure_client.post(
            self.url, json.dumps(payload), content_type="application/json",
        ).status_code, 200)
        self.assertEqual(self.client.get(self.url).status_code, 405)
        self.assertEqual(self.client.post(
            self.url, " " * 1_000_001, content_type="application/json",
        ).status_code, 413)

    def test_invalid_envelopes_and_records_create_nothing(self):
        invalid_payloads = [
            {}, {"activities": []}, {"sleeps": {}},
            {"sleeps": [{"userId": "health-user-1", "calendarDate": "not-a-date"}]},
            {"dailies": [{"userId": "health-user-1", "calendarDate": "2026-11-10",
                           "restingHeartRateInBeatsPerMinute": True}]},
        ]
        for payload in invalid_payloads[:-1]:
            self.assertEqual(self.push(payload).status_code, 400)
        # A structurally valid record with an unusable optional metric is accepted but writes nothing.
        self.assertEqual(self.push(invalid_payloads[-1]).status_code, 200)
        self.assertFalse(AthleteDailyVital.objects.exists())

    def test_health_url_is_visible_only_to_product_administrator(self):
        self.client.force_login(self.coach)
        page = self.client.get(reverse("garmin_connections"))
        self.assertNotContains(page, health_receiver_key())
        administrator = get_user_model().objects.create_user(
            username="health-admin", is_superuser=True, is_staff=True,
        )
        self.client.force_login(administrator)
        page = self.client.get(reverse("garmin_connections"))
        self.assertContains(page, self.url)
        self.assertContains(page, "HEALTH – Dailies")
        self.assertEqual(page["Cache-Control"], "private, no-store")
