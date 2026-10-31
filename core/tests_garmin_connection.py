from urllib.parse import parse_qs, urlsplit
from unittest.mock import Mock, patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from core.models import Athlete, GarminConnection
from core.views.garmin import CONSENT_VERSION, ai_allowed


@override_settings(GARMIN_CLIENT_ID="test-client", GARMIN_CLIENT_SECRET="test-secret",
                   GARMIN_REDIRECT_URI="https://example.org/integrations/garmin/callback/")
class GarminConnectionTests(TestCase):
    def setUp(self):
        users = get_user_model()
        self.coach = users.objects.create_user(username="coach", is_staff=True)
        self.user = users.objects.create_user(username="runner", first_name="Runner", last_name="One")
        self.athlete = Athlete.objects.create(owner=self.coach, name="Runner One", gender="V", birth_year=2000)
        self.client.force_login(self.user)

    def enable(self):
        self.athlete.garmin_connection_enabled = True
        self.athlete.save()

    def begin(self, ai=True):
        data = {"consent_garmin_data": "on"}
        if ai:
            data["consent_garmin_ai"] = "on"
        return self.client.post(reverse("garmin_connect"), data)

    def callback(self, mocked_post, ai=True):
        response = self.begin(ai)
        query = parse_qs(urlsplit(response["Location"]).query)
        mocked_post.return_value = Mock(json=lambda: {
            "access_token": "test-access", "refresh_token": "test-refresh", "expires_in": 3600,
        })
        return self.client.get(reverse("garmin_callback"), {"code": "test-code", "state": query["state"][0]})

    def test_default_off_and_only_enabled_athlete_sees_tile(self):
        self.assertFalse(self.athlete.garmin_connection_enabled)
        self.assertNotContains(self.client.get(reverse("dashboard")), 'id="garmin-heading"')
        self.assertEqual(self.begin().status_code, 403)
        self.enable()
        page = self.client.get(reverse("dashboard"))
        self.assertContains(page, 'id="garmin-heading"')
        self.assertContains(page, "Withdraw AI permission")
        self.assertNotContains(page, 'id="garmin-ai-consent" checked')
        self.client.force_login(self.coach)
        self.assertNotContains(self.client.get(reverse("dashboard")), 'id="garmin-heading"')
        self.assertEqual(self.begin().status_code, 403)

    def test_missing_data_consent_or_configuration_does_not_start_oauth(self):
        self.enable()
        response = self.client.post(reverse("garmin_connect"), {"consent_garmin_ai": "on"})
        self.assertIn("consent_required", response["Location"])
        with override_settings(GARMIN_CLIENT_SECRET=""):
            self.assertIn("not_configured", self.begin()["Location"])
        self.assertNotIn("garmin_oauth_pending", self.client.session)

    @patch("core.views.garmin.requests.post")
    def test_pkce_and_callback_record_explicit_ai_consent(self, post):
        self.enable()
        result = self.begin()
        query = parse_qs(urlsplit(result["Location"]).query)
        self.assertEqual(query["code_challenge_method"], ["S256"])
        self.assertIn("code_challenge", query)
        self.assertIn("connected", self.callback(post)["Location"])
        self.athlete.refresh_from_db()
        self.assertEqual(self.athlete.garmin_ai_consent_version, CONSENT_VERSION)
        self.assertTrue(ai_allowed(self.athlete))
        self.assertTrue(GarminConnection.objects.filter(athlete=self.athlete).exists())
        self.assertEqual(self.client.get(reverse("garmin_callback"), {"code": "x", "state": "x"}).status_code, 302)
        self.assertEqual(post.call_count, 1)

    @patch("core.views.garmin.requests.post")
    def test_connection_does_not_require_ai_consent(self, post):
        self.enable()
        self.callback(post, ai=False)
        self.assertTrue(GarminConnection.objects.exists())
        self.assertFalse(ai_allowed(self.athlete))

    @patch("core.views.garmin.requests.post")
    def test_invalid_state_and_disabled_permission_reject_callback(self, post):
        self.enable()
        self.begin()
        self.client.get(reverse("garmin_callback"), {"code": "x", "state": "wrong"})
        post.assert_not_called()
        self.begin()
        pending = self.client.session["garmin_oauth_pending"]
        self.athlete.garmin_connection_enabled = False
        self.athlete.save()
        self.assertEqual(self.client.get(reverse("garmin_callback"), {"code": "x", "state": pending["state"]}).status_code, 403)
        post.assert_not_called()

    @patch("core.views.garmin.requests.delete")
    def test_withdraw_clears_connection_and_blocks_ai_even_if_remote_fails(self, delete):
        self.enable()
        self.athlete.garmin_ai_consent_at = timezone.now()
        self.athlete.garmin_ai_consent_version = CONSENT_VERSION
        self.athlete.save()
        GarminConnection.objects.create(athlete=self.athlete, access_token="test-access", data_consent_at=timezone.now())
        delete.return_value.status_code = 503
        self.assertTrue(ai_allowed(self.athlete))
        response = self.client.post(reverse("garmin_withdraw"), {"athlete_id": 999})
        self.assertIn("disconnected_remote_pending", response["Location"])
        self.assertFalse(ai_allowed(self.athlete))  # Also checks stale model instances.
        self.assertFalse(GarminConnection.objects.exists())
        self.athlete.refresh_from_db()
        self.assertIsNotNone(self.athlete.garmin_ai_withdrawn_at)
        self.assertTrue(self.athlete.garmin_connection_enabled)  # Trainer permission survives.

    def test_withdraw_invalidates_pending_oauth_and_is_post_only(self):
        self.enable()
        self.begin()
        self.assertEqual(self.client.get(reverse("garmin_withdraw")).status_code, 405)
        self.client.post(reverse("garmin_withdraw"))
        self.assertNotIn("garmin_oauth_pending", self.client.session)
        self.client.force_login(self.coach)
        self.assertEqual(self.client.post(reverse("garmin_withdraw")).status_code, 403)

    def test_switch_only_visible_to_coach(self):
        self.assertNotContains(self.client.get(reverse("athlete_settings")), 'id="garmin_connection_enabled"')
        self.client.force_login(self.coach)
        self.assertContains(self.client.get(reverse("coach_athlete_edit", args=[self.athlete.pk])), "Allow Garmin Connection")

    def test_coach_dashboard_lists_only_connected_athletes_of_active_coach(self):
        from core.models import CoachAccess
        self.enable()
        GarminConnection.objects.create(athlete=self.athlete, access_token="private-token", data_consent_at=timezone.now())
        other_coach = get_user_model().objects.create_user(username="other-coach", is_staff=True)
        other = Athlete.objects.create(owner=other_coach, name="Other connected runner", birth_year=2000, gender="V", garmin_connection_enabled=True)
        GarminConnection.objects.create(athlete=other, access_token="other-token", data_consent_at=timezone.now())
        self.client.force_login(self.coach)
        page = self.client.get(reverse("dashboard"))
        self.assertContains(page, 'id="coach-garmin-heading"')
        self.assertContains(page, "under construction")
        self.assertContains(page, f'href="{reverse("garmin_connections")}"')
        self.assertNotContains(page, "Runner One")
        self.assertGreater(page.content.index(b'id="coach-garmin-connections"'), page.content.index(b'Polar (under development)'))
        page = self.client.get(reverse("garmin_connections"))
        self.assertEqual([a.pk for a in page.context["connected_athletes"]], [self.athlete.pk])
        self.assertNotContains(page, "Other connected runner")
        self.assertNotContains(page, "private-token")
        CoachAccess.objects.create(owner=other_coach, grantee=self.coach, can_edit=False)
        session = self.client.session
        session["active_coach_owner_id"] = other_coach.pk
        session.save()
        page = self.client.get(reverse("garmin_connections"))
        self.assertEqual([a.pk for a in page.context["connected_athletes"]], [other.pk])

    def test_coach_garmin_tile_empty_and_hidden_from_athlete(self):
        self.client.force_login(self.coach)
        page = self.client.get(reverse("dashboard"))
        self.assertNotContains(page, "No athletes connected yet.")
        self.assertContains(self.client.get(reverse("garmin_connections")), "No athletes connected yet.")
        self.enable()  # Permission alone is not a connection.
        self.assertEqual(list(self.client.get(reverse("garmin_connections")).context["connected_athletes"]), [])
        self.client.force_login(self.user)
        page = self.client.get(reverse("dashboard"))
        self.assertNotContains(page, 'id="coach-garmin-heading"')
        self.assertEqual(self.client.get(reverse("garmin_connections")).status_code, 403)

    def settings_data(self):
        return {"name": self.athlete.name, "gender": "V", "birth_year": "2000",
                "zone_method": "manual", "z1_pace": "6:00", "z2_pace": "5:30",
                "z3_pace": "5:00", "z4_pace": "4:30", "z5_pace": "4:00"}

    def test_connected_athlete_opens_all_available_activities_newest_first(self):
        from core.models import GarminActivity
        self.enable()
        GarminConnection.objects.create(athlete=self.athlete, access_token="secret-token", data_consent_at=timezone.now())
        earlier = timezone.now() - timezone.timedelta(days=2)
        for index, start in enumerate((earlier, timezone.now())):
            GarminActivity.objects.create(athlete=self.athlete, activity_start=start,
                original_filename="private-file.fit", file_hash=str(index), raw_file=b"private raw data",
                parsed_data={"human": {"distance": f"{index + 5}.00 km"}})
        self.client.force_login(self.coach)
        url = reverse("garmin_athlete_activities", args=[self.athlete.pk])
        self.assertContains(self.client.get(reverse("garmin_connections")), f'href="{url}"')
        page = self.client.get(url)
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, earlier.strftime("%d-%m-%Y"))
        self.assertContains(page, "5.00 km")
        self.assertContains(page, "6.00 km")
        self.assertLess(page.content.index(b"6.00 km"), page.content.index(b"5.00 km"))
        for secret in ("secret-token", "private-file.fit", "private raw data"):
            self.assertNotContains(page, secret)

    def test_activities_page_enforces_coach_ownership_and_active_connection(self):
        self.enable()
        connection = GarminConnection.objects.create(athlete=self.athlete, access_token="token", data_consent_at=timezone.now())
        url = reverse("garmin_athlete_activities", args=[self.athlete.pk])
        self.assertEqual(self.client.get(url).status_code, 403)
        other_coach = get_user_model().objects.create_user(username="unrelated-coach", is_staff=True)
        self.client.force_login(other_coach)
        self.assertEqual(self.client.get(url).status_code, 404)
        self.client.force_login(self.coach)
        self.assertContains(self.client.get(url), "No Garmin activities available")
        self.athlete.garmin_connection_enabled = False
        self.athlete.save()
        self.assertEqual(self.client.get(url).status_code, 404)
        self.enable()
        connection.delete()
        self.assertEqual(self.client.get(url).status_code, 404)

    @patch("core.views.garmin.requests.delete")
    def test_coach_switch_saves_and_off_disconnects(self, delete):
        self.client.force_login(self.coach)
        url = reverse("coach_athlete_edit", args=[self.athlete.pk])
        response = self.client.post(url, {**self.settings_data(), "garmin_connection_enabled": "on"})
        self.assertEqual(response.status_code, 302, getattr(response, "context", None))
        self.athlete.refresh_from_db()
        self.assertTrue(self.athlete.garmin_connection_enabled)
        GarminConnection.objects.create(athlete=self.athlete, access_token="test-access", data_consent_at=timezone.now())
        delete.return_value.status_code = 204
        self.assertEqual(self.client.post(url, self.settings_data()).status_code, 302)
        self.athlete.refresh_from_db()
        self.assertFalse(self.athlete.garmin_connection_enabled)
        self.assertFalse(GarminConnection.objects.exists())
        self.assertIsNotNone(self.athlete.garmin_ai_withdrawn_at)

    def test_athlete_cannot_enable_trainer_permission_by_posting_it(self):
        response = self.client.post(reverse("athlete_settings"), {
            **self.settings_data(), "garmin_connection_enabled": "on",
            "garmin_ai_consent_at": timezone.now().isoformat(),
        })
        self.assertEqual(response.status_code, 302)
        self.athlete.refresh_from_db()
        self.assertFalse(self.athlete.garmin_connection_enabled)
        self.assertFalse(ai_allowed(self.athlete))

    def test_other_athlete_cannot_withdraw_permission_for_target(self):
        self.enable()
        self.athlete.garmin_ai_consent_at = timezone.now()
        self.athlete.garmin_ai_consent_version = CONSENT_VERSION
        self.athlete.save()
        other = get_user_model().objects.create_user(username="other", first_name="Other", last_name="Runner")
        Athlete.objects.create(owner=self.coach, name="Other Runner", birth_year=2000, gender="V", garmin_connection_enabled=True)
        self.client.force_login(other)
        self.client.post(reverse("garmin_withdraw"), {"athlete_id": self.athlete.pk})
        self.assertTrue(ai_allowed(self.athlete))

    @patch("core.views.polar_raw.translate")
    @patch("core.views.polar_raw._model_b_ai_description")
    @patch("core.views.polar_raw.type_b_description", return_value="Main: 1000 m Z1")
    def test_garmin_without_consent_never_calls_ai(self, fallback, ai, translate):
        from core.views.polar_raw import translate_model_b
        translate.return_value = [{"parts": [{}]}]
        translate_model_b([{"laps": {"laps": [{"distanceMeters": 1000, "durationMillis": 300000}]}}], 5, self.athlete, allow_ai=False)
        ai.assert_not_called()
        fallback.assert_called_once()
