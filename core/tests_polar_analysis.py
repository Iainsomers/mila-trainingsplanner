from types import SimpleNamespace
from unittest.mock import patch
from django.test import SimpleTestCase, TestCase, RequestFactory
from django.contrib.auth import get_user_model
from django.http import HttpResponse
from django.template.loader import render_to_string
from core.models import Athlete, PolarAnalysisSettings
from core.views.polar_analysis import analyze_exercise, analyze_payload, ai_interpretation, validate_hr, hr_upper
from core.views.polar_analysis_settings import analysis_configuration
from core.views.polar_raw import polar_raw_view

REFS = [value / 3.6 for value in [12.9, 15, 18, 20.2, 21.8]]
BOUNDS = [145, 160, 175, 185]


class PolarAnalysisMathTests(SimpleTestCase):
    def test_manual_laps_use_nearest_zone_and_low_hr_belongs_to_z1(self):
        exercise = {"distanceMeters": 800, "durationMillis": 320000,
                    "laps": {"laps": [{"distanceMeters": 400, "durationMillis": 240000}, {"distanceMeters": 400, "durationMillis": 80000}]},
                    "samples": {"samples": [{"type": "DISTANCE", "intervalMillis": 1000, "values": [0, 100, 200, 300, 400, 500, 600, 700, 800]},
                                              {"type": "HEART_RATE", "intervalMillis": 1000, "values": [100, 100, 130, 150, 160, 170, 180, 190, 190]}]}}
        result = analyze_exercise(exercise, REFS, BOUNDS)
        self.assertEqual(result["meters"]["speed"], [400, 0, 400, 0, 0])
        self.assertEqual(result["meters"]["hr"], [300, 100, 200, 100, 100])
        self.assertEqual(result["unclassified_m"], {"speed": 0, "hr": 0})

    def test_missing_hr_is_unclassified_not_carried_forward(self):
        exercise = {"distanceMeters": 30, "durationMillis": 3000,
                    "samples": {"samples": [{"type": "DISTANCE", "intervalMillis": 1000, "values": [0, 10, 20, 30]},
                                              {"type": "HEART_RATE", "intervalMillis": 1000, "values": [140, 140, None, 170]}]}}
        result = analyze_exercise(exercise, REFS, BOUNDS)
        self.assertEqual(result["meters"]["hr"], [10, 0, 0, 0, 0])
        self.assertEqual(result["unclassified_m"]["hr"], 20)

    def test_partial_laps_and_sample_tail_remain_unclassified(self):
        exercise = {"distanceMeters": 500, "laps": {"laps": [{"distanceMeters": 400, "durationMillis": 80000}]}}
        result = analyze_exercise(exercise, REFS, BOUNDS)
        self.assertEqual(result["unclassified_m"]["speed"], 100)
        self.assertEqual(result["unclassified_m"]["hr"], 500)

    def test_fallback_and_invalid_zones(self):
        exercise = {"distanceMeters": 60, "durationMillis": 20000,
                    "samples": {"samples": [{"type": "DISTANCE", "intervalMillis": 1000, "values": [i * 3 for i in range(21)]}]}}
        result = analyze_exercise(exercise, REFS, BOUNDS)
        self.assertEqual(result["method"], "Processed distance samples")
        self.assertEqual(sum(result["meters"]["speed"]), 60)
        self.assertEqual(analyze_exercise(exercise, [], BOUNDS)["unclassified_m"]["speed"], 60)

    def test_hr_validation_and_profile_range_parser(self):
        self.assertEqual(hr_upper("160-170"), 170)
        self.assertEqual(hr_upper("max 145"), 145)
        self.assertEqual(validate_hr(BOUNDS), BOUNDS)
        for value in [[145, 145, 175, 185], [145, None, 175, 185], [145, 160, 175, 250]]:
            with self.assertRaises(ValueError): validate_hr(value)

    def test_non_running_recordings_are_not_mixed_into_running_total(self):
        athlete = SimpleNamespace(get_zone_speed_mps=lambda: {str(i): v for i, v in enumerate(REFS, 1)})
        payload = [{"exercises": [{"sport": {"id": "1"}, "distanceMeters": 100}, {"sport": {"id": "2"}, "distanceMeters": 20000}]}]
        self.assertEqual(len(analyze_payload(payload, athlete, BOUNDS)), 1)

    @patch.dict("os.environ", {"OPENAI_API_KEY": ""})
    def test_ai_unavailable_does_not_affect_tables(self):
        text, error = ai_interpretation([])
        self.assertEqual(text, "")
        self.assertIn("fixed calculations", error)


