import json
from datetime import timedelta
from unittest.mock import Mock, patch

from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.utils import timezone

from core.models import Athlete, MySasyConnection, MySasyLinkAttempt, MySasyMonthlyUsage
from core.mysasy import MySasyError, measurements
from core.views.mysasy import PENDING

BASE = "/integrations/mysasy/"
ROWS = [{"id": 1, "timestamp": "2026-11-18 08:10:00", "compensation": 75,
         "totalPower": 3.79, "consumption": 7.87, "replenishment": 3.36,
         "functionalAge": 35.09, "detailUrl": "https://client.mysasy.com/#date=2026-11-18"}]


@override_settings(MYSASY_CLIENT_SECRET="test-client-secret", MYSASY_APPLICATION_ID="31")
class MySasyTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="Sasy_Runner")
        self.coach = get_user_model().objects.create_user(username="sasy-coach", is_staff=True)
        self.athlete = Athlete.objects.create(name="Sasy Runner", owner=self.coach,
            birth_year=2000, gender="X", mysasy_connection_enabled=True)
        self.client.force_login(self.user)

    def start(self):
        return self.client.post(BASE + "connect/", {"consent": "on", "permission": "on"})

    def callback(self):
        return self.client.get(BASE + "callback/", {"success": "1", "token": "private-token"})

    def connection(self):
        return MySasyConnection.objects.create(athlete=self.athlete, auth_token="saved-token",
            consented_at=timezone.now(), consented_by=self.user, measurements=ROWS,
            last_checked_at=timezone.now())

    def test_connect_requires_both_permissions_and_server_configuration(self):
        for data in ({}, {"consent": "on"}, {"permission": "on"}):
            self.client.post(BASE + "connect/", data)
            self.assertFalse(MySasyLinkAttempt.objects.exists())
        with override_settings(MYSASY_CLIENT_SECRET=""):
            self.start()
            self.assertFalse(MySasyLinkAttempt.objects.exists())
            self.assertContains(self.client.get(BASE), "awaiting application configuration")
        response = self.start()
        self.assertEqual(response.url, "https://client.mysasy.com/profile/connect/31")
        self.assertEqual(MySasyLinkAttempt.objects.get().user, self.user)
        self.assertNotIn("private-token", str(dict(self.client.session)))

    @patch("core.views.mysasy.measurements", return_value=ROWS)
    def test_callback_confirmation_and_replay(self, api):
        self.start()
        response = self.callback()
        self.assertEqual(response.url, BASE + "confirm/")
        self.assertEqual(response["Referrer-Policy"], "no-referrer")
        self.assertIn("no-store", response["Cache-Control"])
        self.assertFalse(MySasyConnection.objects.exists())
        api.assert_not_called()
        page = self.client.get(response.url)
        self.assertContains(page, "75")
        self.assertNotContains(page, "private-token")
        self.client.get(response.url)
        api.assert_called_once_with("private-token")
        identity = self.client.session[PENDING]
        self.assertEqual(self.client.post(BASE + "finish/", {"attempt": identity}).status_code, 403)
        done = self.client.post(BASE + "finish/", {"attempt": identity, "own_account": "on", "athlete": 999})
        self.assertEqual(done.status_code, 302)
        connection = MySasyConnection.objects.get()
        self.assertEqual(connection.athlete, self.athlete)
        self.assertEqual(connection.auth_token, "private-token")
        self.assertEqual(connection.measurements, ROWS)
        self.assertFalse(MySasyLinkAttempt.objects.exists())
        self.assertNotIn(PENDING, self.client.session)
        self.assertEqual(self.callback().url, BASE)
        self.assertEqual(MySasyConnection.objects.count(), 1)

    def test_callback_needs_same_live_session_and_is_one_use(self):
        self.assertEqual(self.callback().url, BASE)
        self.start()
        MySasyLinkAttempt.objects.update(created_at=timezone.now() - timedelta(minutes=11))
        self.assertEqual(self.callback().url, BASE)
        self.start()
        identity = self.client.session[PENDING]
        other = get_user_model().objects.create_user(username="Other_Sasy")
        Athlete.objects.create(name="Other Sasy", birth_year=2000, gender="X", mysasy_connection_enabled=True)
        self.client.force_login(other)
        session = self.client.session
        session[PENDING] = identity
        session.save()
        self.assertEqual(self.callback().url, BASE)
        self.assertFalse(MySasyConnection.objects.exists())
        self.client.force_login(self.user)
        self.start()
        self.callback()
        self.assertEqual(self.callback().url, BASE)

    def test_rejected_invalid_and_duplicate_tokens_clear_pending(self):
        for query in ({"success": "0"}, {"success": "1"}, {"success": "1", "token": "bad\nvalue"},
                      {"success": "1", "token": ["one", "two"]}):
            self.start()
            self.client.get(BASE + "callback/", query)
            self.assertFalse(MySasyLinkAttempt.objects.exists())
            self.assertNotIn(PENDING, self.client.session)
        self.assertFalse(MySasyConnection.objects.exists())

    @patch("core.views.mysasy.measurements", return_value=[])
    def test_empty_measurements_cached_and_cancel_does_not_replace_existing(self, api):
        previous = self.connection()
        self.start()
        self.callback()
        self.client.get(BASE + "confirm/")
        self.client.get(BASE + "confirm/")
        api.assert_called_once()
        self.client.post(BASE + "finish/", {"attempt": self.client.session[PENDING], "cancel": "on"})
        previous.refresh_from_db()
        self.assertEqual(previous.auth_token, "saved-token")
        self.assertFalse(MySasyLinkAttempt.objects.exists())

    @patch("core.views.mysasy.measurements", side_effect=MySasyError("Unavailable"))
    def test_failed_confirmation_does_not_replace_existing(self, api):
        self.connection()
        self.start()
        self.callback()
        page = self.client.get(BASE + "confirm/", follow=True)
        self.assertContains(page, "Unavailable")
        self.assertEqual(MySasyConnection.objects.get().auth_token, "saved-token")
        self.assertFalse(MySasyLinkAttempt.objects.exists())

    def test_post_actions_need_csrf(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.user)
        for action in ("connect", "finish", "refresh", "disconnect"):
            self.assertEqual(client.post(BASE + action + "/").status_code, 403)

    def test_coach_and_disabled_athlete_cannot_connect(self):
        for actor, enabled in ((self.coach, True), (self.user, False)):
            self.athlete.mysasy_connection_enabled = enabled
            self.athlete.save()
            self.client.force_login(actor)
            for action in ("", "callback/", "confirm/"):
                self.assertEqual(self.client.get(BASE + action).status_code, 403)
            for action in ("connect/", "finish/", "refresh/", "disconnect/"):
                self.assertEqual(self.client.post(BASE + action).status_code, 403)

    def test_anonymous_callback_never_copies_token_to_login_redirect(self):
        self.client.logout()
        response = self.callback()
        self.assertEqual(response.url, BASE)
        self.assertNotIn("private-token", response.url)
        self.assertEqual(response["Referrer-Policy"], "no-referrer")

    @patch("core.views.mysasy.measurements", return_value=ROWS)
    def test_disabled_after_callback_cannot_finish(self, api):
        self.start()
        self.callback()
        self.client.get(BASE + "confirm/")
        identity = self.client.session[PENDING]
        Athlete.objects.filter(pk=self.athlete.pk).update(mysasy_connection_enabled=False)
        self.assertEqual(self.client.post(BASE + "finish/", {"attempt": identity, "own_account": "on"}).status_code, 403)
        self.assertFalse(MySasyConnection.objects.exists())

    def test_coach_reads_cached_measurements_only_for_authorized_athlete(self):
        self.connection()
        url = f"/coach/athletes/{self.athlete.pk}/mysasy/"
        self.assertEqual(self.client.get(url).status_code, 403)
        self.client.force_login(self.coach)
        page = self.client.get(url)
        self.assertContains(page, "75")
        self.assertNotContains(page, "Refresh measurements")
        self.assertNotContains(page, "saved-token")
        self.assertIn("no-store", page["Cache-Control"])
        other = get_user_model().objects.create_user(username="other-coach", is_staff=True)
        self.client.force_login(other)
        self.assertEqual(self.client.get(url).status_code, 404)

    def test_shared_coach_requires_vitals_visibility(self):
        from core.models import CoachAccess, CoachSettings, CoachEvaluationSharing
        self.connection()
        other = get_user_model().objects.create_user(username="shared-sasy-coach", is_staff=True)
        CoachAccess.objects.create(owner=self.coach, grantee=other)
        CoachSettings.objects.update_or_create(user=self.coach, defaults={"evaluation_sharing_enabled": True})
        self.client.force_login(other)
        session = self.client.session
        session["active_coach_owner_id"] = self.coach.pk
        session.save()
        url = f"/coach/athletes/{self.athlete.pk}/mysasy/"
        self.assertEqual(self.client.get(url).status_code, 403)
        CoachEvaluationSharing.objects.create(owner=self.coach, grantee=other, vitals=True)
        self.assertEqual(self.client.get(url).status_code, 200)
        self.assertEqual(self.client.post(url).status_code, 403)

    @patch("core.mysasy.requests.get")
    def test_coach_test_preserves_unknown_fields_and_redacts_credentials(self, get):
        payload = [dict(ROWS[0], sleepDuration=7.5, sleepQuality=82,
            additional={"nightHR": 42, "HRV": 67, "access_token": "never-show", "password": "private"},
            echo="saved-token test-client-secret", note="</textarea><script>bad()</script>")]
        response = Mock(status_code=200)
        response.iter_content.return_value = [json.dumps(payload).encode()]
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        get.return_value = response
        connection = self.connection()
        self.client.force_login(self.coach)
        url = f"/coach/athletes/{self.athlete.pk}/mysasy/"
        page = self.client.post(url, follow=True)
        self.assertContains(page, "sleepDuration")
        self.assertContains(page, "nightHR")
        self.assertContains(page, "[redacted]")
        for secret in ("never-show", "saved-token", "test-client-secret", "<script>bad()</script>"):
            self.assertNotContains(page, secret)
        connection.refresh_from_db()
        self.assertEqual(connection.diagnostic_payload[0]["sleepQuality"], 82)
        self.assertEqual(connection.diagnostic_payload[0]["additional"]["access_token"], "[redacted]")
        self.assertEqual(connection.measurements, ROWS)
        self.client.post(url)
        self.client.get(url)
        get.assert_called_once()
        self.client.force_login(self.user)
        own_page = self.client.get(BASE)
        self.assertNotContains(own_page, "API test data")
        self.assertNotContains(own_page, "sleepDuration")
        self.assertEqual(self.client.post(url).status_code, 403)

    @patch("core.views.mysasy.diagnostic_response", side_effect=MySasyError("Unavailable"))
    def test_failed_test_preserves_previous_data_and_cools_down(self, api):
        connection = self.connection()
        connection.diagnostic_payload = []
        connection.save()
        self.client.force_login(self.coach)
        url = f"/coach/athletes/{self.athlete.pk}/mysasy/"
        self.assertContains(self.client.post(url, follow=True), "Unavailable")
        self.client.post(url)
        api.assert_called_once()
        connection.refresh_from_db()
        self.assertEqual(connection.diagnostic_payload, [])
        self.assertIsNotNone(connection.diagnostic_checked_at)

    @patch("core.views.mysasy.diagnostic_response")
    def test_test_action_checks_scope_privacy_csrf_and_connection(self, api):
        self.connection()
        url = f"/coach/athletes/{self.athlete.pk}/mysasy/"
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.coach)
        self.assertEqual(csrf_client.post(url).status_code, 403)
        outsider = get_user_model().objects.create_user(username="outsider-test", is_staff=True)
        self.client.force_login(outsider)
        self.assertEqual(self.client.post(url).status_code, 404)
        self.client.force_login(self.coach)
        Athlete.objects.filter(pk=self.athlete.pk).update(mysasy_connection_enabled=False)
        self.assertEqual(self.client.post(url).status_code, 403)
        Athlete.objects.filter(pk=self.athlete.pk).update(mysasy_connection_enabled=True)
        MySasyConnection.objects.all().delete()
        self.assertEqual(self.client.post(url).status_code, 302)
        api.assert_not_called()

    @patch("core.views.mysasy.measurements", return_value=ROWS)
    def test_refresh_cooldown_and_disconnect(self, api):
        connection = self.connection()
        self.client.post(BASE + "refresh/")
        api.assert_not_called()
        MySasyConnection.objects.update(last_checked_at=timezone.now() - timedelta(minutes=11))
        self.client.post(BASE + "refresh/")
        api.assert_called_once_with(connection.auth_token)
        self.client.get(BASE)
        api.assert_called_once()
        self.start()
        self.client.post(BASE + "disconnect/")
        self.assertFalse(MySasyConnection.objects.exists())
        self.assertFalse(MySasyLinkAttempt.objects.exists())

    def test_hardware_visibility_and_coach_status(self):
        self.assertContains(self.client.get("/planning/?section=hardware"), "mySASY account")
        self.connection()
        self.client.force_login(self.coach)
        page = self.client.get(f"/coach/athletes/{self.athlete.pk}/edit/")
        self.assertContains(page, "Allow mySASY connection")
        self.assertContains(page, "mySASY: Connected")
        self.athlete.mysasy_connection_enabled = False
        self.athlete.save()
        self.client.force_login(self.user)
        self.assertNotContains(self.client.get("/planning/?section=hardware"), "mySASY account")

    def test_coach_can_enable_and_disable_athlete_cannot_grant_permission(self):
        data = {"name": self.athlete.name, "birth_year": "2000", "gender": "X", "zone_method": "manual"}
        data.update({f"z{i}_pace": f"{6-i}:30" for i in range(1, 6)})
        self.client.force_login(self.coach)
        self.connection()
        self.start()  # Coaches cannot start an attempt.
        page = self.client.post(f"/coach/athletes/{self.athlete.pk}/edit/", data)
        self.assertEqual(page.status_code, 302)
        self.athlete.refresh_from_db()
        self.assertFalse(self.athlete.mysasy_connection_enabled)
        self.assertFalse(MySasyConnection.objects.exists())
        self.client.force_login(self.user)
        data["mysasy_connection_enabled"] = "on"
        response = self.client.post("/athlete/settings/", data)
        self.assertEqual(response.status_code, 302)
        self.athlete.refresh_from_db()
        self.assertFalse(self.athlete.mysasy_connection_enabled)
        self.client.force_login(self.coach)
        self.client.post(f"/coach/athletes/{self.athlete.pk}/edit/", data)
        self.athlete.refresh_from_db()
        self.assertTrue(self.athlete.mysasy_connection_enabled)


