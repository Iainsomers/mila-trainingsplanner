from datetime import date
from urllib.parse import parse_qs, urlsplit
from unittest.mock import Mock, patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from core.models import Athlete, AthleteDailyVital, OuraConnection


@override_settings(
    OURA_CLIENT_ID="test-client-id",
    OURA_CLIENT_SECRET="test-client-secret",
    OURA_REDIRECT_URI="https://mila-trainingsplanner.onrender.com/integrations/oura/callback/",
)
class OuraDashboardAndOAuthTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.coach = User.objects.create_user(username="coach-owner", password="pw", is_staff=True)
        self.athlete_user = User.objects.create_user(
            username="runner-one",
            password="pw",
            first_name="Runner",
            last_name="One",
        )
        self.athlete = Athlete.objects.create(
            owner=self.coach,
            name="Runner One",
            birth_year=2010,
            gender="V",
            oura_connection_enabled=True,
            daily_vitals_enabled=True,
        )
        self.client.force_login(self.athlete_user)

    def test_athlete_dashboard_has_a_separate_hardware_settings_oura_block(self):
        response = self.client.get(reverse("dashboard"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Hardware settings")
        self.assertContains(response, "Oura connection")
        self.assertContains(response, reverse("oura_connect"))

    def test_oura_import_button_is_shown_on_the_athletes_ayc_when_vitals_are_available(self):
        OuraConnection.objects.create(
            athlete=self.athlete,
            access_token="access-token",
            scope="daily",
            health_data_consent_at="2026-10-29T08:00:00+00:00",
        )

        response = self.client.get(reverse("athlete_year_calendar"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Use Oura data")
        self.assertContains(response, reverse("oura_vitals_import"))

    def test_oura_settings_are_hidden_and_connect_is_blocked_when_coach_disables_them(self):
        self.athlete.oura_connection_enabled = False
        self.athlete.save(update_fields=["oura_connection_enabled"])

        response = self.client.get(reverse("dashboard"))
        connect_response = self.client.post(
            reverse("oura_connect"),
            {"consent_oura_data": "on", "confirm_adult_or_guardian": "on"},
        )

        self.assertNotContains(response, "Hardware settings")
        self.assertNotContains(response, "Oura connection")
        self.assertRedirects(connect_response, f"{reverse('dashboard')}?oura=not_enabled", fetch_redirect_response=False)
        self.assertFalse(OuraConnection.objects.exists())

    def test_connect_requires_both_health_and_guardian_confirmations(self):
        response = self.client.post(reverse("oura_connect"), {"consent_oura_data": "on"})

        self.assertRedirects(response, f"{reverse('dashboard')}?oura=guardian_required", fetch_redirect_response=False)
        self.assertFalse(OuraConnection.objects.exists())

    def test_connect_starts_minimum_scope_pkce_oauth_flow(self):
        response = self.client.post(
            reverse("oura_connect"),
            {"consent_oura_data": "on", "confirm_adult_or_guardian": "on"},
        )

        self.assertEqual(response.status_code, 302)
        query = parse_qs(urlsplit(response["Location"]).query)
        self.assertEqual(query["scope"], ["daily"])
        self.assertEqual(query["redirect_uri"], ["https://mila-trainingsplanner.onrender.com/integrations/oura/callback/"])
        self.assertEqual(query["code_challenge_method"], ["S256"])
        self.assertTrue(query["state"][0])
        self.assertTrue(query["code_challenge"][0])

    @patch("core.views.oura.requests.post")
    def test_callback_saves_tokens_for_the_current_athlete_after_state_validation(self, mocked_post):
        self.client.post(
            reverse("oura_connect"),
            {"consent_oura_data": "on", "confirm_adult_or_guardian": "on"},
        )
        session = self.client.session
        state = session["oura_oauth_pending"]["state"]
        mocked_response = Mock()
        mocked_response.json.return_value = {
            "access_token": "access-token",
            "refresh_token": "refresh-token",
            "expires_in": 3600,
            "scope": "daily heartrate",
        }
        mocked_response.raise_for_status.return_value = None
        mocked_post.return_value = mocked_response

        response = self.client.get(reverse("oura_callback"), {"code": "auth-code", "state": state})

        self.assertRedirects(response, f"{reverse('dashboard')}?oura=connected", fetch_redirect_response=False)
        connection = OuraConnection.objects.get(athlete=self.athlete)
        self.assertEqual(connection.access_token, "access-token")
        self.assertEqual(connection.refresh_token, "refresh-token")
        self.assertEqual(connection.consented_by, self.athlete_user)
        self.assertTrue(connection.adult_or_guardian_permission_confirmed)
        mocked_post.assert_called_once()

    @patch("core.views.oura.requests.post")
    def test_callback_rejects_a_mismatched_state(self, mocked_post):
        self.client.post(
            reverse("oura_connect"),
            {"consent_oura_data": "on", "confirm_adult_or_guardian": "on"},
        )

        response = self.client.get(
            reverse("oura_callback"),
            {"code": "auth-code", "state": "wrong-state"},
        )

        self.assertRedirects(response, f"{reverse('dashboard')}?oura=authorization_failed", fetch_redirect_response=False)
        self.assertFalse(OuraConnection.objects.exists())
        mocked_post.assert_not_called()

    def test_disconnect_removes_local_connection_and_revokes_remote_token(self):
        OuraConnection.objects.create(
            athlete=self.athlete,
            access_token="access-token",
            health_data_consent_at="2026-10-29T08:00:00+00:00",
        )

        with patch("core.views.oura.requests.get") as mocked_get:
            response = self.client.post(reverse("oura_disconnect"))

        self.assertRedirects(response, f"{reverse('dashboard')}?oura=disconnected", fetch_redirect_response=False)
        self.assertFalse(OuraConnection.objects.exists())
        mocked_get.assert_called_once()

    @patch("core.views.oura.requests.get")
    def test_coach_oura_test_window_previews_recent_data_without_saving_it(self, mocked_get):
        OuraConnection.objects.create(
            athlete=self.athlete,
            access_token="access-token",
            scope="daily",
            health_data_consent_at="2026-10-29T08:00:00+00:00",
        )
        sleep_response = Mock()
        sleep_response.status_code = 200
        sleep_response.raise_for_status.return_value = None
        sleep_response.json.return_value = {"data": [{
            "day": "2026-10-28",
            "type": "long_sleep",
            "total_sleep_duration": 27000,
            "lowest_heart_rate": 47.8,
            "average_hrv": 72.4,
        }], "next_token": None}
        daily_sleep_response = Mock()
        daily_sleep_response.raise_for_status.return_value = None
        daily_sleep_response.json.return_value = {"data": [{"day": "2026-10-28", "score": 82}], "next_token": None}
        readiness_response = Mock()
        readiness_response.raise_for_status.return_value = None
        readiness_response.json.return_value = {"data": [{"day": "2026-10-28", "score": 79}], "next_token": None}
        mocked_get.side_effect = [sleep_response, daily_sleep_response, readiness_response]

        self.client.force_login(self.coach)
        response = self.client.post(reverse("oura_test"), {"athlete_id": self.athlete.id})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Recent Oura results: Runner One")
        self.assertContains(response, "7.5")
        self.assertContains(response, "82")
        self.assertContains(response, "79")
        self.assertContains(response, "47.8")
        self.assertContains(response, "72.4")
        self.assertFalse(AthleteDailyVital.objects.filter(athlete=self.athlete).exists())
        self.assertEqual(mocked_get.call_count, 3)

    @patch("core.views.oura.requests.get")
    def test_oura_preview_does_not_change_existing_daily_vitals(self, mocked_get):
        OuraConnection.objects.create(
            athlete=self.athlete,
            access_token="access-token",
            scope="daily",
            health_data_consent_at="2026-10-29T08:00:00+00:00",
        )
        vital = AthleteDailyVital.objects.create(
            athlete=self.athlete,
            date="2026-10-28",
            sleep_hours=6.5,
            morning_hr=51,
        )
        responses = []
        sleep_response = Mock()
        sleep_response.raise_for_status.return_value = None
        sleep_response.json.return_value = {"data": [{
            "day": "2026-10-28",
            "type": "long_sleep",
            "total_sleep_duration": 27000,
            "lowest_heart_rate": 47,
            "average_hrv": 72,
        }], "next_token": None}
        responses.append(sleep_response)
        for payload in ({"data": [], "next_token": None}, {"data": [], "next_token": None}):
            api_response = Mock()
            api_response.raise_for_status.return_value = None
            api_response.json.return_value = payload
            responses.append(api_response)
        mocked_get.side_effect = responses

        self.client.force_login(self.coach)
        self.client.post(reverse("oura_test"), {"athlete_id": self.athlete.id})

        vital.refresh_from_db()
        self.assertEqual(vital.sleep_hours, 6.5)
        self.assertEqual(vital.morning_hr, 51)
        self.assertIsNone(vital.hrv)
        self.assertEqual(mocked_get.call_count, 3)

    @patch("core.views.oura.requests.get")
    def test_coach_cannot_preview_when_oura_permission_is_disabled(self, mocked_get):
        OuraConnection.objects.create(
            athlete=self.athlete,
            access_token="access-token",
            scope="daily",
            health_data_consent_at="2026-10-29T08:00:00+00:00",
        )
        self.athlete.oura_connection_enabled = False
        self.athlete.save(update_fields=["oura_connection_enabled"])
        self.client.force_login(self.coach)

        response = self.client.post(reverse("oura_test"), {"athlete_id": self.athlete.id})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "No accessible athlete has both Oura permission enabled")
        mocked_get.assert_not_called()

    def test_coach_cannot_connect_oura_for_an_athlete(self):
        self.client.force_login(self.coach)

        response = self.client.post(
            reverse("oura_connect"),
            {"consent_oura_data": "on", "confirm_adult_or_guardian": "on"},
        )

        self.assertEqual(response.status_code, 403)
        self.assertFalse(OuraConnection.objects.exists())

    def _oura_collections(self, mocked_get, *, days, readiness_days=None):
        readiness_days = readiness_days if readiness_days is not None else days
        payloads = [
            {"data": [{
                "day": day,
                "type": "long_sleep",
                "total_sleep_duration": 27000,
                "lowest_heart_rate": 47.6,
                "average_hrv": 72.4,
            } for day in days], "next_token": None},
            {"data": [{"day": day, "score": 82} for day in days], "next_token": None},
            {"data": [{"day": day, "score": 78} for day in readiness_days], "next_token": None},
        ]
        responses = []
        for payload in payloads:
            response = Mock()
            response.raise_for_status.return_value = None
            response.json.return_value = payload
            responses.append(response)
        mocked_get.side_effect = responses

    @patch("core.views.oura.timezone.localdate", return_value=date(2026, 10, 30))
    @patch("core.views.oura.requests.get")
    def test_athlete_oura_vitals_preview_uses_readiness_as_hidden_gate_and_only_suggests_empty_fields(
        self, mocked_get, _mocked_today
    ):
        OuraConnection.objects.create(
            athlete=self.athlete,
            access_token="access-token",
            scope="daily",
            health_data_consent_at="2026-10-29T08:00:00+00:00",
        )
        AthleteDailyVital.objects.create(
            athlete=self.athlete,
            date="2026-10-29",
            sleep_hours=6.5,
            morning_hr=51,
        )
        self._oura_collections(
            mocked_get,
            days=["2026-10-29", "2026-10-28", "2026-10-27"],
            readiness_days=["2026-10-29", "2026-10-28"],
        )

        response = self.client.post(reverse("oura_vitals_import"), {"action": "preview"})

        self.assertEqual(response.status_code, 200)
        items = response.json()["items"]
        self.assertEqual(items, [
            {
                "day": "2026-10-29",
                "sleep_hours": None,
                "sleep_quality": 8.2,
                "hrv": 72,
                "morning_hr": None,
            },
            {
                "day": "2026-10-28",
                "sleep_hours": 7.5,
                "sleep_quality": 8.2,
                "hrv": 72,
                "morning_hr": 48,
            },
        ])
        self.assertIsNone(AthleteDailyVital.objects.get(athlete=self.athlete, date="2026-10-29").sleep_quality)
        self.assertNotIn("readiness_score", response.json()["items"][0])
        self.assertNotIn("2026-10-27", [item["day"] for item in items])

    @patch("core.views.oura.timezone.localdate", return_value=date(2026, 10, 30))
    @patch("core.views.oura.requests.get")
    def test_athlete_can_remove_days_then_use_all_without_overwriting_or_importing_morning_hr(
        self, mocked_get, _mocked_today
    ):
        OuraConnection.objects.create(
            athlete=self.athlete,
            access_token="access-token",
            scope="daily",
            health_data_consent_at="2026-10-29T08:00:00+00:00",
        )
        vital = AthleteDailyVital.objects.create(
            athlete=self.athlete,
            date="2026-10-29",
            sleep_hours=6.5,
            morning_hr=51,
        )
        self._oura_collections(mocked_get, days=["2026-10-29", "2026-10-28", "2026-10-27"])

        response = self.client.post(
            reverse("oura_vitals_import"),
            {"action": "apply", "selected_days": '["2026-10-29", "2026-10-28"]'},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["saved_count"], 2)
        vital.refresh_from_db()
        self.assertEqual(vital.sleep_hours, 6.5)
        self.assertEqual(float(vital.sleep_quality), 8.2)
        self.assertEqual(vital.morning_hr, 51)
        self.assertEqual(vital.hrv, 72)
        imported = AthleteDailyVital.objects.get(athlete=self.athlete, date="2026-10-28")
        self.assertEqual(imported.sleep_hours, 7.5)
        self.assertEqual(float(imported.sleep_quality), 8.2)
        self.assertEqual(imported.morning_hr, 48)
        self.assertEqual(imported.hrv, 72)
        self.assertFalse(AthleteDailyVital.objects.filter(athlete=self.athlete, date="2026-10-27").exists())
        self.assertEqual(mocked_get.call_count, 3)

    def test_oura_vitals_import_is_unavailable_to_coaches(self):
        self.client.force_login(self.coach)

        response = self.client.post(reverse("oura_vitals_import"), {"action": "preview"})

        self.assertEqual(response.status_code, 403)
        self.assertFalse(AthleteDailyVital.objects.filter(athlete=self.athlete).exists())

    def test_oura_vitals_import_requires_daily_vitals_to_be_enabled(self):
        OuraConnection.objects.create(
            athlete=self.athlete,
            access_token="access-token",
            health_data_consent_at="2026-10-29T08:00:00+00:00",
        )
        self.athlete.daily_vitals_enabled = False
        self.athlete.save(update_fields=["daily_vitals_enabled"])

        response = self.client.post(reverse("oura_vitals_import"), {"action": "preview"})

        self.assertEqual(response.status_code, 403)
