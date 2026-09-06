from django.contrib.auth import get_user_model
from datetime import date, timedelta
import json
import os
from pathlib import Path
from unittest.mock import patch

from django.test import TestCase
from django.template.loader import get_template

from core.models import Athlete, AthleteBasePlanningBlock, AthleteBasePlanningSlot, AthleteDailyVital, AthleteDayCheck, CoachAccess, CoachSettings, Group, PlanMembership, PolarConnection, RaceEntry, RaceEvent, RaceEventDistance, StandardStrengthProgram, TrainingPlan, TrainingSegment, TrainingSlot, YearPlannerEntry, YearPlannerWhereabout
from core.views.calendar import _ayc_slot_loads_for_totals, _segment_rep_time_label, _virtual_slot_from_base_training
from core.views.coach import (
    _build_alternative_watch_suggestion,
    _parse_pr_time_to_seconds,
    _race_line_text,
    _race_selected_count,
    _watch_activities_for_plan,
    _watch_plan_is_clear_mismatch,
    _watch_v4_sessions_for_plan,
)


class PolarPlanMismatchTests(TestCase):
    def test_polar_registration_created_status_is_success(self):
        user = get_user_model().objects.create_user(username="polar-user", password="secret")
        self.client.force_login(user)

        responses = [
            (200, {
                "access_token": "token",
                "x_user_id": "12345",
                "token_type": "bearer",
                "expires_in": 3600,
                "scope": "accesslink.read_all",
            }),
            (201, {"user-id": 12345, "member-id": f"mila-user-{user.id}"}),
        ]

        session = self.client.session
        session["polar_oauth_state"] = "state-1"
        session.save()

        with patch.dict(os.environ, {
            "POLAR_CLIENT_ID": "client",
            "POLAR_CLIENT_SECRET": "secret",
            "POLAR_REDIRECT_URI": "http://testserver/integrations/polar/callback/",
        }):
            with patch("core.views.coach._polar_json_request", side_effect=responses):
                response = self.client.get("/integrations/polar/callback/?code=test-code&state=state-1")

        self.assertEqual(response.status_code, 302)
        self.assertIn("connected=1", response["Location"])
        connection = PolarConnection.objects.get(user=user)
        self.assertEqual(connection.status, PolarConnection.STATUS_CONNECTED)
        self.assertEqual(connection.last_error, "")

    def test_running_plan_ignores_cycling_activity_on_same_day(self):
        activities = [
            {"id": "run", "sport": "RUNNING"},
            {"id": "ride", "sport": "CYCLING"},
        ]
        self.assertEqual(
            [item["id"] for item in _watch_activities_for_plan("6*200m z4", activities)],
            ["run"],
        )

    def test_explicit_cycling_plan_selects_cycling_activity(self):
        activities = [
            {"id": "run", "sport": "RUNNING"},
            {"id": "ride", "sport": "CYCLING"},
        ]
        self.assertEqual(
            [item["id"] for item in _watch_activities_for_plan("45 min cycling z2", activities)],
            ["ride"],
        )

    def test_v4_laps_are_also_filtered_by_planned_sport(self):
        sessions = [
            {"id": "run", "sport": "RUNNING"},
            {"id": "ride", "sport": "CYCLING"},
        ]
        self.assertEqual(
            [item["id"] for item in _watch_v4_sessions_for_plan("8*400m", sessions)],
            ["run"],
        )

    def test_clear_structured_mismatch_is_flagged(self):
        self.assertTrue(_watch_plan_is_clear_mismatch(
            "12*400m t3",
            [{"distance_m": 5000}],
            {"mode": "structured_unmatched", "confidence": 0.2, "splits": []},
        ))

    def test_small_distance_difference_is_not_flagged(self):
        self.assertFalse(_watch_plan_is_clear_mismatch(
            "5km z2",
            [{"distance_m": 5100}],
            {"mode": "distance", "confidence": 0.8, "splits": []},
        ))

    def test_alternative_can_use_activity_total_as_safe_fallback(self):
        suggestion = _build_alternative_watch_suggestion([{
            "id": "polar-1", "distance_m": 5000, "duration_seconds": 1500, "raw": {},
        }])

        self.assertEqual(suggestion["mode"], "alternative_reconstruction")
        self.assertEqual(suggestion["activity_id"], "polar-1")
        self.assertEqual(suggestion["splits"][0]["label"], "Continuous block")
        self.assertEqual(suggestion["confidence"], 0.35)

    def test_automatic_kilometre_splits_are_not_treated_as_workout_blocks(self):
        suggestion = _build_alternative_watch_suggestion([{
            "id": "polar-2",
            "distance_m": 14800,
            "duration_seconds": 5757,
            "raw": {
                "distance": 14800,
                "duration": "PT1H35M57S",
                "samples": [{"sample_type": "10", "recording_rate": 1, "data": "0,1000,2000"}],
            },
        }])

        self.assertEqual(len(suggestion["splits"]), 1)
        self.assertEqual(suggestion["splits"][0]["label"], "Continuous block")
        self.assertIn("no reliable lap structure", suggestion["summary"])

    def test_repeating_short_accelerations_are_detected_from_speed_curve(self):
        speeds = []
        for _repeat in range(5):
            speeds.extend([10.0] * 45)
            speeds.extend([16.0] * 25)
        speeds.extend([10.0] * 60)
        suggestion = _build_alternative_watch_suggestion([{
            "id": "fartlek-1",
            "distance_m": 1450,
            "duration_seconds": len(speeds),
            "raw": {
                "distance": 1450,
                "duration": f"PT{len(speeds)}S",
                "samples": [{"sample_type": "1", "recording_rate": 1, "data": speeds}],
            },
        }])

        self.assertEqual(suggestion["mode"], "alternative_pace_pattern")
        self.assertEqual(len(suggestion["splits"]), 5)
        self.assertIn("5 sustained faster sections", suggestion["summary"])

    def test_irregular_pace_changes_do_not_become_a_fake_interval_plan(self):
        speeds = [10.0] * 60
        for fast_seconds, easy_seconds in [(13, 40), (25, 70), (82, 25), (18, 95), (140, 35)]:
            speeds.extend([16.0] * fast_seconds)
            speeds.extend([10.0] * easy_seconds)
        suggestion = _build_alternative_watch_suggestion([{
            "id": "variable-run",
            "distance_m": 4200,
            "duration_seconds": len(speeds),
            "raw": {
                "distance": 4200,
                "duration": f"PT{len(speeds)}S",
                "samples": [{"sample_type": "1", "recording_rate": 1, "data": speeds}],
            },
        }])

        self.assertEqual(suggestion["mode"], "alternative_reconstruction")
        self.assertEqual(len(suggestion["splits"]), 1)
        self.assertIn("no reliable lap structure", suggestion["summary"])

    def test_mobile_ayc_contains_alternative_plan_action(self):
        source = get_template("core/athlete_year_calendar.html").template.source
        self.assertIn("Suggest alternative plan", source)
        self.assertIn("&alternative=1", source)


class TrainerPlanningListTests(TestCase):
    def test_plan_name_shows_owner_name_in_small_muted_text(self):
        coach = get_user_model().objects.create_user(
            username="planowner",
            password="secret",
            first_name="Mila",
            last_name="Coach",
            is_staff=True,
        )
        TrainingPlan.objects.create(
            owner=coach,
            name="Middle distance",
            plan_kind=TrainingPlan.PLAN_KIND_TRAINER,
        )
        self.client.force_login(coach)

        response = self.client.get("/planning/trainer/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Middle distance")
        self.assertContains(
            response,
            '<th>Coach</th>',
            html=False,
        )
        self.assertContains(
            response,
            '<td class="text-start">',
            html=False,
        )
        self.assertContains(
            response,
            '<small class="text-muted trainer-plan-owner">Mila Coach</small>',
            html=False,
        )