class PolarAnalysisSettingsTests(TestCase):
    def setUp(self):
        self.coach = get_user_model().objects.create_user(username="polar-owner", is_staff=True)
        self.other = get_user_model().objects.create_user(username="polar-other", is_staff=True)
        self.runner = get_user_model().objects.create_user(username="polar-runner")
        self.athlete = Athlete.objects.create(name="Synthetic Runner", owner=self.coach, birth_year=1997, gender="M")
        self.factory = RequestFactory()
        self.target = {"key": f"athlete:{self.athlete.id}", "athlete": self.athlete, "user": self.runner, "label": "Runner"}

    def request(self, user, save=True, target_key=None):
        data = {"mode": "D", "polar_target": target_key or self.target["key"], "hr_target": self.target["key"], "date": "2026-10-10", "interval": "5", "hr_estimated": "on"}
        data.update({f"hr_upper_{i}": str(value) for i, value in enumerate(BOUNDS, 1)})
        if save: data["save_hr_limits"] = "on"
        request = self.factory.post("/", data)
        request.user, request.session = user, {}
        return request

    def test_owner_and_own_athlete_can_save_and_reload(self):
        for user in [self.coach, self.runner]:
            request = self.request(user)
            context = analysis_configuration(request, self.target, request.POST)
            self.assertEqual(context["hr_bounds"], BOUNDS)
            self.assertTrue(context["hr_estimated"])
        self.assertEqual(PolarAnalysisSettings.objects.get(athlete=self.athlete).hr_upper_bpm, BOUNDS)
        request = self.factory.get("/")
        request.user = self.coach
        self.assertEqual(analysis_configuration(request, self.target, request.GET)["hr_source"], "Saved analysis limits")

    def test_view_only_coach_cannot_save(self):
        request = self.request(self.other)
        with self.assertRaises(ValueError): analysis_configuration(request, self.target, request.POST)
        self.assertFalse(PolarAnalysisSettings.objects.exists())

    def test_stale_form_cannot_save_limits_for_another_selected_athlete(self):
        request = self.request(self.coach)
        other_target = dict(self.target, key="athlete:999")
        with self.assertRaises(ValueError): analysis_configuration(request, other_target, request.POST)
        self.assertFalse(PolarAnalysisSettings.objects.exists())

    @patch("core.views.polar_raw._polar_targets_for_user")
    @patch("core.views.polar_raw._polar_json_request")
    def test_type_d_view_renders_both_distributions_and_stores_limits(self, fetch, targets):
        targets.return_value = [dict(self.target, connection=SimpleNamespace(v4_access_token="secret"))]
        fetch.return_value = (200, [{"exercises": [{"sport": {"id": "1"}, "distanceMeters": 400, "durationMillis": 80000,
                                                  "laps": {"laps": [{"distanceMeters": 400, "durationMillis": 80000}]}}]}])
        with patch("core.views.polar_raw.render", side_effect=lambda request, template, context: HttpResponse(render_to_string(template, context))):
            response = polar_raw_view(self.request(self.coach))
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Speed km", response.content)
        self.assertIn(b"HR km", response.content)
        self.assertIn(b"Estimated HR limits", response.content)
        self.assertNotIn(b"secret", response.content)

    @patch("core.views.polar_raw._polar_targets_for_user")
    @patch("core.views.polar_raw._polar_json_request")
    def test_foreign_target_cannot_mutate_fallback_athlete(self, fetch, targets):
        targets.return_value = [self.target]
        with patch("core.views.polar_raw.render", side_effect=lambda request, template, context: HttpResponse(render_to_string(template, context))):
            response = polar_raw_view(self.request(self.coach, target_key="athlete:999"))
        self.assertIn(b"Unknown athlete", response.content)
        fetch.assert_not_called()
        self.assertFalse(PolarAnalysisSettings.objects.exists())
