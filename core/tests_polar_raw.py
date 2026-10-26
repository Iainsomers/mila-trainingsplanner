import json
from unittest.mock import MagicMock, patch
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
    translate_model_b,
    _model_b_ai_description,
    type_b_description,
    type_a_description,
    type_a_general_description,
)


def _tim_olsthoorn_6_plus_8_laps():
    """Screenshot-derived lap sequence: 6 x 400 m, then 8 x 400 m."""
    values = [
        (5507.6, 1933.254), (103.1, 34.500), (20.8, 23.624),
        (392.9, 80.875), (108.1, 57.501), (393.4, 82.750),
        (117.4, 60.500), (383, 79.375), (120, 59.749),
        (375.3, 79.251), (111.6, 60.500), (391.3, 83.500),
        (107.9, 60.499), (378.4, 79.125), (65.3, 20.501),
        (40.1, 39.750), (495.7, 140.250), (383.5, 79.000),
        (111.6, 59.624), (378.5, 78.126), (116.3, 283.250),
        (0, 18.250), (378.5, 80.374), (106.7, 61.875),
        (389.7, 75.251), (124.3, 61.500), (380.2, 74.249),
        (89.9, 42.501), (28.5, 19.249), (387.1, 74.501),
        (113.1, 61.125), (379.4, 74.624), (111.7, 59.125),
        (384.5, 75.001), (22, 5.125),
    ]
    return [
        {"distanceMeters": distance, "durationMillis": duration * 1000}
        for distance, duration in values
    ]


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

    def test_type_a_lap_shows_average_heart_rate_from_second_samples(self):
        result = translate([{"laps": {"laps": [
            {"distanceMeters": 400, "durationMillis": 4000, "splitTimeMillis": 4000},
            {"distanceMeters": 400, "durationMillis": 4000, "splitTimeMillis": 8000},
        ]}, "samples": {"samples": [
            {"type": "HEART_RATE", "intervalMillis": 1000, "values": [140, 150, 160, 170, 180, 190, 200, 210]},
        ]}}], 5)
        rows = result[0]["parts"][0]["manual"]
        self.assertEqual([row["average_hr"] for row in rows], ["155", "195"])

    def test_model_b_starts_with_same_type_a_output(self):
        payload = [{"sport": {"id": "1"}, "laps": {"laps": [
            {"distanceMeters": 1000, "durationMillis": 240000},
        ]}}]
        self.assertEqual(translate_model_b(payload, 5), translate(payload, 5, mode="A"))

    def test_model_b_recognizes_two_repeated_500m_sets_with_combined_lap(self):
        values = [
            (1160, 605752), (185, 80250), (788, 562376),
            (512, 101125), (45, 49875), (2, 9500), (488, 98625),
            (53, 53874), (13, 8251), (493, 98500), (64, 62249),
            (481, 99751), (73, 67375), (485, 98500), (55, 61000),
            (499, 99500), (54, 48500), (1, 11750), (489, 96874),
            (553, 161501), (192, 223249), (498, 95000), (75, 60126),
            (498, 96249), (40, 51126), (14, 20749), (494, 97875),
            (27, 37751), (13, 20875), (501, 98249), (45, 59000),
            (502, 95125), (40, 39750), (5, 19500), (500, 96751),
            (49, 44875), (0.1, 14124), (494, 94876), (81, 58750),
            (495, 93124), (1526, 482253),
        ]
        laps = [{"distanceMeters": distance, "durationMillis": duration} for distance, duration in values]
        athlete = SimpleNamespace(get_zone_speed_mps=lambda: {"1": 5.0})
        description = type_b_description(laps, athlete)
        self.assertIn("8×500 m", description)
        self.assertEqual(description.count("8×500 m"), 2)
        self.assertIn("CD: 1550 m Z1", description)

    def test_model_b_keeps_two_reps_after_a_long_recovery_inside_second_set(self):
        laps = _tim_olsthoorn_6_plus_8_laps()

        def zones(distance, duration_ms, _athlete):
            speed = distance / (duration_ms / 1000) if duration_ms else 0
            return ("Z3" if distance >= 350 and speed >= 4 else "Z1", "NA")

        with patch("core.views.polar_raw.lap_zone_paces", side_effect=zones):
            description = type_b_description(laps, SimpleNamespace())

        self.assertIn("Main: 6×400 m Z3", description)
        self.assertIn("8×400 m Z3", description)

    def test_model_b_rejects_ai_description_that_omits_repeated_active_laps(self):
        laps = _tim_olsthoorn_6_plus_8_laps()

        def zones(distance, duration_ms, _athlete):
            speed = distance / (duration_ms / 1000) if duration_ms else 0
            return ("Z3" if distance >= 350 and speed >= 4 else "Z1", "NA")

        response = MagicMock()
        response.read.return_value = json.dumps({"choices": [{"message": {"content": json.dumps({
            "warmup_m": 5650,
            "cooldown_m": None,
            "sets": 1,
            "segments": [
                {"count": 6, "distance_m": 400, "zone": "Z3", "pace": "3:30", "recovery_s": 60},
                {"count": 6, "distance_m": 400, "zone": "Z3", "pace": "3:17", "recovery_s": 61},
            ],
            "confidence": 0.95,
        })}}]}).encode()
        response.__enter__.return_value = response
        with (
            patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"}),
            patch("core.views.polar_raw.lap_zone_paces", side_effect=zones),
            patch("core.views.polar_raw.urlopen", return_value=response),
        ):
            result = translate_model_b(
                [{"sport": {"id": "1"}, "laps": {"laps": laps}}],
                5,
                SimpleNamespace(),
            )

        description = result[0]["parts"][0]["description"]
        self.assertIn("Main: 6×400 m Z3", description)
        self.assertIn("8×400 m Z3", description)
        self.assertEqual(description.count("×400 m Z3"), 2)

    def test_model_b_ai_description_builds_nested_sets_from_structured_response(self):
        laps = []
        laps.append({"distanceMeters": 3800, "durationMillis": 1200000})
        for _ in range(2):
            laps.extend([
                {"distanceMeters": 500, "durationMillis": 100000},
                {"distanceMeters": 60, "durationMillis": 60000},
                {"distanceMeters": 400, "durationMillis": 80000},
                {"distanceMeters": 60, "durationMillis": 60000},
                {"distanceMeters": 500, "durationMillis": 100000},
            ])
        laps.append({"distanceMeters": 900, "durationMillis": 300000})
        response = MagicMock()
        response.read.return_value = json.dumps({"choices": [{"message": {"content": json.dumps({
            "warmup_m": 3800,
            "cooldown_m": 900,
            "sets": 2,
            "segments": [
                {"count": 2, "distance_m": 500, "zone": "Z3", "pace": "3:20", "recovery_s": 60},
                {"count": 1, "distance_m": 400, "zone": "Z3", "pace": "3:20", "recovery_s": None},
            ],
            "confidence": 0.9,
        })}}]}).encode()
        response.__enter__.return_value = response
        with patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"}), patch("core.views.polar_raw.urlopen", return_value=response):
            description = _model_b_ai_description(laps)
        self.assertEqual(description, "WU: 3800 m Z1 · Main: 2×(2×500 m Z3 (3:20) p60 + 400 m Z3 (3:20)) · CD: 900 m Z1")

    def test_model_b_ai_rounds_distances_and_compresses_repeated_sequence(self):
        laps = [
            {"distanceMeters": 2451, "durationMillis": 720000},
            {"distanceMeters": 526, "durationMillis": 600000},
        ]
        for distance in (1158, 990, 812, 1148, 1000, 824):
            laps.extend([
                {"distanceMeters": distance, "durationMillis": 210000 if distance in {812, 824} else 240000},
                {"distanceMeters": 50, "durationMillis": 60000},
            ])
        laps.append({"distanceMeters": 1897, "durationMillis": 600000})
        response = MagicMock()
        response.read.return_value = json.dumps({"choices": [{"message": {"content": json.dumps({
            "warmup_m": None,
            "cooldown_m": None,
            "sets": 1,
            "segments": [
                {"count": 1, "distance_m": 1158, "zone": "Z2", "pace": "4:10", "recovery_s": 60},
                {"count": 1, "distance_m": 990, "zone": "Z2", "pace": "4:10", "recovery_s": 60},
                {"count": 1, "distance_m": 812, "zone": "Z2", "pace": "4:10", "recovery_s": None},
                {"count": 1, "distance_m": 1148, "zone": "Z2", "pace": "4:10", "recovery_s": 60},
                {"count": 1, "distance_m": 1000, "zone": "Z2", "pace": "4:10", "recovery_s": 60},
                {"count": 1, "distance_m": 824, "zone": "Z2", "pace": "4:10", "recovery_s": None},
            ],
            "confidence": 0.9,
        })}}]}).encode()
        response.__enter__.return_value = response
        athlete = SimpleNamespace(get_zone_speed_mps=lambda: {"1": 3.0, "2": 4.2, "3": 5.0})
        with patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"}), patch("core.views.polar_raw.urlopen", return_value=response):
            description = _model_b_ai_description(laps, athlete)
        self.assertEqual(description, "WU: 3000 m Z1 · Main: 2×(1150 m Z2 (4:10) p60 + 1000 m Z2 (4:10) p60 + 800 m Z2 (4:10)) · CD: 1900 m Z1")

    def test_model_b_rejects_ai_distances_not_present_in_laps(self):
        laps = [
            {"distanceMeters": 3800, "durationMillis": 1200000},
            {"distanceMeters": 2000, "durationMillis": 420000},
            {"distanceMeters": 350, "durationMillis": 120000},
            {"distanceMeters": 2000, "durationMillis": 423000},
            {"distanceMeters": 150, "durationMillis": 90000},
            {"distanceMeters": 2000, "durationMillis": 425000},
            {"distanceMeters": 50, "durationMillis": 30000},
            {"distanceMeters": 1000, "durationMillis": 215000},
            {"distanceMeters": 100, "durationMillis": 40000},
            {"distanceMeters": 1000, "durationMillis": 213000},
        ]
        response = MagicMock()
        response.read.return_value = json.dumps({"choices": [{"message": {"content": json.dumps({
            "warmup_m": 3800,
            "cooldown_m": None,
            "sets": 1,
            "segments": [
                {"count": 3, "distance_m": 500, "zone": "Z2", "pace": "3:36", "recovery_s": 120},
                {"count": 5, "distance_m": 400, "zone": "Z2", "pace": "3:38", "recovery_s": 120},
            ],
            "confidence": 0.95,
        })}}]}).encode()
        response.__enter__.return_value = response
        with patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"}), patch("core.views.polar_raw.urlopen", return_value=response):
            self.assertEqual(_model_b_ai_description(laps), "")

    def test_model_b_fills_missing_segment_pace_from_measured_laps(self):
        laps = [
            {"distanceMeters": 3000, "durationMillis": 900000},
            {"distanceMeters": 1000, "durationMillis": 240000},
            {"distanceMeters": 100, "durationMillis": 60000},
            {"distanceMeters": 1000, "durationMillis": 246000},
            {"distanceMeters": 100, "durationMillis": 60000},
            {"distanceMeters": 1200, "durationMillis": 420000},
        ]
        response = MagicMock()
        response.read.return_value = json.dumps({"choices": [{"message": {"content": json.dumps({
            "warmup_m": 3000,
            "cooldown_m": 1200,
            "sets": 1,
            "segments": [
                {"count": 2, "distance_m": 1000, "zone": "Z2", "pace": "", "recovery_s": 60},
            ],
            "confidence": 0.95,
        })}}]}).encode()
        response.__enter__.return_value = response
        with patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"}), patch("core.views.polar_raw.urlopen", return_value=response):
            description = _model_b_ai_description(laps)
        self.assertIn("2×1000 m Z2 (4:03) p60", description)

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
            "WU: 3800 m Z1 · Main: 3×2000 m Z2 (3:38) p107 + "
            "2×1000 m Z2 (3:36) p40 · CD: none",
        )

        result = translate([{"sport": {"id": "1"}, "laps": {"laps": laps}}], 5, mode="A", athlete=athlete)
        self.assertEqual(result[0]["parts"][0]["description"], type_a_description(laps, athlete))
        self.assertEqual(result[0]["parts"][0]["training_fields"]["wu"], "3800 m Z1")
        self.assertIn("3×2000 m Z2", result[0]["parts"][0]["training_fields"]["main"])
        self.assertEqual(
            [round(load["meters"]) for load in result[0]["parts"][0]["watch_loads"]],
            [3785, 1987, 338, 2003, 164, 1993, 73, 990, 98, 994, 30],
        )

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
            "WU: 3800 m Z1 · Main: 6×1000 m Z1>Z2 (3:42) p87 · CD: none",
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
            "WU: 4300 m Z1 · Main: 9×100 m Z1>Z3 (3:55) p82 · CD: 4600 m Z1",
        )

    def test_type_a_describes_continuous_run_without_manual_laps(self):
        athlete = SimpleNamespace(
            get_zone_speed_mps=lambda: {"1": 3.0, "2": 3.5, "3": 4.0, "4": 4.5, "5": 5.0},
            pr_tm_s=None, pr_thm_s=None, pr_10000_s=None, pr_5000_s=None,
            pr_3000_s=None, pr_1500_s=None, pr_1000_s=None, pr_800_s=None,
            pr_600_s=None, pr_400_s=None,
        )
        exercise = {
            "sport": {"id": "1"},
            "distanceMeters": 14958.7,
            "durationMillis": 4286783,
        }
        self.assertEqual(
            type_a_general_description(exercise, athlete),
            "Continuous run: 15.0 km Z2 (4:47/km)",
        )
        result = translate([exercise], 5, mode="A", athlete=athlete)
        part = result[0]["parts"][0]
        self.assertEqual(part["description_label"], "General description")
        self.assertEqual(part["description"], "Continuous run: 15.0 km Z2 (4:47/km)")
        self.assertEqual(part["training_fields"], {"wu": "", "main": "15.0 km Z2 (4:47/km)", "cd": ""})

    def test_type_a_treats_one_long_lap_and_gps_remainder_as_continuous_run(self):
        athlete = SimpleNamespace(
            get_zone_speed_mps=lambda: {"1": 3.8, "2": 4.6, "3": 5.0, "4": 5.5, "5": 6.0},
            pr_tm_s=None, pr_thm_s=None, pr_10000_s=None, pr_5000_s=None,
            pr_3000_s=None, pr_1500_s=None, pr_1000_s=None, pr_800_s=None,
            pr_600_s=None, pr_400_s=None,
        )
        description = type_a_description([
            {"distanceMeters": 13170.5, "durationMillis": 3600157},
            {"distanceMeters": 6, "durationMillis": 1375},
        ], athlete)
        self.assertEqual(description, "Continuous run: 13.2 km Z1 (4:33/km)")

    def test_type_a_splits_short_repetitions_and_tolerates_one_gps_outlier(self):
        athlete = SimpleNamespace(
            get_zone_speed_mps=lambda: {"1": 4.0, "2": 4.7, "3": 5.2, "4": 5.7, "5": 6.2},
            pr_tm_s=None, pr_thm_s=None, pr_10000_s=None, pr_5000_s=None,
            pr_3000_s=None, pr_1500_s=None, pr_1000_s=None, pr_800_s=None,
            pr_600_s=None, pr_400_s=None,
        )
        values = [
            (3980.7, 1206782), (42.1, 12000), (65.5, 29750),
            (58.3, 14375), (73.9, 61000), (57.9, 14125),
            (109.3, 60500), (77.1, 16125), (77.0, 61250),
            (50.2, 13125), (136.7, 92625), (100.9, 24125),
            (107.2, 77750), (105.6, 22625), (74.5, 70750),
            (100.7, 23375), (90.4, 69875), (112.5, 23250),
            (55.4, 43875), (4230.6, 1219875),
        ]
        laps = [{"distanceMeters": distance, "durationMillis": duration} for distance, duration in values]
        self.assertEqual(
            type_a_description(laps, athlete),
            "WU: 4000 m Z1 · Main: 5×50 m Z1>Z2 (4:04) p53 + "
            "4×100 m Z1>Z2 (3:42) p73 · CD: 4250 m Z1",
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
