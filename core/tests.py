from django.contrib.auth import get_user_model
from datetime import date, timedelta
from pathlib import Path

from django.test import TestCase
from django.template.loader import get_template

from core.models import Athlete, AthleteBasePlanningBlock, AthleteBasePlanningSlot, Group, PlanMembership, RaceEntry, RaceEvent, RaceEventDistance, StandardStrengthProgram, TrainingPlan, TrainingSegment, TrainingSlot
from core.views.calendar import _segment_rep_time_label
from core.views.coach import _parse_pr_time_to_seconds, _race_line_text, _race_selected_count


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

    def test_auto_wucd_is_not_applied_for_z1_z2_only_core(self):
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


class TrainerStatsTests(TestCase):
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
        response = self.client.get("/planning/stats/")

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
        response = self.client.get("/planning/stats/")

        self.assertContains(response, "Base Stats Athlete")
        self.assertContains(response, "7.0 km")