@override_settings(MYSASY_CLIENT_SECRET="test-client-secret", MYSASY_APPLICATION_ID="31")
class MySasyClientTests(TestCase):
    def response(self, data=ROWS, status=200):
        response = Mock(status_code=status)
        response.iter_content.return_value = [json.dumps(data).encode()]
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        return response

    @patch("core.mysasy.requests.get")
    def test_bounded_request_headers_and_safe_link(self, get):
        get.return_value = self.response(ROWS + [dict(ROWS[0], detailUrl="https://evil.example/", compensation=0)])
        rows = measurements("athlete-token")
        args, kwargs = get.call_args
        self.assertEqual(args[0], "https://api.mysasy.com/myapi/v1/measurements")
        self.assertEqual(kwargs["headers"], {"X-Client-Secret": "test-client-secret", "X-Auth-Token": "athlete-token"})
        self.assertFalse(kwargs["allow_redirects"])
        self.assertEqual(kwargs["timeout"], 15)
        self.assertEqual(rows[1]["detailUrl"], "")
        self.assertEqual(rows[1]["compensation"], 0)
        self.assertEqual(MySasyMonthlyUsage.objects.get().requests, 1)

    @patch("core.mysasy.requests.get")
    def test_errors_size_and_shared_quota(self, get):
        get.return_value = self.response(status=401)
        with self.assertRaises(MySasyError):
            measurements("token")
        get.return_value = self.response()
        get.return_value.iter_content.return_value = [b"x" * (1024 * 1024 + 1)]
        with self.assertRaises(MySasyError):
            measurements("token")
        with override_settings(MYSASY_MONTHLY_REQUEST_LIMIT=2):
            with self.assertRaisesMessage(MySasyError, "monthly"):
                measurements("token")
        self.assertEqual(get.call_count, 2)
