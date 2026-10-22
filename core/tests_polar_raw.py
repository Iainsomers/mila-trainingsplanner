from unittest.mock import patch
from types import SimpleNamespace
from django.test import SimpleTestCase, RequestFactory
from django.template.loader import render_to_string
from django.http import HttpResponse
from core.views.polar_raw import (
    distance_rounded_to_50,
    lap_zone_paces,
    pace,
    polar_raw_view,
    sample_rows,
    translate,
)


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
        self.assertEqual(rows[1], {"time": "1", "distance": "NA", "hr": "101", "pace": "NA"})
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
        self.assertEqual(part["manual"][0]["distance_rounded_50"], "400")
        self.assertEqual(len(part["auto"]), 1)
        self.assertEqual(part["distance"], "NA")

    def test_lap_distance_is_rounded_to_nearest_50_metres(self):
        self.assertEqual(distance_rounded_to_50(424.99), "400")
        self.assertEqual(distance_rounded_to_50(425), "450")
        self.assertEqual(distance_rounded_to_50(476), "500")
        self.assertEqual(distance_rounded_to_50(None), "NA")
        self.assertEqual(distance_rounded_to_50(-1), "NA")

        html = render_to_string(
            "core/polar_raw_laps.html",
            {"rows": [{"index": 1, "distance": "425", "distance_rounded_50": "450",
                       "duration": "00:01:00.000", "pace": "2:21", "z_pace": "Z5", "t_pace": "T4",
                       "elapsed": "00:01:00.000"}]},
        )
        self.assertIn("Distance rounded to 50 m", html)
        self.assertIn("<td>450</td>", html)
        self.assertIn("<th>Zx</th>", html)
        self.assertIn("<th>Tx</th>", html)

    def test_lap_zone_pace_uses_selected_athlete_z_and_t_references(self):
        athlete = SimpleNamespace(
            get_zone_speed_mps=lambda: {"1": 3.0, "2": 3.5, "3": 4.0, "4": 4.5, "5": 5.0},
            pr_tm_s=12000,
            pr_thm_s=5400,
            pr_10000_s=2400,
            pr_5000_s=1050,
            pr_3000_s=600,
            pr_1500_s=285,
            pr_1000_s=180,
            pr_800_s=136,
            pr_600_s=99,
            pr_400_s=60,
        )
        self.assertEqual(lap_zone_paces(400, 90000, athlete), ("Z4", "T10"))
        self.assertEqual(lap_zone_paces(400, 90000, None), ("NA", "NA"))

        result = translate(
            [{"laps": {"laps": [{"distanceMeters": 400, "durationMillis": 90000}]}}],
            5,
            athlete=athlete,
        )
        row = result[0]["parts"][0]["manual"][0]
        self.assertEqual(row["z_pace"], "Z4")
        self.assertEqual(row["t_pace"], "T10")

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


    @patch("core.views.polar_raw._polar_targets_for_user")
    @patch("core.views.polar_raw._polar_json_request")
    def test_date_format_fallback_and_400_message(self, fetch, targets):
        from urllib.parse import parse_qs, urlsplit
        user = SimpleNamespace(is_authenticated=True)
        connection = SimpleNamespace(v4_access_token="secret")
        targets.return_value = [{"key": "self", "user": user, "connection": connection, "label": "Runner"}]
        request = RequestFactory().post("/", {"date": "2026-10-10", "interval": "5"})
        request.user, request.session = user, {}
        fetch.side_effect = [(400, {"message": "Cannot parse from datetime"}), (200, [])]
        self.assertEqual(polar_raw_view(request).status_code, 200)
        first = parse_qs(urlsplit(fetch.call_args_list[0].args[0]).query)
        second = parse_qs(urlsplit(fetch.call_args_list[1].args[0]).query)
        self.assertEqual(first["from"], ["2026-10-10T00:00:00"])
        self.assertEqual(second["from"], ["2026-10-10T00:00:00.000"])
        fetch.side_effect = [(400, {"message": "Unsupported feature"})]
        response = polar_raw_view(request)
        self.assertIn(b"Unsupported feature", response.content)
        self.assertNotIn(b"Reconnect Polar v4 if authorization", response.content)


    def test_pace_is_per_lap_and_per_displayed_segment(self):
        result = translate([{"laps": {"laps": [{"distanceMeters": 400, "durationMillis": 90000}]}}], 5)
        self.assertEqual(result[0]["parts"][0]["manual"][0]["pace"], "3:45")
        rows, _, _ = sample_rows({"samples": {"samples": [
            {"type": "DISTANCE", "intervalMillis": 5000, "values": [0, 20, 30, None, 50, 50, 45, 65]}]}}, 5)
        self.assertEqual([row["pace"] for row in rows], ["NA", "4:10", "8:20", "NA", "NA", "NA", "NA", "4:10"])
        self.assertEqual(pace(359.6, 1000), "6:00")
        self.assertEqual(pace(0, 1000), "NA")
        self.assertEqual(pace(60, 0), "NA")
