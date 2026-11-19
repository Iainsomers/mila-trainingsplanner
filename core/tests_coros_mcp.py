from unittest.mock import patch, Mock
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from django.core import signing
import json
from core.models import Athlete, CorosMCPConnection, GarminActivity, TrainingSlot
from core.views.coros_mcp import _download_fit
from core.views.garmin import CONSENT_VERSION, fit_ai_allowed


class CorosMCPTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="MCP_Runner")
        self.athlete = Athlete.objects.create(name="MCP Runner", birth_year=2000, gender="X", coros_connection_enabled=True)
        self.client.force_login(self.user)

    @patch("core.views.coros_mcp.requests.post")
    def test_connect_requires_consent_and_uses_pkce(self, post):
        self.client.post("/integrations/coros/mcp/connect/")
        post.assert_not_called()
        post.return_value = Mock(content=b"{}", json=lambda: {"client_id":"mila"})
        response = self.client.post("/integrations/coros/mcp/connect/", {"consent":"on"})
        self.assertIn("code_challenge_method=S256", response.url)
        self.assertIn("state=", response.url)
        self.assertEqual(self.client.session["coros_mcp_pending"]["athlete"], self.athlete.pk)

    @patch("core.views.coros_mcp.requests.post")
    def test_callback_checks_state_and_is_one_use(self, post):
        session = self.client.session
        session["coros_mcp_pending"] = {"state":"correct", "athlete":self.athlete.pk,
            "user":self.user.pk, "started":timezone.now().timestamp(), "client":"mila", "verifier":"secret", "callback":"http://testserver/callback"}
        session.save()
        self.assertEqual(self.client.get("/integrations/coros/mcp/callback/?state=wrong&code=code").status_code, 403)
        post.assert_not_called()
        self.assertEqual(self.client.get("/integrations/coros/mcp/callback/?state=correct&code=code").status_code, 403)
        self.assertFalse(CorosMCPConnection.objects.exists())

    def test_coach_cannot_connect_as_athlete(self):
        self.user.is_staff = True
        self.user.save()
        for path in ("", "connect/", "preview/", "disconnect/"):
            response = (self.client.get if not path else self.client.post)("/integrations/coros/mcp/" + path)
            self.assertEqual(response.status_code, 403)

    def test_disabled_permission_blocks_all_connection_actions(self):
        self.athlete.coros_connection_enabled = False
        self.athlete.save()
        self.assertEqual(self.client.get("/integrations/coros/mcp/").status_code, 403)
        for path in ("connect/", "preview/", "disconnect/"):
            self.assertEqual(self.client.post("/integrations/coros/mcp/" + path).status_code, 403)

    def test_planning_hardware_shows_coros_only_when_enabled(self):
        page = self.client.get("/planning/?section=hardware")
        self.assertContains(page, "COROS account")
        self.athlete.coros_connection_enabled = False
        self.athlete.save()
        page = self.client.get("/planning/?section=hardware")
        self.assertNotContains(page, "COROS account")

    def test_coros_page_offers_and_saves_separate_fit_ai_permission(self):
        self.assertFalse(self.athlete.garmin_fit_upload_enabled)
        page = self.client.get("/integrations/coros/mcp/")
        self.assertContains(page, "AI analysis permission")
        self.assertContains(page, "optional AI analysis using OpenAI")
        self.assertFalse(fit_ai_allowed(self.athlete))

        response = self.client.post(
            "/integrations/coros/mcp/ai-permission/", {"consent_fit_ai": "on"},
        )
        self.assertRedirects(response, "/integrations/coros/mcp/")
        self.athlete.refresh_from_db()
        self.assertEqual(self.athlete.fit_ai_consent_version, CONSENT_VERSION)
        self.assertTrue(fit_ai_allowed(self.athlete))
        self.assertContains(
            self.client.get("/integrations/coros/mcp/"),
            'id="coros-fit-ai-consent" checked',
            html=False,
        )

        self.client.post("/integrations/coros/mcp/ai-permission/")
        self.athlete.refresh_from_db()
        self.assertIsNotNone(self.athlete.fit_ai_withdrawn_at)
        self.assertFalse(fit_ai_allowed(self.athlete))

    def test_only_own_enabled_coros_athlete_can_change_fit_ai_permission(self):
        self.user.is_staff = True
        self.user.save()
        response = self.client.post(
            "/integrations/coros/mcp/ai-permission/", {"consent_fit_ai": "on"},
        )
        self.assertEqual(response.status_code, 403)
        self.athlete.refresh_from_db()
        self.assertIsNone(self.athlete.fit_ai_consent_at)

    @patch("core.views.coros_mcp.requests.post")
    def test_valid_callback_saves_only_own_connection(self, post):
        session = self.client.session
        session["coros_mcp_pending"] = {"state":"correct", "athlete":self.athlete.pk,
            "user":self.user.pk, "started":timezone.now().timestamp(), "client":"mila", "verifier":"secret", "callback":"http://testserver/callback"}
        session.save()
        post.return_value = Mock(content=b"{}", json=lambda: {"access_token":"private", "refresh_token":"refresh", "expires_in":3600})
        response = self.client.get("/integrations/coros/mcp/callback/?state=correct&code=code")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(CorosMCPConnection.objects.get().athlete_id, self.athlete.pk)
        page = self.client.get("/integrations/coros/mcp/")
        self.assertContains(page, "Your COROS account is connected")
        self.assertNotContains(page, "private")

    def connection(self):
        return CorosMCPConnection.objects.create(athlete=self.athlete, client_id="mila",
            access_token="private-access", consented_at=timezone.now())

    def ticket(self, connection):
        return signing.dumps({"user":self.user.pk, "athlete":self.athlete.pk,
            "connection":connection.pk, "label":"12345", "sport":100}, salt="coros-fit-selection")

    @patch("core.views.coros_mcp._start_session", return_value="session")
    @patch("core.views.coros_mcp._tool")
    def test_encoded_activity_list_has_readable_rows_and_bound_import_button(self, tool, start):
        self.connection()
        tool.return_value = {"content":[{"type":"text", "text":json.dumps(
            "Sport Records\n1. Outdoor Run — 2026-11-16\n Duration: 1:00:00 | Distance: 12 km\n LabelId: 12345 | SportType: 100")}]}
        page = self.client.post("/integrations/coros/mcp/preview/")
        self.assertContains(page, "Outdoor Run")
        self.assertContains(page, "12 km")
        self.assertContains(page, "Import FIT for analysis")
        self.assertNotContains(page, "\\n")
        self.assertNotContains(page, "private-access")
        self.assertEqual(len(page.context["activities"]), 1)

    @patch("core.views.coros_mcp._start_session", return_value="session")
    @patch("core.views.coros_mcp._tool")
    @patch("core.views.coros_mcp._download_fit", return_value=b"original-fit")
    @patch("core.views.coros_mcp.parse_fit")
    def test_import_is_private_idempotent_and_does_not_modify_diary(self, parse, download, tool, start):
        connection = self.connection()
        parse.return_value = {"human":{"activity_start":timezone.now()}, "laps":[]}
        tool.return_value = {"content":[{"type":"text", "text":'Download: https://files.coros.com/activity.fit?signature=private'}]}
        payload = {"selection":self.ticket(connection)}
        for _ in range(2):
            page = self.client.post("/integrations/coros/mcp/import/", payload)
            self.assertEqual(page.status_code, 200)
            self.assertNotContains(page, "signature=private")
        self.assertEqual(GarminActivity.objects.count(), 1)
        activity = GarminActivity.objects.get()
        self.assertEqual(activity.athlete_id, self.athlete.pk)
        self.assertEqual(bytes(activity.raw_file), b"original-fit")
        self.assertEqual(activity.parsed_data["coros_mcp_label"], "12345")
        download.assert_called_once()
        self.assertFalse(TrainingSlot.objects.exists())
        other = get_user_model().objects.create_user(username="Other_Runner")
        other_athlete = Athlete.objects.create(name="Other Runner", birth_year=2000, gender="X", coros_connection_enabled=True)
        CorosMCPConnection.objects.create(athlete=other_athlete, client_id="other", access_token="other", consented_at=timezone.now())
        self.client.force_login(other)
        self.assertEqual(self.client.post("/integrations/coros/mcp/import/", payload).status_code, 403)

    @patch("core.views.coros_mcp._start_session")
    def test_modified_selection_is_rejected_before_network(self, start):
        connection = self.connection()
        self.assertEqual(self.client.post("/integrations/coros/mcp/import/",
            {"selection":self.ticket(connection) + "tampered"}).status_code, 403)
        start.assert_not_called()

    @patch("core.views.coros_mcp.requests.get")
    def test_download_rejects_untrusted_host_without_request(self, get):
        for url in ("http://files.coros.com/file.fit", "https://127.0.0.1/file.fit",
                    "https://coros.com.attacker.example/file.fit", "https://user@files.coros.com/file.fit"):
            with self.assertRaises(ValueError):
                _download_fit(url)
        get.assert_not_called()

    @patch("core.views.coros_mcp.requests.get")
    def test_download_bounds_size_and_rechecks_redirect_destination(self, get):
        response = Mock(status_code=302, headers={"Location":"https://127.0.0.1/secret"})
        get.return_value.__enter__ = Mock(return_value=response)
        get.return_value.__exit__ = Mock(return_value=False)
        with self.assertRaises(ValueError):
            _download_fit("https://files.coros.com/file.fit")
        get.assert_called_once()
        get.reset_mock()
        response = Mock(status_code=200, headers={})
        response.iter_content.return_value = [b"x" * (12 * 1024 * 1024 + 1)]
        get.return_value.__enter__ = Mock(return_value=response)
        with self.assertRaisesRegex(ValueError, "exceeds"):
            _download_fit("https://files.coros.com/file.fit")

    @patch("core.views.coros_mcp._start_session", return_value="session")
    @patch("core.views.coros_mcp._tool")
    @patch("core.views.coros_mcp._download_fit", return_value=b"not-a-fit")
    def test_invalid_fit_is_not_saved(self, download, tool, start):
        connection = self.connection()
        tool.return_value = {"content":[{"type":"text", "text":"https://files.coros.com/file.fit"}]}
        page = self.client.post("/integrations/coros/mcp/import/", {"selection":self.ticket(connection)})
        self.assertContains(page, "could not be imported")
        self.assertFalse(GarminActivity.objects.exists())

    @patch("core.views.coros_mcp._start_session", return_value="session")
    @patch("core.views.coros_mcp._tool")
    @patch("core.views.coros_mcp._download_fit")
    @patch("core.views.coros_mcp.parse_fit", return_value={"human":{}, "laps":[]})
    def test_permission_withdrawn_during_download_prevents_storage(self, parse, download, tool, start):
        connection = self.connection()
        tool.return_value = {"content":[{"type":"text", "text":"https://files.coros.com/file.fit"}]}
        def withdraw(url):
            Athlete.objects.filter(pk=self.athlete.pk).update(coros_connection_enabled=False)
            return b"fit"
        download.side_effect = withdraw
        page = self.client.post("/integrations/coros/mcp/import/", {"selection":self.ticket(connection)})
        self.assertEqual(page.status_code, 403)
        self.assertFalse(GarminActivity.objects.exists())

    @patch("core.views.coros_mcp._tool")
    def test_download_quota_is_shared_and_blocks_before_request(self, tool):
        from core.views.coros_mcp import import_activity
        connection = self.connection()
        connection.download_window_at = timezone.now()
        connection.download_requests = 50
        connection.save()
        with self.assertRaisesRegex(ValueError, "quota"):
            import_activity(connection, "session", "12345", 100)
        tool.assert_not_called()
