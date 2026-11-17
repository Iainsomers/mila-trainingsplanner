from unittest.mock import patch, Mock
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from core.models import Athlete, CorosMCPConnection


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
