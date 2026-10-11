from unittest.mock import patch
from types import SimpleNamespace
from django.test import SimpleTestCase, RequestFactory
from django.template.loader import render_to_string
from django.http import HttpResponse
from core.views.polar_raw import sample_rows, translate, polar_raw_view


class RawPolarTests(SimpleTestCase):
    def setUp(self):
        # Render the real templates without unrelated database context processors.
        renderer = patch("core.views.polar_raw.render", side_effect=lambda request, template, context: HttpResponse(render_to_string(template, context)))
        renderer.start()
        self.addCleanup(renderer.stop)

    def test_samples_keep_nulls_and_do_not_interpolate(self):
        exercise = {"durationMillis": 5000, "samples": {"samples": [
            {"type": "DISTANCE", "intervalMillis": 2000, "values": [0, None, 12]},
            {"type": "HEART_RATE", "intervalMillis": 1000, "values": [100, 101, 102, 103, 104, 105]}]}}
        rows, metadata, truncated = sample_rows(exercise, 1)
        self.assertEqual(rows[1], {"time": "1", "distance": "NA", "hr": "101"})
        self.assertEqual(rows[2]["distance"], "NA")
        self.assertEqual(rows[4]["distance"], "12")
        self.assertEqual(rows[5]["distance"], "NA")
        self.assertFalse(truncated)

    def test_lap_precision_and_separate_categories(self):
        result = translate({"trainingSessions": [{"distanceMeters": 1234.5, "exercises": [
            {"laps": {"laps": [{"distanceMeters": 400.25, "durationMillis": 60234}],
                      "autoLaps": [{"distanceMeters": 1000, "durationMillis": 200000}]}}]}]}, 5)
        part = result[0]["parts"][0]
        self.assertEqual(part["manual"][0]["duration"], "00:01:00.234")
        self.assertEqual(part["manual"][0]["distance"], "400.25")
        self.assertEqual(len(part["auto"]), 1)
        self.assertEqual(part["distance"], "NA")

    @patch("core.views.polar_raw._polar_targets_for_user")
    @patch("core.views.polar_raw._polar_json_request")
    def test_fetch_uses_bearer_and_renders(self, fetch, targets):
        user = SimpleNamespace(is_authenticated=True)
        connection = SimpleNamespace(v4_access_token="secret")
        targets.return_value = [{"key": "self", "user": user, "connection": connection, "label": "Runner"}]
        fetch.return_value = (200, [])
        request = RequestFactory().post("/", {"polar_target": "self", "date": "2026-10-10", "interval": "5", "mode": "B"})
        request.user, request.session = user, {}
        response = polar_raw_view(request)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(fetch.call_args.kwargs["headers"]["Authorization"], "Bearer secret")
        self.assertNotIn(b"secret", response.content)

    @patch("core.views.polar_raw._polar_targets_for_user")
    @patch("core.views.polar_raw._polar_json_request")
    def test_foreign_target_and_invalid_interval_never_fetch(self, fetch, targets):
        user = SimpleNamespace(is_authenticated=True)
        targets.return_value = [{"key": "self", "user": user, "label": "Runner"}]
        for values in [{"polar_target": "user:99", "interval": "5"}, {"polar_target": "self", "interval": "0"}]:
            request = RequestFactory().post("/", dict(date="2026-10-10", **values))
            request.user, request.session = user, {}
            self.assertEqual(polar_raw_view(request).status_code, 200)
        fetch.assert_not_called()

    @patch("core.views.polar_raw._refresh_polar_v4_token")
    @patch("core.views.polar_raw._polar_targets_for_user")
    @patch("core.views.polar_raw._polar_json_request")
    def test_expired_token_refreshes_once(self, fetch, targets, refresh):
        user = SimpleNamespace(is_authenticated=True)
        connection = SimpleNamespace(v4_access_token="old")
        targets.return_value = [{"key": "self", "user": user, "connection": connection, "label": "Runner"}]
        def renew(value):
            value.v4_access_token = "new"
            return True, ""
        refresh.side_effect = renew
        fetch.side_effect = [(401, {}), (200, [])]
        request = RequestFactory().post("/", {"date": "2026-10-10", "interval": "5"})
        request.user, request.session = user, {}
        self.assertEqual(polar_raw_view(request).status_code, 200)
        self.assertEqual(fetch.call_count, 2)
        refresh.assert_called_once_with(connection)
        self.assertEqual(fetch.call_args.kwargs["headers"]["Authorization"], "Bearer new")
