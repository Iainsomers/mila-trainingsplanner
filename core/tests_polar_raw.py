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
    type_a_description,
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

    def test_type_a_excludes_known_non_running_recordings(self):
        payload = {"trainingSessions": [{
            "sport": {"id": "2", "name": "Cycling"},
            "exercises": [
                {"sport": {"id": "2", "name": "Cycling"}, "distanceMeters": 20000},
                {"sport": {"id": "1", "name": "Running"}, "distanceMeters": 5000},
            ],
        }]}
        type_a = translate(payload, 5, mode="A")
        self.assertEqual(len(type_a[0]["parts"]), 1)
        self.assertEqual(type_a[0]["parts"][0]["distance"], "5000")

        type_b = translate(payload, 5, mode="B")
        self.assertEqual(len(type_b[0]["parts"]), 2)

        cycling_only = translate([{
            "sport": {"id": "2", "name": "Cycling"},
            "laps": {"laps": [{"distanceMeters": 1000, "durationMillis": 90000}]},
        }], 5, mode="A")
        self.assertEqual(cycling_only, [])

    def test_type_a_generates_warmup_main_recoveries_and_no_cooldown(self):
        athlete = SimpleNamespace(
            get_zone_speed_mps=lambda: {"1": 3.8, "2": 4.6, "3": 5.0, "4": 5.5, "5": 6.0},
            pr_tm_s=None, pr_thm_s=None, pr_10000_s=None, pr_5000_s=None,
            pr_3000_s=None, pr_1500_s=None, pr_1000_s=None, pr_800_s=None,
            pr_600_s=None, pr_400_s=None,
        )
        laps = [
            {"distanceMeters": 3784.7, "durationMillis": 1108657},
            {"distanceMeters": 1986.9, "durationMillis": 428000},
            {"distanceMeters": 338.5, "durationMillis": 124625},
            {"distanceMeters": 2003.2, "durationMillis": 433000},
            {"distanceMeters": 163.8, "durationMillis": 89500},
            {"distanceMeters": 1993.1, "durationMillis": 443126},
            {"distanceMeters": 72.9, "durationMillis": 29750},
            {"distanceMeters": 989.7, "durationMillis": 215750},
            {"distanceMeters": 97.8, "durationMillis": 40125},
            {"distanceMeters": 994.1, "durationMillis": 213125},
            {"distanceMeters": 30.5, "durationMillis": 8125},
        ]
        self.assertEqual(
            type_a_description(laps, athlete),
            "WU: 3800 m Z1 · Main: 3×2000 m Z2 p107 + "
            "2×1000 m Z2 p40 · CD: none",
        )

        result = translate([{"sport": {"id": "1"}, "laps": {"laps": laps}}], 5, mode="A", athlete=athlete)
        self.assertEqual(result[0]["parts"][0]["description"], type_a_description(laps, athlete))

    def test_type_a_groups_repeated_distance_across_z1_to_z2(self):
        athlete = SimpleNamespace(
            get_zone_speed_mps=lambda: {"1": 4.35, "2": 4.55, "3": 5.0, "4": 5.5, "5": 6.0},
            pr_tm_s=None, pr_thm_s=None, pr_10000_s=None, pr_5000_s=None,
            pr_3000_s=None, pr_1500_s=None, pr_1000_s=None, pr_800_s=None,
            pr_600_s=None, pr_400_s=None,
        )
        laps = [
            {"distanceMeters": 3777.5, "durationMillis": 1067531},
            {"distanceMeters": 981.3, "durationMillis": 224750},
            {"distanceMeters": 246.0, "durationMillis": 89625},
            {"distanceMeters": 994.6, "durationMillis": 227000},
            {"distanceMeters": 255.6, "durationMillis": 85875},
            {"distanceMeters": 1003.8, "durationMillis": 224375},
            {"distanceMeters": 248.3, "durationMillis": 84875},
            {"distanceMeters": 1016.1, "durationMillis": 224250},
            {"distanceMeters": 252.7, "durationMillis": 84750},
            {"distanceMeters": 1013.3, "durationMillis": 223500},
            {"distanceMeters": 249.1, "durationMillis": 87875},
            {"distanceMeters": 1016.5, "durationMillis": 216500},
            {"distanceMeters": 19.5, "durationMillis": 4125},
        ]
        self.assertEqual(
            type_a_description(laps, athlete),
            "WU: 3800 m Z1 · Main: 6×1000 m Z1>Z2 p87 · CD: none",
        )

    def test_type_a_detects_short_repetitions_by_clear_speed_split(self):
        athlete = SimpleNamespace(
            get_zone_speed_mps=lambda: {"1": 4.2, "2": 4.6, "3": 5.1, "4": 5.6, "5": 6.1},
            pr_tm_s=None, pr_thm_s=None, pr_10000_s=None, pr_5000_s=None,
            pr_3000_s=None, pr_1500_s=None, pr_1000_s=None, pr_800_s=None,
            pr_600_s=None, pr_400_s=None,
        )
        values = [
            (4278.7, 1337657), (86.6, 20750), (84.9, 77750),
            (100.1, 19625), (84.6, 77000), (99.2, 23000),
            (85.3, 75375), (102.1, 22750), (104.1, 75375),
            (92.4, 22750), (184.7, 119875), (82.6, 21875),
            (98.8, 75625), (101.3, 23125), (128.0, 81000),
            (92.8, 22750), (97.7, 74625), (89.0, 22375),
            (4612.2, 1350875),
        ]
        laps = [{"distanceMeters": distance, "durationMillis": duration} for distance, duration in values]
        self.assertEqual(
            type_a_description(laps, athlete),
            "WU: 4300 m Z1 · Main: 9×100 m Z1>Z3 p82 · CD: 4600 m Z1",
        )

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