class YearPlannerTests(TestCase):
    def _coach_and_athlete(self):
        coach = get_user_model().objects.create_user(
            username="year-coach",
            password="secret",
            is_staff=True,
        )
        athlete = Athlete.objects.create(
            owner=coach,
            name="Year Athlete",
            birth_year=2001,
            gender="X",
        )
        self.client.force_login(coach)
        return coach, athlete

    def test_year_planner_shows_basis_and_selected_athlete(self):
        _, athlete = self._coach_and_athlete()

        response = self.client.get(f"/planning/year/?period=current_next&athletes={athlete.id}")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Basis")
        self.assertContains(response, "Year Athlete")
        self.assertContains(response, "Whereabouts")

    def test_year_planner_does_not_preselect_athletes(self):
        _, athlete = self._coach_and_athlete()

        response = self.client.get("/planning/year/?period=current_next")

        self.assertEqual(response.status_code, 200)
        self.assertTrue(any(row["scope"] == "basis" for row in response.context["rows"]))
        self.assertFalse(any(row["scope"] == f"athlete-{athlete.id}" for row in response.context["rows"]))
        self.assertNotContains(response, f'value="{athlete.id}"\n                checked')
        self.assertContains(response, "year-layout-stack")

    def test_year_planner_can_hide_basis_row(self):
        _, athlete = self._coach_and_athlete()

        response = self.client.get(f"/planning/year/?period=current_next&basis=0&athletes={athlete.id}")

        self.assertEqual(response.status_code, 200)
        self.assertFalse(any(row["scope"] == "basis" for row in response.context["rows"]))
        self.assertContains(response, "Year Athlete")

    def test_year_planner_stacked_layout_renders_chunks(self):
        _, athlete = self._coach_and_athlete()

        response = self.client.get(f"/planning/year/?year=2026&period=season&layout=stack&zoom=3&athletes={athlete.id}")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Sep 2026 - Nov 2026")
        self.assertContains(response, "year-layout-stack")

    def test_year_planner_saves_base_and_athlete_entries(self):
        coach, athlete = self._coach_and_athlete()

        base_response = self.client.post(
            "/planning/year/entry/",
            data=json.dumps({
                "scope": "basis",
                "date": "2026-09-07",
                "training": "aerobe",
            }),
            content_type="application/json",
        )
        athlete_response = self.client.post(
            "/planning/year/entry/",
            data=json.dumps({
                "scope": f"athlete-{athlete.id}",
                "date": "2026-09-07",
                "training": "taper",
            }),
            content_type="application/json",
        )

        self.assertEqual(base_response.status_code, 200)
        self.assertEqual(athlete_response.status_code, 200)
        self.assertTrue(YearPlannerEntry.objects.filter(owner=coach, athlete__isnull=True, training_type="aerobe").exists())
        self.assertTrue(YearPlannerEntry.objects.filter(owner=coach, athlete=athlete, training_type="taper").exists())

    def test_year_planner_saves_whereabout_range(self):
        coach, athlete = self._coach_and_athlete()

        response = self.client.post(
            "/planning/year/whereabout/",
            data=json.dumps({
                "scope": f"athlete-{athlete.id}",
                "start_date": "2026-09-07",
                "end_date": "2026-09-17",
                "whereabouts": "camp",
                "note": "Altitude camp",
            }),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(YearPlannerWhereabout.objects.filter(
            owner=coach,
            athlete=athlete,
            start_date=date(2026, 9, 7),
            end_date=date(2026, 9, 17),
            whereabouts_type="camp",
            note="Altitude camp",
        ).exists())
        page = self.client.get(f"/planning/year/?year=2026&period=season&athletes={athlete.id}")
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, "Altitude camp")

    def test_empty_year_planner_save_deletes_entry(self):
        coach, athlete = self._coach_and_athlete()
        YearPlannerEntry.objects.create(
            owner=coach,
            athlete=athlete,
            date=date(2026, 9, 7),
            training_type="aerobe",
        )

        response = self.client.post(
            "/planning/year/entry/",
            data=json.dumps({
                "scope": f"athlete-{athlete.id}",
                "date": "2026-09-07",
                "training": "",
                "whereabouts": "",
            }),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(YearPlannerEntry.objects.filter(owner=coach, athlete=athlete, date=date(2026, 9, 7)).exists())

    def test_year_planner_group_filter_uses_trainer_plan_references(self):
        coach, athlete = self._coach_and_athlete()
        other = Athlete.objects.create(owner=coach, name="Other Athlete", birth_year=2002, gender="X")
        plan = TrainingPlan.objects.create(
            owner=coach,
            name="Tuesday group",
            plan_kind=TrainingPlan.PLAN_KIND_TRAINER,
        )
        block = AthleteBasePlanningBlock.objects.create(
            athlete=athlete,
            planning_kind=AthleteBasePlanningBlock.KIND_BASE,
            start_month=1,
            start_day=1,
            end_month=12,
            end_day=31,
        )
        AthleteBasePlanningSlot.objects.create(
            block=block,
            weekday=1,
            slot_index=2,
            mode=AthleteBasePlanningSlot.MODE_TRAINER,
            trainer_plan=plan,
        )

        response = self.client.get(f"/planning/year/?period=current_next&athlete_group=plan-{plan.id}")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Year Athlete")
        self.assertNotContains(response, "Other Athlete")


class SlotModalSaveTests(TestCase):
    def _user_plan_and_athlete(self):
        user = get_user_model().objects.create_user(
            username="coach",
            password="secret",
            is_staff=True,
        )
        plan = TrainingPlan.objects.create(owner=user, name="Plan")
        athlete = Athlete.objects.create(
            owner=user,
            name="Athlete",
            birth_year=2000,
            gender="X",
            auto_wucd_enabled=True,
            auto_wu_m=1500,
            auto_cd_m=1000,
        )
        PlanMembership.objects.create(plan=plan, athlete=athlete)
        self.client.force_login(user)
        return user, plan, athlete

    def test_cd_is_saved_after_all_split_core_segments(self):
        user = get_user_model().objects.create_user(
            username="coach",
            password="secret",
        )
        plan = TrainingPlan.objects.create(owner=user, name="Plan")
        self.client.force_login(user)

        response = self.client.post(
            f"/slot-modal/2026/01/05/1/?plan={plan.id}",
            {
                "plan": str(plan.id),
                "core_text": "1000m z3 // 1000m z4 // 1000m z5",
                "cd_text": "10min z1",
            },
        )

        self.assertEqual(response.status_code, 200)
        slot = TrainingSlot.objects.get(plan=plan, date="2026-01-05", slot_index=1)
        segments = list(slot.segments.order_by("order", "id"))

        self.assertEqual([seg.type for seg in segments], ["CORE", "CORE", "CORE", "CD"])
        cd_order = next(seg.order for seg in segments if seg.type == "CD")
        core_orders = [seg.order for seg in segments if seg.type == "CORE"]
        self.assertGreater(cd_order, max(core_orders))

    def test_auto_wucd_is_applied_when_core_is_present(self):
        _, plan, athlete = self._user_plan_and_athlete()

        response = self.client.post(
            f"/slot-modal/2026/01/06/1/?plan={plan.id}&athlete={athlete.id}",
            {
                "plan": str(plan.id),
                "athlete": str(athlete.id),
                "core_text": "1000m z3",
            },
        )

        self.assertEqual(response.status_code, 200)
        slot = TrainingSlot.objects.get(plan=plan, athlete=athlete, date="2026-01-06", slot_index=1)
        segments = list(slot.segments.order_by("order", "id"))
        self.assertEqual([seg.type for seg in segments], ["WU", "CORE", "CD"])
        self.assertEqual(segments[0].text, "1500m z1")
        self.assertEqual(segments[-1].text, "1000m z1")

    def test_auto_wucd_is_not_applied_without_core(self):
        _, plan, athlete = self._user_plan_and_athlete()

        response = self.client.post(
            f"/slot-modal/2026/01/07/1/?plan={plan.id}&athlete={athlete.id}",
            {
                "plan": str(plan.id),
                "athlete": str(athlete.id),
                "mob_text": "drills",
            },
        )

        self.assertEqual(response.status_code, 200)
        slot = TrainingSlot.objects.get(plan=plan, athlete=athlete, date="2026-01-07", slot_index=1)
        segments = list(slot.segments.order_by("order", "id"))
        self.assertEqual([seg.type for seg in segments], ["MOB"])

    def test_auto_wucd_is_not_applied_when_any_main_contains_z1(self):
        _, plan, athlete = self._user_plan_and_athlete()

        response = self.client.post(
            f"/slot-modal/2026/01/09/1/?plan={plan.id}&athlete={athlete.id}",
            {
                "plan": str(plan.id),
                "athlete": str(athlete.id),
                "core_text": "1000m z1 // 1000m z2",
            },
        )

        self.assertEqual(response.status_code, 200)
        slot = TrainingSlot.objects.get(plan=plan, athlete=athlete, date="2026-01-09", slot_index=1)
        segments = list(slot.segments.order_by("order", "id"))
        self.assertEqual([seg.type for seg in segments], ["CORE", "CORE"])

    def test_auto_wucd_is_applied_for_z2_only_main(self):
        _, plan, athlete = self._user_plan_and_athlete()

        response = self.client.post(
            f"/slot-modal/2026/01/11/1/?plan={plan.id}&athlete={athlete.id}",
            {
                "plan": str(plan.id),
                "athlete": str(athlete.id),
                "core_text": "40min z2",
            },
        )

        self.assertEqual(response.status_code, 200)
        slot = TrainingSlot.objects.get(plan=plan, athlete=athlete, date="2026-01-11", slot_index=1)
        segments = list(slot.segments.order_by("order", "id"))
        self.assertEqual([seg.type for seg in segments], ["WU", "CORE", "CD"])

    def test_group_auto_wucd_is_applied_for_base_plan_training(self):
        user = get_user_model().objects.create_user(
            username="groupcoach",
            password="secret",
            is_staff=True,
        )
        athlete = Athlete.objects.create(
            owner=user,
            name="Group Athlete",
            birth_year=2000,
            gender="X",
        )
        group = Group.objects.create(
            owner=user,
            name="Group",
            auto_wucd_enabled=True,
            auto_wu_m=1200,
            auto_cd_m=800,
        )
        group.athletes.add(athlete)
        plan = TrainingPlan.objects.create(owner=user, name="Group Plan")
        plan.groups.add(group)
        self.client.force_login(user)

        response = self.client.post(
            f"/slot-modal/2026/01/10/1/?plan={plan.id}",
            {
                "plan": str(plan.id),
                "core_text": "1000m z3",
            },
        )

        self.assertEqual(response.status_code, 200)
        slot = TrainingSlot.objects.get(plan=plan, athlete__isnull=True, date="2026-01-10", slot_index=1)
        segments = list(slot.segments.order_by("order", "id"))
        self.assertEqual([seg.type for seg in segments], ["WU", "CORE", "CD"])
        self.assertEqual(segments[0].text, "1200m z1")
        self.assertEqual(segments[-1].text, "800m z1")

    def test_athlete_auto_wucd_overrides_group_base_training(self):
        user = get_user_model().objects.create_user(
            username="mixedcoach",
            password="secret",
            is_staff=True,
        )
        group = Group.objects.create(
            owner=user,
            name="Mixed Group",
            auto_wucd_enabled=True,
            auto_wu_m=700,
            auto_cd_m=700,
        )
        group_athlete = Athlete.objects.create(
            owner=user,
            name="Group Setting Athlete",
            birth_year=2000,
            gender="X",
        )
        athlete_setting_athlete = Athlete.objects.create(
            owner=user,
            name="Athlete Setting Athlete",
            birth_year=2000,
            gender="X",
            auto_wucd_enabled=True,
            auto_wu_m=1500,
            auto_cd_m=1000,
        )
        group.athletes.add(group_athlete, athlete_setting_athlete)
        plan = TrainingPlan.objects.create(owner=user, name="Mixed Plan")
        plan.groups.add(group)
        self.client.force_login(user)

        response = self.client.post(
            f"/slot-modal/2026/01/11/1/?plan={plan.id}",
            {
                "plan": str(plan.id),
                "core_text": "1000m z3",
            },
        )

        self.assertEqual(response.status_code, 200)
        base_slot = TrainingSlot.objects.get(plan=plan, athlete__isnull=True, date="2026-01-11", slot_index=1)
        base_segments = list(base_slot.segments.order_by("order", "id"))
        self.assertEqual(base_segments[0].text, "700m z1")
        self.assertEqual(base_segments[-1].text, "700m z1")

        athlete_slot = TrainingSlot.objects.get(plan=plan, athlete=athlete_setting_athlete, date="2026-01-11", slot_index=1)
        athlete_segments = list(athlete_slot.segments.order_by("order", "id"))
        self.assertEqual([seg.type for seg in athlete_segments], ["WU", "CORE", "CD"])
        self.assertEqual(athlete_segments[0].text, "1500m z1")
        self.assertEqual(athlete_segments[-1].text, "1000m z1")
        self.assertFalse(TrainingSlot.objects.filter(plan=plan, athlete=group_athlete, date="2026-01-11", slot_index=1).exists())

    def test_athlete_year_can_create_training_without_existing_slot(self):
        _, plan, athlete = self._user_plan_and_athlete()

        response = self.client.post(
            f"/athlete/year/?year=2026&athlete={athlete.id}",
            {
                "date": "2026-01-08",
                "slot_index": "1",
                "plan": str(plan.id),
                "slot_text": "1000m z3",
                "core_text": "1000m z3",
            },
        )

        self.assertEqual(response.status_code, 200)
        slot = TrainingSlot.objects.get(plan=plan, athlete=athlete, date="2026-01-08", slot_index=1)
        segments = list(slot.segments.order_by("order", "id"))
        self.assertEqual([seg.type for seg in segments], ["WU", "CORE", "CD"])
        self.assertEqual(segments[1].text, "1000m z3")

    def test_mobile_pm_training_contains_modal_prefill_values(self):
        template_path = get_template("core/athlete_year_calendar.html").origin.name
        template_source = Path(template_path).read_text(encoding="utf-8")
        pm_mobile_block = template_source.split(
            '<div class="ayc-mobile-slot-label">PM</div>', 1
        )[1].split('</div>\n          </div>', 1)[0]

        for field in ("wu", "mob", "sprint", "core", "core2", "alt", "cd"):
            self.assertIn(f'data-prefill-{field}=', pm_mobile_block)

    def test_authenticated_pages_offer_post_logout_to_login(self):
        self._user_plan_and_athlete()

        response = self.client.get("/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'method="post" action="/logout/"', html=False)

        logout_response = self.client.post("/logout/")
        self.assertRedirects(logout_response, "/login/", fetch_redirect_response=False)

    def test_athlete_sees_base_planning_tab_as_read_only(self):
        coach = get_user_model().objects.create_user(
            username="baseplanningcoach", password="secret", is_staff=True
        )
        athlete_user = get_user_model().objects.create_user(
            username="baseplanningathlete", password="secret"
        )
        athlete = Athlete.objects.create(
            owner=coach,
            name="baseplanningathlete",
            birth_year=2000,
            gender="X",
        )
        self.client.force_login(athlete_user)

        settings_response = self.client.get("/athlete/settings/?tab=base-planning")
        self.assertEqual(settings_response.status_code, 200)
        self.assertContains(settings_response, "Base planning")
        self.assertContains(settings_response, "readonly=1", html=False)

        base_response = self.client.get(
            f"/planning/base/?athlete={athlete.id}&embedded=1&kind=base"
        )
        self.assertEqual(base_response.status_code, 200)
        self.assertContains(base_response, "View only")
        blocked_post = self.client.post(
            "/planning/base/",
            {"athlete_id": str(athlete.id), "kind": "base", "action": "add_block"},
        )
        self.assertEqual(blocked_post.status_code, 403)

    def test_mobile_ayc_template_contains_week_reports_and_vitals_popup(self):
        _, _, athlete = self._user_plan_and_athlete()
        athlete.week_report_enabled = True
        athlete.daily_vitals_enabled = True
        athlete.save(update_fields=["week_report_enabled", "daily_vitals_enabled"])

        response = self.client.get(f"/athlete/year/?year=2026&athlete={athlete.id}")
        self.assertEqual(response.status_code, 200)
        template_source = response.content.decode()

        self.assertIn('class="ayc-mobile-week-report"', template_source)
        for field in ("comm_athlete", "comm_trainer", "match_report", "injuries"):
            self.assertIn(f'data-field="{field}"', template_source)
        self.assertIn('class="btn btn-sm btn-outline-danger ayc-mobile-vitals-button"', template_source)
        self.assertIn('id="mobileVitalsModal"', template_source)
        self.assertIn('class="ayc-mobile-vitals-avg"', template_source)

    def test_mobile_vitals_batch_saves_all_four_values(self):
        _, _, athlete = self._user_plan_and_athlete()
        athlete.daily_vitals_enabled = True
        athlete.save(update_fields=["daily_vitals_enabled"])
        day = date.today().isoformat()

        response = self.client.post(
            f"/athlete/year/?year={date.today().year}&athlete={athlete.id}",
            {
                "date": day,
                "daily_vitals_submit": "1",
                "daily_vitals_batch": "1",
                "sleep_hours": "7.75",
                "sleep_quality": "8",
                "morning_hr": "48",
                "hrv": "72",
            },
        )

        self.assertRedirects(response, f"/athlete/year/?year={date.today().year}&athlete={athlete.id}")
        vital = AthleteDailyVital.objects.get(athlete=athlete, date=day)
        self.assertEqual(vital.sleep_hours, 7.75)
        self.assertEqual(vital.sleep_quality, 8)
        self.assertEqual(vital.morning_hr, 48)
        self.assertEqual(vital.hrv, 72)

        page = self.client.get(f"/athlete/year/?year={date.today().year}&athlete={athlete.id}")
        self.assertContains(page, 'id="mobileVitalsForm"')
        self.assertContains(page, 'X-Requested-With', html=False)
        self.assertContains(page, 'bootstrap.Modal.getOrCreateInstance(modalEl).hide()', html=False)
        for field_name in ("sleep_hours", "sleep_quality", "morning_hr", "hrv"):
            self.assertContains(page, f'name="{field_name}"', html=False)

        ajax_response = self.client.post(
            f"/athlete/year/?year={date.today().year}&athlete={athlete.id}",
            {
                "date": day,
                "daily_vitals_submit": "1",
                "daily_vitals_batch": "1",
                "sleep_hours": "8.25",
                "sleep_quality": "9",
                "morning_hr": "46",
                "hrv": "77",
            },
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(ajax_response.status_code, 204)
        vital.refresh_from_db()
        self.assertEqual(vital.sleep_hours, 8.25)
        self.assertEqual(vital.sleep_quality, 9)
        self.assertEqual(vital.morning_hr, 46)
        self.assertEqual(vital.hrv, 77)

        refreshed_page = self.client.get(
            f"/athlete/year/?year={date.today().year}&athlete={athlete.id}"
        )
        self.assertContains(refreshed_page, 'data-vitals-sleep-hours="8.25"', html=False)
        self.assertContains(refreshed_page, 'data-vitals-sleep-quality="9"', html=False)
        self.assertContains(refreshed_page, 'data-vitals-morning-hr="46"', html=False)
        self.assertContains(refreshed_page, 'data-vitals-hrv="77"', html=False)

    def test_coach_can_save_future_vitals_and_training_report_for_selected_athlete(self):
        _, _, athlete = self._user_plan_and_athlete()
        athlete.daily_vitals_enabled = True
        athlete.save(update_fields=["daily_vitals_enabled"])
        future_day = date.today() + timedelta(days=2)

        vital_response = self.client.post(
            f"/athlete/year/?year={future_day.year}&athlete={athlete.id}",
            {
                "date": future_day.isoformat(),
                "daily_vitals_submit": "1",
                "daily_vitals_batch": "1",
                "sleep_hours": "7.5",
                "sleep_quality": "8",
                "morning_hr": "49",
                "hrv": "70",
            },
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(vital_response.status_code, 204)
        self.assertTrue(
            AthleteDailyVital.objects.filter(athlete=athlete, date=future_day).exists()
        )

        desktop_vital_response = self.client.post(
            f"/athlete/year/?year={future_day.year}&athlete={athlete.id}",
            {
                "date": future_day.isoformat(),
                "daily_vitals_submit": "1",
                "field": "morning_hr",
                "value": "47",
            },
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(desktop_vital_response.status_code, 204)
        saved_vital = AthleteDailyVital.objects.get(athlete=athlete, date=future_day)
        self.assertEqual(saved_vital.morning_hr, 47)

        report_response = self.client.post(
            f"/athlete/year/?year={future_day.year}&athlete={athlete.id}",
            {
                "date": future_day.isoformat(),
                "slot_index": "1",
                "report_submit": "1",
                "check_status": "done_as_planned",
                "rpe": "6",
                "report_comment": "Coach test report",
            },
        )
        self.assertEqual(report_response.status_code, 200)
        saved_report = AthleteDayCheck.objects.get(
            athlete=athlete, date=future_day, slot_index=1
        )
        self.assertEqual(saved_report.rpe, 6)
        self.assertEqual(saved_report.comment, "Coach test report")

        desktop_page = self.client.get(
            f"/athlete/year/?year={future_day.year}&athlete={athlete.id}"
        )
        desktop_vitals_script = desktop_page.content.decode().split(
            "function postDailyVital(el)", 1
        )[1].split("</script>", 1)[0]
        self.assertNotIn("window.location.reload();", desktop_vitals_script)
        self.assertIn('"X-Requested-With": "XMLHttpRequest"', desktop_vitals_script)

    def test_shared_coach_can_save_vitals_for_accessible_athlete(self):
        owner = get_user_model().objects.create_user(
            username="athleteowner", password="secret", is_staff=True
        )
        shared_coach = get_user_model().objects.create_user(
            username="sharedcoach", password="secret", is_staff=True
        )
        athlete = Athlete.objects.create(
            owner=owner,
            name="Shared athlete",
            birth_year=2000,
            gender="X",
            daily_vitals_enabled=True,
            is_private=False,
        )
        CoachAccess.objects.create(owner=owner, grantee=shared_coach, can_edit=True)
        self.client.force_login(shared_coach)

        dashboard = self.client.get("/")
        self.assertContains(dashboard, "View as coach")
        self.assertContains(dashboard, "athleteowner")

        own_page = self.client.get(
            f"/athlete/year/?year={date.today().year}&athlete={athlete.id}"
        )
        self.assertNotContains(own_page, "Shared athlete")

        self.client.post("/", {"coach_view_owner": str(owner.id)})

        page = self.client.get(
            f"/athlete/year/?year={date.today().year}&athlete={athlete.id}"
        )
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, "Shared athlete")

        response = self.client.post(
            f"/athlete/year/?year={date.today().year}&athlete={athlete.id}",
            {
                "date": date.today().isoformat(),
                "daily_vitals_submit": "1",
                "field": "hrv",
                "value": "81",
            },
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(response.status_code, 204)
        self.assertEqual(
            AthleteDailyVital.objects.get(athlete=athlete, date=date.today()).hrv,
            81,
        )

        report_response = self.client.post(
            f"/athlete/year/?year={date.today().year}&athlete={athlete.id}",
            {
                "date": date.today().isoformat(),
                "slot_index": "1",
                "report_submit": "1",
                "check_status": "adjusted_ok",
                "rpe": "5",
                "report_comment": "Shared coach report",
            },
        )
        self.assertEqual(report_response.status_code, 200)
        shared_report = AthleteDayCheck.objects.get(
            athlete=athlete, date=date.today(), slot_index=1
        )
        self.assertEqual(shared_report.status, "adjusted_ok")
        self.assertEqual(shared_report.comment, "Shared coach report")

    def test_coach_view_dropdown_is_not_transitive(self):
        coach_a = get_user_model().objects.create_user(
            username="coach-a", password="secret", is_staff=True
        )
        coach_b = get_user_model().objects.create_user(
            username="coach-b", password="secret", is_staff=True
        )
        coach_c = get_user_model().objects.create_user(
            username="coach-c", password="secret", is_staff=True
        )
        CoachAccess.objects.create(owner=coach_b, grantee=coach_a, can_edit=True)
        CoachAccess.objects.create(owner=coach_c, grantee=coach_b, can_edit=True)

        Athlete.objects.create(
            owner=coach_b,
            name="B athlete",
            birth_year=2000,
            gender="X",
            is_private=False,
        )
        Athlete.objects.create(
            owner=coach_c,
            name="C athlete",
            birth_year=2000,
            gender="X",
            is_private=False,
        )

        self.client.force_login(coach_a)
        dashboard = self.client.get("/")
        self.assertContains(dashboard, "coach-b")
        self.assertNotContains(dashboard, "coach-c")

        self.client.post("/", {"coach_view_owner": str(coach_c.id)})
        athletes_page = self.client.get("/coach/athletes/")
        self.assertNotContains(athletes_page, "C athlete")

        self.client.post("/", {"coach_view_owner": str(coach_b.id)})
        athletes_page = self.client.get("/coach/athletes/")
        self.assertContains(athletes_page, "B athlete")
        self.assertNotContains(athletes_page, "C athlete")

    def test_view_only_coach_access_blocks_writes(self):
        owner = get_user_model().objects.create_user(
            username="view-owner", password="secret", is_staff=True
        )
        shared_coach = get_user_model().objects.create_user(
            username="view-only-coach", password="secret", is_staff=True
        )
        athlete = Athlete.objects.create(
            owner=owner,
            name="View only athlete",
            birth_year=2000,
            gender="X",
            is_private=False,
        )
        CoachAccess.objects.create(owner=owner, grantee=shared_coach)

        self.client.force_login(shared_coach)
        self.client.post("/", {"coach_view_owner": str(owner.id)})

        page = self.client.get(
            f"/athlete/year/?year={date.today().year}&athlete={athlete.id}"
        )
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, "View only athlete")

        response = self.client.post(
            f"/athlete/year/?year={date.today().year}&athlete={athlete.id}",
            {
                "date": date.today().isoformat(),
                "daily_vitals_submit": "1",
                "field": "hrv",
                "value": "81",
            },
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(response.status_code, 403)
        self.assertFalse(AthleteDailyVital.objects.filter(athlete=athlete).exists())


class SegmentRepTimeDisplayTests(TestCase):
    def test_compound_reps_show_split_times_for_current_and_goal_pr(self):
        athlete = Athlete.objects.create(
            name="Runner",
            birth_year=2000,
            gender="X",
            pr_1500_s=295,
            target_pr_1500_s=285,
        )
        segment = TrainingSegment(
            type="CORE",
            text="2*(600m-400m) t15",
            t_type="1500",
            reps=2,
            distance_m=1000,
            norm_distance_m=2000,
        )

        self.assertEqual(_segment_rep_time_label(athlete, segment), "1:58/1:19-->1:54/1:16")

    def test_compound_reps_use_zones_inside_parentheses_per_part(self):
        athlete = Athlete.objects.create(
            name="Zone Runner",
            birth_year=2000,
            gender="X",
            zone_speed_mps={
                "1": 100 / 30,
                "2": 300 / 76,
                "3": 3.4,
                "4": 3.8,
                "5": 4.2,
                "6": 4.6,
            },
        )
        segment = TrainingSegment(
            type="CORE",
            text="24*(300m z2-100m z1)",
            reps=24,
            distance_m=400,
            norm_distance_m=9600,
        )

        self.assertEqual(_segment_rep_time_label(athlete, segment), "1:16/0:30")

    def test_compound_reps_keep_outer_zone_for_all_parts(self):
        athlete = Athlete.objects.create(
            name="Outer Zone Runner",
            birth_year=2001,
            gender="X",
            zone_speed_mps={
                "1": 100 / 30,
                "2": 300 / 76,
                "3": 3.4,
                "4": 3.8,
                "5": 4.2,
                "6": 4.6,
            },
        )
        segment = TrainingSegment(
            type="CORE",
            text="24*(300m-100m) z2",
            zone="2",
            reps=24,
            distance_m=400,
            norm_distance_m=9600,
        )

        self.assertEqual(_segment_rep_time_label(athlete, segment), "1:16/0:25")

    def test_duration_reps_show_current_and_goal_t_pace(self):
        athlete = Athlete.objects.create(
            name="Time Runner",
            birth_year=2000,
            gender="X",
            pr_1500_s=300,
            target_pr_1500_s=285,
        )
        segment = TrainingSegment(
            type="CORE",
            text="10*1' t15",
            t_type="1500",
            reps=10,
            duration_s=600,
        )

        self.assertEqual(_segment_rep_time_label(athlete, segment), "3:20-->3:10 min/km")

    def test_duration_segment_shows_zone_pace(self):
        athlete = Athlete.objects.create(
            name="Zone Time Runner",
            birth_year=2000,
            gender="X",
            zone_speed_mps={"3": 1000 / 240},
        )
        segment = TrainingSegment(
            type="CORE",
            text='90" z3',
            zone="3",
            duration_s=90,
        )

        self.assertEqual(_segment_rep_time_label(athlete, segment), "4:00 min/km")


class RaceSelectDisplayTests(TestCase):
    def test_athlete_uses_race_calendar_with_own_selection_controls(self):
        coach = get_user_model().objects.create_user(
            username="calendarowner", password="secret", is_staff=True
        )
        athlete_user = get_user_model().objects.create_user(
            username="calendarathlete", password="secret"
        )
        athlete = Athlete.objects.create(
            owner=coach, name="calendarathlete", birth_year=2000, gender="X"
        )
        race = RaceEvent.objects.create(owner=coach, name="Shared race", date="2026-07-16")
        distance = RaceEventDistance.objects.create(race=race, distance="1500")
        self.client.force_login(athlete_user)

        response = self.client.get("/race-calendar/?year=2026&period=full")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["view_mode"], "list")
        self.assertContains(response, "Shared race")
        self.assertContains(response, "calendarathlete")
        self.assertContains(response, "Add race")
        self.assertContains(response, 'class="race-entry-athlete"', html=False)
        self.assertContains(response, "open>", html=False)
        self.assertContains(
            response,
            f'name="coach_{athlete.id}_{distance.id}" value="1"  disabled',
            html=False,
        )
        self.assertContains(
            response,
            f'name="athlete_{athlete.id}_{distance.id}" value="1"',
            html=False,
        )
        self.assertNotContains(response, "Save selections")
        self.assertContains(response, 'data-auto-save="1"', html=False)

        athlete_calendar = self.client.get("/race-calendar/?year=2026&view=calendar&period=full")
        self.assertContains(athlete_calendar, 'class="race-calendar-event race-calendar-none"', html=False)
        self.assertNotContains(athlete_calendar, '<span class="race-calendar-count">', html=False)

        auto_save_response = self.client.post(
            f"/race-calendar/{race.id}/entries/save/",
            {f"athlete_{athlete.id}_{distance.id}": "1"},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(auto_save_response.status_code, 200)
        self.assertEqual(auto_save_response.json(), {"ok": True})
        self.assertTrue(RaceEntry.objects.get(race_distance=distance, athlete=athlete).athlete_selected)

        add_from_list = self.client.post(
            "/race-calendar/",
            {
                "name": "Athlete list race",
                "date": "2026-09-01",
                "view": "list",
                "period": "full",
            },
        )
        self.assertEqual(add_from_list.status_code, 302)
        self.assertTrue(
            RaceEvent.objects.filter(owner=coach, name="Athlete list race").exists()
        )
        athlete_distance_response = self.client.post(
            f"/race-calendar/{race.id}/distances/add/",
            {
                "distances": "800",
                "remove_distances": str(distance.id),
                "view": "list",
                "period": "full",
            },
        )
        self.assertEqual(athlete_distance_response.status_code, 302)
        self.assertTrue(RaceEventDistance.objects.filter(id=distance.id).exists())
        self.assertTrue(
            RaceEventDistance.objects.filter(race=race, distance="800").exists()
        )
        athlete_distance_page = self.client.get(
            "/race-calendar/?year=2026&view=list&period=full"
        )
        self.assertContains(athlete_distance_page, "Save distances")
        self.assertNotContains(athlete_distance_page, 'name="remove_distances"', html=False)

        athlete_calendar_add = self.client.get(
            "/race-calendar/?year=2026&view=calendar&period=full"
        )
        self.assertContains(athlete_calendar_add, 'id="addRaceDateModal"', html=False)
        self.assertContains(athlete_calendar_add, 'data-bs-target="#addRaceDateModal"', html=False)
        add_from_calendar = self.client.post(
            "/race-calendar/",
            {
                "name": "Athlete calendar race",
                "date": "2026-09-02",
                "view": "calendar",
                "period": "full",
            },
        )
        self.assertEqual(add_from_calendar.status_code, 302)
        self.assertTrue(
            RaceEvent.objects.filter(owner=coach, name="Athlete calendar race").exists()
        )

        participating_calendar = self.client.get(
            "/race-calendar/?year=2026&view=calendar&period=full"
        )
        self.assertContains(participating_calendar, 'class="race-calendar-event race-calendar-pending"', html=False)
        self.assertNotContains(participating_calendar, '<span class="race-calendar-count">', html=False)

        planning_response = self.client.get("/planning/")
        self.assertContains(planning_response, 'href="/race-calendar/"', html=False)
        self.assertNotContains(planning_response, "/race-select/?scope=athlete", html=False)

    def test_race_agreement_changes_pending_pill_to_filled_target_pill(self):
        coach = get_user_model().objects.create_user(
            username="agreementcoach", password="secret", is_staff=True
        )
        athlete_user = get_user_model().objects.create_user(
            username="agreementathlete", password="secret"
        )
        athlete = Athlete.objects.create(
            owner=coach, name="agreementathlete", birth_year=2000, gender="X"
        )
        plan = TrainingPlan.objects.create(
            owner=coach,
            name="Agreement plan",
            start_date="2026-01-01",
            end_date="2026-12-31",
        )
        PlanMembership.objects.create(plan=plan, athlete=athlete)
        race = RaceEvent.objects.create(owner=coach, name="Agreement race", date="2026-07-16")
        distance = RaceEventDistance.objects.create(race=race, distance="1500")

        self.client.force_login(coach)
        coach_response = self.client.post(
            f"/race-calendar/{race.id}/entries/save/",
            {
                "athletes": str(athlete.id),
                f"coach_{athlete.id}_{distance.id}": "1",
                "view": "list",
                "period": "full",
            },
        )
        self.assertEqual(coach_response.status_code, 302)
        entry = RaceEntry.objects.get(race_distance=distance, athlete=athlete)
        self.assertTrue(entry.coach_selected)
        self.assertFalse(entry.athlete_selected)
        pending_segment = TrainingSegment.objects.filter(
            slot__athlete=athlete, text__contains="Agreement race", special="RACE_PENDING"
        ).first()
        self.assertIsNotNone(pending_segment)
        pending_html = get_template("core/partials/segment_display.html").render(
            {"seg": pending_segment}
        )
        self.assertIn("pill-race-pending", pending_html)
        pending_calendar = self.client.get(
            "/race-calendar/?year=2026&view=list&period=full"
        )
        self.assertNotContains(pending_calendar, "race-summary-pill", html=False)

        self.client.force_login(athlete_user)
        athlete_pending_calendar = self.client.get(
            "/race-calendar/?year=2026&period=full"
        )
        self.assertContains(athlete_pending_calendar, "race-choice-pending", html=False)
        self.assertContains(athlete_pending_calendar, "1500m")
        self.assertContains(athlete_pending_calendar, "refreshAthleteRacePill", html=False)

        athlete_response = self.client.post(
            f"/race-calendar/{race.id}/entries/save/",
            {
                f"athlete_{athlete.id}_{distance.id}": "1",
                f"target_{athlete.id}_{distance.id}": "1",
                "view": "list",
                "period": "full",
            },
        )
        self.assertEqual(athlete_response.status_code, 302)
        entry.refresh_from_db()
        self.assertTrue(entry.coach_selected)
        self.assertTrue(entry.athlete_selected)
        self.assertTrue(entry.target_selected)
        confirmed_segment = TrainingSegment.objects.filter(
            slot__athlete=athlete, text__contains="Agreement race", special="IMPORTANT_RACE"
        ).first()
        self.assertIsNotNone(confirmed_segment)
        confirmed_html = get_template("core/partials/segment_display.html").render(
            {"seg": confirmed_segment}
        )
        self.assertIn("pill-important-race", confirmed_html)

    def test_race_calendar_list_hides_distance_choices_until_race_is_opened(self):
        coach = get_user_model().objects.create_user(
            username="racecalendarcoach", password="secret", is_staff=True
        )
        athlete = Athlete.objects.create(
            owner=coach, name="Race list athlete", birth_year=2000, gender="X"
        )
        trainer_plan = TrainingPlan.objects.create(
            owner=coach,
            name="Race group",
            plan_kind=TrainingPlan.PLAN_KIND_TRAINER,
        )
        base_block = AthleteBasePlanningBlock.objects.create(
            athlete=athlete,
            planning_kind=AthleteBasePlanningBlock.KIND_BASE,
            label="Race block",
            start_month=1,
            start_day=1,
            end_month=12,
            end_day=31,
        )
        AthleteBasePlanningSlot.objects.create(
            block=base_block,
            weekday=0,
            slot_index=1,
            mode=AthleteBasePlanningSlot.MODE_TRAINER,
            trainer_plan=trainer_plan,
        )
        race = RaceEvent.objects.create(
            owner=coach, name="Track meeting", date="2026-07-16"
        )
        distance = RaceEventDistance.objects.create(race=race, distance="1500")
        RaceEntry.objects.create(
            race_distance=distance,
            athlete=athlete,
            coach_selected=True,
            athlete_selected=True,
        )
        self.client.force_login(coach)

        response = self.client.get("/race-calendar/?year=2026&view=list&period=full")

        self.assertEqual(response.status_code, 200)
        source = response.content.decode()
        list_section = source.split('<div class="race-list">', 1)[1].split(
            '<div class="modal fade"', 1
        )[0]
        self.assertIn('class="race-list-item"', list_section)
        self.assertIn(f'data-bs-target="#raceModal{race.id}"', list_section)
        self.assertIn("1500m", list_section)
        self.assertNotIn('name="distances"', list_section)
        self.assertNotIn("Save distances", list_section)
        self.assertContains(response, "grid-template-columns: 220px minmax(0, 1fr)", html=False)
        self.assertContains(response, 'class="race-distance-management"', html=False)
        self.assertContains(response, 'class="race-entry-athlete"', html=False)
        self.assertNotContains(response, "Save selections")
        self.assertContains(response, 'data-auto-save="1"', html=False)
        self.assertNotContains(response, "Open selected", html=False)
        self.assertContains(response, "refreshRaceSummary", html=False)
        self.assertContains(response, f'value="plan:{trainer_plan.id}"', html=False)
        self.assertContains(response, "Race group")
        self.assertContains(response, f'data-plan-ids="{trainer_plan.id}"', html=False)
        self.assertContains(response, 'class="race-distance-count">1</span>', html=False)
        self.assertNotContains(response, 'race-participant-badge', html=False)
        self.assertContains(response, 'class="card race-filter-card"', html=False)
        self.assertContains(response, "grid-template-columns: repeat(2, minmax(0, 1fr))", html=False)
        self.assertContains(response, f'value="athlete:{athlete.id}"', html=False)

        trainer_auto_save = self.client.post(
            f"/race-calendar/{race.id}/entries/save/",
            {
                "athletes": str(athlete.id),
                f"coach_{athlete.id}_{distance.id}": "1",
                f"target_{athlete.id}_{distance.id}": "1",
            },
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(trainer_auto_save.status_code, 200)
        self.assertEqual(trainer_auto_save.json(), {"ok": True})
        saved_entry = RaceEntry.objects.get(race_distance=distance, athlete=athlete)
        self.assertTrue(saved_entry.coach_selected)
        self.assertTrue(saved_entry.target_selected)

    def test_race_calendar_scope_filters_races_and_distance_counts(self):
        coach = get_user_model().objects.create_user(
            username="racefiltercoach", password="secret", is_staff=True
        )
        athlete_one = Athlete.objects.create(
            owner=coach, name="Filtered athlete", birth_year=2000, gender="X"
        )
        athlete_two = Athlete.objects.create(
            owner=coach, name="Other athlete", birth_year=2001, gender="X"
        )
        trainer_plan = TrainingPlan.objects.create(
            owner=coach, name="Filtered group", plan_kind=TrainingPlan.PLAN_KIND_TRAINER
        )
        PlanMembership.objects.create(plan=trainer_plan, athlete=athlete_one)
        shared_race = RaceEvent.objects.create(
            owner=coach, name="Shared filtered race", date="2026-07-16"
        )
        shared_distance = RaceEventDistance.objects.create(race=shared_race, distance="1500")
        RaceEntry.objects.create(race_distance=shared_distance, athlete=athlete_one, coach_selected=True)
        athlete_two_entry = RaceEntry.objects.create(
            race_distance=shared_distance,
            athlete=athlete_two,
            coach_selected=True,
            target_selected=True,
        )
        other_race = RaceEvent.objects.create(
            owner=coach, name="Other athlete race", date="2026-07-17"
        )
        other_distance = RaceEventDistance.objects.create(race=other_race, distance="800")
        RaceEntry.objects.create(race_distance=other_distance, athlete=athlete_two, coach_selected=True)
        self.client.force_login(coach)

        response = self.client.get(
            f"/race-calendar/?year=2026&view=list&period=full&race_group=plan:{trainer_plan.id}&race_athlete=athlete:{athlete_one.id}&show_all=0"
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Shared filtered race")
        self.assertNotContains(response, "Other athlete race")
        self.assertContains(response, 'class="race-distance-count">1</span>', html=False)
        self.assertNotContains(response, 'class="race-distance-count">2</span>', html=False)
        self.assertContains(response, f'value="plan:{trainer_plan.id}" selected', html=False)
        self.assertContains(response, f'value="athlete:{athlete_one.id}" selected', html=False)
        top_athlete_selector = response.content.decode().split('id="raceAthlete"', 1)[1].split('</select>', 1)[0]
        self.assertIn(f'value="athlete:{athlete_one.id}" selected', top_athlete_selector)
        self.assertNotIn(f'value="athlete:{athlete_two.id}"', top_athlete_selector)
        self.assertContains(response, f'data-initial-filter="athlete:{athlete_one.id}"', html=False)
        self.assertContains(response, 'class="form-check-input race-expand-toggle"', html=False)
        self.assertContains(response, 'row.open = toggle.checked', html=False)

        group_response = self.client.get(
            f"/race-calendar/?year=2026&view=list&period=full&race_group=plan:{trainer_plan.id}&race_athlete=all&show_all=1"
        )
        self.assertContains(group_response, f'data-initial-filter="plan:{trainer_plan.id}"', html=False)

        scoped_calendar = self.client.get(
            f"/race-calendar/?year=2026&view=calendar&period=full&race_group=plan:{trainer_plan.id}&race_athlete=all&show_all=1"
        )
        self.assertContains(scoped_calendar, 'class="race-calendar-event race-calendar-pending"', html=False)
        self.assertContains(scoped_calendar, 'class="race-calendar-count">1</span>', html=False)
        self.assertNotContains(scoped_calendar, 'class="race-calendar-event race-calendar-target-pending"', html=False)

        all_calendar = self.client.get(
            "/race-calendar/?year=2026&view=calendar&period=full&race_group=all&race_athlete=all&show_all=1"
        )
        self.assertContains(all_calendar, 'class="race-calendar-event race-calendar-target-pending"', html=False)
        self.assertContains(all_calendar, 'class="race-calendar-count">2</span>', html=False)

        athlete_two_entry.athlete_selected = True
        athlete_two_entry.save(update_fields=["athlete_selected"])
        confirmed_calendar = self.client.get(
            "/race-calendar/?year=2026&view=calendar&period=full&race_group=all&race_athlete=all&show_all=1"
        )
        self.assertContains(confirmed_calendar, 'class="race-calendar-event race-calendar-target-confirmed"', html=False)

    def test_races_overview_redirects_directly_to_calendar(self):
        coach = get_user_model().objects.create_user(
            username="racesredirectcoach", password="secret", is_staff=True
        )
        self.client.force_login(coach)

        response = self.client.get("/races/")

        self.assertRedirects(response, "/race-calendar/", fetch_redirect_response=False)

    def test_target_checkbox_makes_race_important_without_athlete_checkbox(self):
        race = RaceEvent(name="Target Race", date="2026-07-16")
        distance = RaceEventDistance(race=race, distance="1500")
        athlete = Athlete(name="Runner", birth_year=2000, gender="X")
        entry = RaceEntry(
            race_distance=distance,
            athlete=athlete,
            coach_selected=False,
            athlete_selected=False,
            target_selected=True,
        )

        count = _race_selected_count(entry)

        self.assertEqual(count, 3)
        self.assertIn("Race!", _race_line_text(race, distance, count))


class StandardStrengthAccessTests(TestCase):
    def test_athlete_can_open_program_from_trainer_plan_selected_in_base_planning(self):
        User = get_user_model()
        coach = User.objects.create_user(username="basecoach", password="secret", is_staff=True)
        athlete_user = User.objects.create_user(username="baseathlete", password="secret")
        athlete = Athlete.objects.create(
            owner=coach,
            name="baseathlete",
            birth_year=2000,
            gender="X",
        )
        trainer_plan = TrainingPlan.objects.create(
            owner=coach,
            name="Base linked trainer plan",
            plan_kind=TrainingPlan.PLAN_KIND_TRAINER,
        )
        block = AthleteBasePlanningBlock.objects.create(
            athlete=athlete,
            planning_kind=AthleteBasePlanningBlock.KIND_BASE,
            label="Full year",
            start_month=1,
            start_day=1,
            end_month=12,
            end_day=31,
        )
        AthleteBasePlanningSlot.objects.create(
            block=block,
            weekday=0,
            slot_index=1,
            mode=AthleteBasePlanningSlot.MODE_TRAINER,
            trainer_plan=trainer_plan,
        )
        program = StandardStrengthProgram.objects.create(owner=coach, name="Base circuit")
        trainer_slot = TrainingSlot.objects.create(
            plan=trainer_plan,
            date=date(2026, 8, 10),
            slot_index=1,
        )
        TrainingSegment.objects.create(
            slot=trainer_slot,
            order=1,
            type="MOB",
            text=program.name,
            standard_strength_program=program,
        )

        self.client.force_login(athlete_user)
        response = self.client.get(f"/planning/standard-strength/{program.id}/")

        self.assertEqual(response.status_code, 200)

    def test_athlete_can_open_program_used_after_more_than_200_other_segments(self):
        User = get_user_model()
        coach = User.objects.create_user(username="strengthcoach", password="secret", is_staff=True)
        athlete_user = User.objects.create_user(username="strengthathlete", password="secret")
        athlete = Athlete.objects.create(
            owner=coach,
            name="strengthathlete",
            birth_year=2000,
            gender="X",
        )
        plan = TrainingPlan.objects.create(owner=coach, name="Strength access plan")
        program = StandardStrengthProgram.objects.create(owner=coach, name="Standard circuit")

        slots = [
            TrainingSlot(
                plan=plan,
                date=date(2026, 1, 1) + timedelta(days=index),
                slot_index=1,
            )
            for index in range(201)
        ]
        TrainingSlot.objects.bulk_create(slots)
        TrainingSegment.objects.bulk_create([
            TrainingSegment(
                slot=slot,
                order=1,
                type="MOB",
                text=program.name,
                standard_strength_program=program,
            )
            for slot in slots
        ])

        athlete_slot = TrainingSlot.objects.create(
            plan=plan,
            athlete=athlete,
            date=date(2026, 12, 31),
            slot_index=1,
        )
        TrainingSegment.objects.create(
            slot=athlete_slot,
            order=1,
            type="MOB",
            text=program.name,
            standard_strength_program=program,
        )

        self.client.force_login(athlete_user)
        response = self.client.get(f"/planning/standard-strength/{program.id}/")

        self.assertEqual(response.status_code, 200)

    def test_unrelated_athlete_cannot_open_program(self):
        User = get_user_model()
        coach = User.objects.create_user(username="othercoach", password="secret", is_staff=True)
        athlete_user = User.objects.create_user(username="unrelatedathlete", password="secret")
        Athlete.objects.create(
            owner=coach,
            name="unrelatedathlete",
            birth_year=2000,
            gender="X",
        )
        program = StandardStrengthProgram.objects.create(owner=coach, name="Private circuit")

        self.client.force_login(athlete_user)
        response = self.client.get(f"/planning/standard-strength/{program.id}/")

        self.assertEqual(response.status_code, 403)


class AthleteTimeInputFormatTests(TestCase):
    def test_400m_format_accepts_more_than_60_seconds(self):
        self.assertEqual(_parse_pr_time_to_seconds("72.35"), 72.35)

    def test_athlete_form_marks_each_time_field_with_its_fixed_format(self):
        user = get_user_model().objects.create_user(
            username="timeformatcoach",
            password="secret",
            is_staff=True,
        )
        athlete = Athlete.objects.create(
            owner=user,
            name="Time Format Athlete",
            birth_year=2000,
            gender="X",
        )
        self.client.force_login(user)

        response = self.client.get(f"/coach/athletes/{athlete.id}/edit/?tab=zones")

        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertIn('class="zone-time-grid"', html)
        self.assertIn('class="pr-time-grid"', html)
        self.assertEqual(html.count('class="col-md-2 pr-time-card"'), 8)
        self.assertEqual(html.count('data-time-label="PR"'), 8)
        self.assertEqual(html.count('data-time-label="Doel"'), 8)
        for name in ("t4", "target_t4"):
            self.assertIn(f'name="{name}"', html)
            self.assertRegex(html, rf'name="{name}"[^>]+data-time-format="seconds-hundredths"')
        for name in ("pr_800", "target_pr_800", "pr_1500", "target_pr_1500"):
            self.assertRegex(html, rf'name="{name}"[^>]+data-time-format="minutes-seconds-hundredths"')
        for name in (
            "pr_3000", "target_pr_3000", "pr_5000", "target_pr_5000",
            "pr_10000", "target_pr_10000",
        ):
            self.assertRegex(html, rf'name="{name}"[^>]+data-time-format="minutes-seconds"')
        for name in ("thm", "target_thm", "tm", "target_tm"):
            self.assertRegex(html, rf'name="{name}"[^>]+data-time-format="hours-minutes-seconds"')
        for zone in range(1, 6):
            self.assertRegex(html, rf'name="z{zone}_pace"[^>]+data-time-format="minutes-seconds"')


class TrainingSegmentLabelTests(TestCase):
    def test_main_labels_replace_core_labels(self):
        self.assertEqual(TrainingSegment(type="CORE").get_type_display(), "Main")
        self.assertEqual(TrainingSegment(type="CORE2").get_type_display(), "Main 2")


class FlexPlannerAltTotalsTests(TestCase):
    def test_flex_totals_keep_alt_z1_to_z3_separate_from_running_distance(self):
        source = get_template("core/flex_planner.html").template.source

        self.assertIn('if (segType === "ALT")', source)
        self.assertIn('["1", "2", "3"].includes(fallbackZone)', source)
        self.assertIn('? [{kind: "alt", zone: fallbackZone, seconds: altSeconds}]', source)
        self.assertIn('if (load.kind === "alt")', source)
        self.assertIn('"ALT Z" + z', source)
        self.assertIn('const altParts = text.split("//")', source)

    def test_flex_save_splits_alt_blocks_and_keeps_each_zone_out_of_kilometres(self):
        from core.stats import athlete_week_stats

        trainer = get_user_model().objects.create_user(username="altblockscoach", password="secret", is_staff=True)
        athlete = Athlete.objects.create(owner=trainer, name="Alt Blocks Athlete", birth_year=2000, gender="X")
        week_start = date.today() - timedelta(days=date.today().weekday())
        plan = TrainingPlan.objects.create(
            owner=trainer,
            name="Flex Planner Alt blocks",
            start_date=week_start,
            end_date=week_start + timedelta(days=6),
        )
        self.client.force_login(trainer)

        response = self.client.post(
            f"/slot-modal/{week_start.year}/{week_start.month}/{week_start.day}/1/",
            {
                "plan": str(plan.id),
                "athlete": str(athlete.id),
                "source": "flex",
                "alt_text": "20' z1//10'z2//10'z3",
            },
        )

        self.assertEqual(response.status_code, 200)
        slot = TrainingSlot.objects.get(plan=plan, athlete=athlete, date=week_start, slot_index=1)
        segments = list(slot.segments.filter(type="ALT").order_by("order", "id"))
        self.assertEqual(
            [(seg.text, seg.zone, seg.duration_s) for seg in segments],
            [("20' z1", "1", 1200), ("10'z2", "2", 600), ("10'z3", "3", 600)],
        )

        stats = athlete_week_stats(plan, athlete, week_start)
        self.assertEqual(stats["alt_zones"]["1"]["duration_s"], 1200)
        self.assertEqual(stats["alt_zones"]["2"]["duration_s"], 600)
        self.assertEqual(stats["alt_zones"]["3"]["duration_s"], 600)
        self.assertTrue(all(zone["distance_m"] == 0 for zone in stats["zones"].values()))

    def test_base_planning_alt_blocks_are_split_too(self):
        slot = _virtual_slot_from_base_training("ALT=20' z1//10'z2//10'z3")

        self.assertEqual(
            _ayc_slot_loads_for_totals(slot),
            [
                {"kind": "alt", "zone": "1", "seconds": 1200.0},
                {"kind": "alt", "zone": "2", "seconds": 600.0},
                {"kind": "alt", "zone": "3", "seconds": 600.0},
            ],
        )

    def test_existing_combined_alt_segment_is_read_as_three_blocks(self):
        from core.stats import athlete_week_stats

        trainer = get_user_model().objects.create_user(username="legacyaltcoach", password="secret", is_staff=True)
        athlete = Athlete.objects.create(owner=trainer, name="Legacy Alt Athlete", birth_year=2000, gender="X")
        week_start = date.today() - timedelta(days=date.today().weekday())
        plan = TrainingPlan.objects.create(owner=trainer, name="Legacy alt plan")
        PlanMembership.objects.create(plan=plan, athlete=athlete)
        slot = TrainingSlot.objects.create(plan=plan, athlete=athlete, date=week_start, slot_index=1)
        TrainingSegment.objects.create(
            slot=slot,
            type="ALT",
            text="20' z1//10'z2//10'z3",
            zone="1",
            duration_s=1200,
        )

        self.assertEqual(
            _ayc_slot_loads_for_totals(slot, athlete),
            [
                {"kind": "alt", "zone": "1", "seconds": 1200},
                {"kind": "alt", "zone": "2", "seconds": 600},
                {"kind": "alt", "zone": "3", "seconds": 600},
            ],
        )
        stats = athlete_week_stats(plan, athlete, week_start)
        self.assertEqual(
            {zone: values["duration_s"] for zone, values in stats["alt_zones"].items()},
            {"1": 1200, "2": 600, "3": 600},
        )


class TrainerStatsTests(TestCase):
    def test_athlete_name_links_to_six_month_weekly_distance_chart(self):
        trainer = get_user_model().objects.create_user(username="chartcoach", password="secret", is_staff=True)
        athlete = Athlete.objects.create(owner=trainer, name="Chart Athlete", birth_year=2000, gender="X")
        current_week = date.today() - timedelta(days=date.today().weekday())
        first_week = current_week - timedelta(weeks=25)
        plan = TrainingPlan.objects.create(
            owner=trainer,
            name="Chart plan",
            start_date=first_week,
            end_date=current_week + timedelta(days=6),
        )
        PlanMembership.objects.create(plan=plan, athlete=athlete)
        for day, meters in ((first_week, 5000), (current_week, 12000)):
            slot = TrainingSlot.objects.create(plan=plan, date=day, slot_index=1)
            TrainingSegment.objects.create(
                slot=slot, type="CORE", text=f"{meters}m z2", zone="2",
                distance_m=meters, norm_distance_m=meters,
            )
        self.client.force_login(trainer)

        overview = self.client.get("/planning/stats/?ok=1")
        detail = self.client.get(f"/planning/stats/athlete/{athlete.id}/")

        self.assertContains(overview, f'/planning/stats/athlete/{athlete.id}/')
        self.assertEqual(detail.status_code, 200)
        self.assertContains(detail, "Total km per week")
        self.assertContains(detail, "The current week may still be incomplete.")
        self.assertEqual(len(detail.context["weeks"]), 26)
        self.assertEqual(detail.context["weeks"][0]["km_label"], "5.0")
        self.assertEqual(detail.context["weeks"][-1]["km_label"], "12.0")

    def test_athlete_chart_period_selector_updates_weeks_and_summary(self):
        trainer = get_user_model().objects.create_user(username="periodcoach", password="secret", is_staff=True)
        athlete = Athlete.objects.create(owner=trainer, name="Period Athlete", birth_year=2000, gender="X")
        current_week = date.today() - timedelta(days=date.today().weekday())
        plan = TrainingPlan.objects.create(
            owner=trainer,
            name="Period plan",
            start_date=current_week - timedelta(weeks=4),
            end_date=current_week + timedelta(days=6),
        )
        PlanMembership.objects.create(plan=plan, athlete=athlete)
        for offset, meters in ((-4, 5000), (0, 15000)):
            slot = TrainingSlot.objects.create(
                plan=plan,
                date=current_week + timedelta(weeks=offset),
                slot_index=1,
            )
            TrainingSegment.objects.create(
                slot=slot, type="CORE", text=f"{meters}m z2", zone="2",
                distance_m=meters, norm_distance_m=meters,
            )
        self.client.force_login(trainer)

        response = self.client.get(f"/planning/stats/athlete/{athlete.id}/?months=1")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["selected_months"], 1)
        self.assertEqual(len(response.context["weeks"]), 4)
        self.assertEqual(response.context["average_km"], "3.8")
        self.assertEqual(response.context["minimum_km"], "0.0")
        self.assertEqual(response.context["maximum_km"], "15.0")
        self.assertContains(response, "Weekly average")
        self.assertContains(response, "Highest week")
        self.assertContains(response, "Lowest week")

        custom_period = self.client.get(f"/planning/stats/athlete/{athlete.id}/?months=17")
        self.assertEqual(custom_period.context["selected_months"], 17)
        self.assertEqual(len(custom_period.context["weeks"]), 74)
        self.assertContains(custom_period, 'value="17"', html=False)

        previous_period = self.client.get(f"/planning/stats/athlete/{athlete.id}/?months=1&period=1")
        self.assertEqual(previous_period.context["period_index"], 1)
        self.assertEqual(
            previous_period.context["period_end"] + timedelta(days=1),
            response.context["period_start"],
        )
        self.assertContains(previous_period, "Previous period")
        self.assertContains(previous_period, "Next period")
        self.assertIn("period=0", previous_period.context["next_period_url"])
        self.assertEqual(response.context["next_period_url"], "")

    def test_athlete_chart_is_trainer_only_and_respects_ownership(self):
        owner = get_user_model().objects.create_user(username="chartowner", password="secret", is_staff=True)
        other_trainer = get_user_model().objects.create_user(username="chartother", password="secret", is_staff=True)
        athlete_user = get_user_model().objects.create_user(username="chartathlete", password="secret")
        athlete = Athlete.objects.create(owner=owner, name="Private Chart Athlete", birth_year=2000, gender="X")

        self.client.force_login(other_trainer)
        self.assertEqual(self.client.get(f"/planning/stats/athlete/{athlete.id}/").status_code, 404)

        self.client.force_login(athlete_user)
        self.assertEqual(self.client.get(f"/planning/stats/athlete/{athlete.id}/").status_code, 403)

    def test_stats_uses_same_athlete_selector_modes_as_dco(self):
        trainer = get_user_model().objects.create_user(username="selectorcoach", password="secret", is_staff=True)
        selected = Athlete.objects.create(owner=trainer, name="Selected Athlete", birth_year=2000, gender="X")
        Athlete.objects.create(owner=trainer, name="Hidden Athlete", birth_year=2001, gender="X")
        self.client.force_login(trainer)

        response = self.client.get(
            f"/planning/stats/?selection=selection&athletes={selected.id}&ok=1"
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Selection")
        self.assertContains(response, "Selected Athlete")
        self.assertNotContains(response, "Hidden Athlete")

    def test_stats_loads_dco_saved_selection(self):
        trainer = get_user_model().objects.create_user(username="sharedselectioncoach", password="secret", is_staff=True)
        selected = Athlete.objects.create(owner=trainer, name="Shared Selected", birth_year=2000, gender="X")
        Athlete.objects.create(owner=trainer, name="Shared Hidden", birth_year=2001, gender="X")
        CoachSettings.objects.create(
            user=trainer,
            dco_saved_selections=[{"id": "squad-a", "name": "Squad A", "athlete_ids": [selected.id]}],
            dco_standard_selection_id="squad-a",
        )
        self.client.force_login(trainer)

        selector = self.client.get("/planning/stats/")
        response = self.client.get("/planning/stats/?selection=selection&saved_selection=squad-a&ok=1")

        self.assertContains(selector, "Squad A *")
        self.assertContains(response, "Shared Selected")
        self.assertNotContains(response, "Shared Hidden")

    def test_stats_landing_page_shows_selector_before_results(self):
        trainer = get_user_model().objects.create_user(username="statslanding", password="secret", is_staff=True)
        Athlete.objects.create(owner=trainer, name="Landing Athlete", birth_year=2000, gender="X")
        self.client.force_login(trainer)

        response = self.client.get("/planning/stats/")

        self.assertContains(response, 'id="statsSelectionMode"', html=False)
        self.assertContains(response, ">Trains<", html=False)
        self.assertContains(response, ">Planned training<", html=False)
        self.assertNotContains(response, "Previous week")

    def test_tile_and_page_are_trainer_only(self):
        User = get_user_model()
        trainer = User.objects.create_user(username="statstrainer", password="secret", is_staff=True)
        athlete_user = User.objects.create_user(username="statsathlete", password="secret")
        Athlete.objects.create(
            owner=trainer,
            name="statsathlete",
            birth_year=2000,
            gender="X",
        )

        self.client.force_login(trainer)
        trainer_overview = self.client.get("/")
        self.assertContains(trainer_overview, "Stats (under development)")
        self.assertEqual(self.client.get("/planning/stats/").status_code, 200)

        self.client.force_login(athlete_user)
        athlete_overview = self.client.get("/")
        self.assertNotContains(athlete_overview, "Stats (under development)")
        self.assertEqual(self.client.get("/planning/stats/").status_code, 403)

    def test_page_shows_previous_and_current_week_distance(self):
        trainer = get_user_model().objects.create_user(
            username="distancecoach",
            password="secret",
            is_staff=True,
        )
        athlete = Athlete.objects.create(
            owner=trainer,
            name="Distance Athlete",
            birth_year=2000,
            gender="X",
        )
        this_week_start = date.today() - timedelta(days=date.today().weekday())
        previous_week_start = this_week_start - timedelta(days=7)
        plan = TrainingPlan.objects.create(
            owner=trainer,
            name="Stats distance plan",
            start_date=previous_week_start,
            end_date=this_week_start + timedelta(days=6),
        )
        PlanMembership.objects.create(plan=plan, athlete=athlete)
        previous_slot = TrainingSlot.objects.create(plan=plan, date=previous_week_start, slot_index=1)
        TrainingSegment.objects.create(
            slot=previous_slot,
            type="CORE",
            text="5km z2",
            zone="2",
            distance_m=5000,
            norm_distance_m=5000,
        )
        current_slot = TrainingSlot.objects.create(plan=plan, date=this_week_start, slot_index=1)
        TrainingSegment.objects.create(
            slot=current_slot,
            type="CORE",
            text="10km z2",
            zone="2",
            distance_m=10000,
            norm_distance_m=10000,
        )

        self.client.force_login(trainer)
        response = self.client.get("/planning/stats/?ok=1")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Distance Athlete")
        self.assertContains(response, "5.0 km")
        self.assertContains(response, "10.0 km")

    def test_page_includes_trainer_plan_selected_via_base_planning(self):
        trainer = get_user_model().objects.create_user(
            username="basestatscoach",
            password="secret",
            is_staff=True,
        )
        athlete = Athlete.objects.create(
            owner=trainer,
            name="Base Stats Athlete",
            birth_year=2000,
            gender="X",
        )
        trainer_plan = TrainingPlan.objects.create(
            owner=trainer,
            name="Stats trainer plan",
            plan_kind=TrainingPlan.PLAN_KIND_TRAINER,
        )
        block = AthleteBasePlanningBlock.objects.create(
            athlete=athlete,
            planning_kind=AthleteBasePlanningBlock.KIND_BASE,
            label="Full year stats",
            start_month=1,
            start_day=1,
            end_month=12,
            end_day=31,
        )
        this_week_start = date.today() - timedelta(days=date.today().weekday())
        AthleteBasePlanningSlot.objects.create(
            block=block,
            weekday=this_week_start.weekday(),
            slot_index=1,
            mode=AthleteBasePlanningSlot.MODE_TRAINER,
            trainer_plan=trainer_plan,
        )
        slot = TrainingSlot.objects.create(
            plan=trainer_plan,
            date=this_week_start,
            slot_index=1,
        )
        TrainingSegment.objects.create(
            slot=slot,
            type="CORE",
            text="7km z2",
            zone="2",
            distance_m=7000,
            norm_distance_m=7000,
        )

        self.client.force_login(trainer)
        response = self.client.get("/planning/stats/?ok=1")

        self.assertContains(response, "Base Stats Athlete")
        self.assertContains(response, "7.0 km")

    def test_stats_columns_sort_name_ascending_and_distances_descending(self):
        trainer = get_user_model().objects.create_user(username="statssort", password="secret", is_staff=True)
        alpha = Athlete.objects.create(owner=trainer, name="Alpha", birth_year=2000, gender="X")
        bravo = Athlete.objects.create(owner=trainer, name="Bravo", birth_year=2000, gender="X")
        this_week = date.today() - timedelta(days=date.today().weekday())
        previous_week = this_week - timedelta(days=7)

        for athlete, previous_m, current_m in ((alpha, 8000, 2000), (bravo, 1000, 10000)):
            plan = TrainingPlan.objects.create(
                owner=trainer,
                name=f"{athlete.name} sort plan",
                start_date=previous_week,
                end_date=this_week + timedelta(days=6),
            )
            PlanMembership.objects.create(plan=plan, athlete=athlete)
            for day, meters in ((previous_week, previous_m), (this_week, current_m)):
                slot = TrainingSlot.objects.create(plan=plan, date=day, slot_index=1)
                TrainingSegment.objects.create(
                    slot=slot, type="CORE", text=f"{meters}m z2", zone="2",
                    distance_m=meters, norm_distance_m=meters,
                )
        self.client.force_login(trainer)

        by_name = self.client.get("/planning/stats/?ok=1")
        by_previous = self.client.get("/planning/stats/?ok=1&sort=previous")
        by_this = self.client.get("/planning/stats/?ok=1&sort=this")

        self.assertEqual([row["athlete"].name for row in by_name.context["rows"]], ["Alpha", "Bravo"])
        self.assertEqual([row["athlete"].name for row in by_previous.context["rows"]], ["Alpha", "Bravo"])
        self.assertEqual([row["athlete"].name for row in by_this.context["rows"]], ["Bravo", "Alpha"])


class HomeScreenIconTests(TestCase):
    def test_login_page_publishes_mila_app_icon(self):
        response = self.client.get("/login/")

        self.assertContains(response, 'rel="apple-touch-icon"', html=False)
        self.assertContains(response, '/static/core/brand/app/mila-app-180x180.png', html=False)

    def test_authenticated_pages_publish_mila_app_icons_and_manifest(self):
        user = get_user_model().objects.create_user(username="appiconcoach", password="secret", is_staff=True)
        self.client.force_login(user)

        response = self.client.get("/")

        self.assertContains(response, 'rel="apple-touch-icon"', html=False)
        self.assertContains(response, '/static/core/brand/app/mila-app-180x180.png', html=False)
        self.assertContains(response, 'rel="manifest"', html=False)
        self.assertContains(response, '/static/core/brand/app/site.webmanifest', html=False)

    def test_manifest_contains_android_home_screen_icons(self):
        manifest_path = Path(__file__).parent / "static" / "core" / "brand" / "app" / "site.webmanifest"
        manifest = manifest_path.read_text(encoding="utf-8")

        self.assertIn('"short_name": "MiLa"', manifest)
        self.assertIn("mila-app-192x192.png", manifest)
        self.assertIn("mila-app-512x512.png", manifest)
