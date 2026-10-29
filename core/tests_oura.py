from urllib.parse import parse_qs, urlsplit
from unittest.mock import Mock, patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from core.models import Athlete, OuraConnection


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
        )
        self.client.force_login(self.athlete_user)

    def test_athlete_dashboard_has_a_separate_hardware_settings_oura_block(self):
        response = self.client.get(reverse("dashboard"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Hardware settings")
        self.assertContains(response, "Oura connection")
        self.assertContains(response, reverse("oura_connect"))

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
        self.assertEqual(query["scope"], ["daily heartrate"])
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

    def test_coach_cannot_connect_oura_for_an_athlete(self):
        self.client.force_login(self.coach)

        response = self.client.post(
            reverse("oura_connect"),
            {"consent_oura_data": "on", "confirm_adult_or_guardian": "on"},
        )

        self.assertEqual(response.status_code, 403)
        self.assertFalse(OuraConnection.objects.exists())
