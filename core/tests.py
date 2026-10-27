from django.contrib.auth import get_user_model
from datetime import date, datetime, time, timedelta
import json
import os
import zipfile
from io import BytesIO
from pathlib import Path
from unittest.mock import patch
from xml.sax.saxutils import escape

from django.test import TestCase
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.cache import cache
from django.template.loader import get_template, render_to_string
from django.utils import timezone

from core.models import Athlete, AthleteBasePlanningBlock, AthleteBasePlanningSlot, AthleteDailyVital, AthleteDayCheck, AthleteWeekReport, AthleteFocusPoint, CoachAccess, CoachEvaluationSharing, CoachSettings, EvaluationQuestion, EvaluationQuestionnaire, EvaluationResponse, FocusPointComment, Group, MatchAthleteRecord, MatchOverview, NewFeature, PlanLike, PlanMembership, PlannedChange, PolarConnection, RaceEntry, RaceEvent, RaceEventDistance, StandardStrengthProgram, Team, TrainingPlan, TrainingSegment, TrainingSlot, UserWish, WishLike, YearPlannerEntry, YearPlannerWhereabout
from core.focus_point_import import FOCUS_POINT_HEADERS
from core.views.calendar import _annotate_slot_segment_display_times, _ayc_pause_distance_m, _ayc_slot_loads_for_totals, _ayc_slot_session_km, _clone_slot_for_display, _segment_hr_label, _segment_rep_time_label, _virtual_slot_from_base_training, _watch_actual_time_label, _watch_segment_loads, _whereabout_dots
from core.views.coach import (
    _build_alternative_watch_suggestion,
    _build_polar_v4_lap_suggestion,
    _polar_v4_normalize_exercise_samples,
    _polar_v4_sample_activities,
    _planned_interval_structure,
    _parse_match_athlete_records,
    _parse_match_participants,
    _parse_match_schedule,
    _parse_pr_time_to_seconds,
    _race_line_text,
    _race_selected_count,
    _watch_activities_for_plan,
    _watch_plan_is_clear_mismatch,
    _watch_v4_sessions_for_plan,
)
from core.views.polar_raw import type_a_description, type_a_training_fields


def _focus_comments_xlsx(rows):
    """Build a small standards-compliant enough inline-string XLSX test fixture."""
    headers = ["", *FOCUS_POINT_HEADERS.keys()]

    def column_name(number):
        result = ""
        while number:
            number, remainder = divmod(number - 1, 26)
            result = chr(65 + remainder) + result
        return result

    all_rows = [headers, *rows]
    xml_rows = []
    for row_index, values in enumerate(all_rows, start=1):
        cells = []
        for column_index, value in enumerate(values, start=1):
            if value is None or value == "":
                continue
            reference = f"{column_name(column_index)}{row_index}"
            cells.append(
                f'<c r="{reference}" t="inlineStr"><is><t>{escape(str(value))}</t></is></c>'
            )
        xml_rows.append(f'<row r="{row_index}">{"".join(cells)}</row>')
    worksheet = (
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        f'<sheetData>{"".join(xml_rows)}</sheetData></worksheet>'
    )
    workbook = (
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        '<sheets><sheet name="Comments" sheetId="1" r:id="rId1"/></sheets></workbook>'
    )
    relationships = (
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
        'Target="worksheets/sheet1.xml"/></Relationships>'
    )
    output = BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("xl/workbook.xml", workbook)
        archive.writestr("xl/_rels/workbook.xml.rels", relationships)
        archive.writestr("xl/worksheets/sheet1.xml", worksheet)
    return output.getvalue()


class SecurityHeadersTests(TestCase):
    def test_security_headers_are_present(self):
        response = self.client.get("/login/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Referrer-Policy"], "same-origin")
        self.assertEqual(response["X-Content-Type-Options"], "nosniff")
        self.assertEqual(
            response["Cross-Origin-Opener-Policy"],
            "same-origin-allow-popups",
        )


class NewPlansWishesTests(TestCase):
    def setUp(self):
        self.admin = get_user_model().objects.create_user(
            username="admin",
            password="secret",
            is_staff=True,
            is_superuser=True,
        )
        self.user = get_user_model().objects.create_user(
            username="wish-user",
            password="secret",
            first_name="Wish",
            last_name="Owner",
        )
        self.other_user = get_user_model().objects.create_user(
            username="wish-liker",
            password="secret",
            first_name="Like",
            last_name="Person",
        )

    def test_dashboard_and_wishes_page_are_available_to_every_user(self):
        self.client.force_login(self.user)

        dashboard = self.client.get("/")
        self.assertContains(dashboard, "New, Plans, Wishes")
        self.assertNotContains(dashboard, "Go to admin")

        response = self.client.get("/new-plans-wishes/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Here you can see what new features")
        self.assertNotContains(response, "Add new feature")

    def test_only_admin_account_sees_admin_dashboard_card(self):
        self.client.force_login(self.admin)
        admin_dashboard = self.client.get("/")
        self.assertContains(admin_dashboard, 'href="/admin/"')
        self.assertContains(admin_dashboard, 'class="card h-100 dashboard-tile"')

    def test_user_can_only_have_three_active_wishes(self):
        self.client.force_login(self.user)
        for number in range(3):
            response = self.client.post(
                "/new-plans-wishes/",
                {"action": "add_wish", "title": f"Wish {number}"},
            )
            self.assertEqual(response.status_code, 302)

        response = self.client.post(
            "/new-plans-wishes/",
            {"action": "add_wish", "title": "Fourth wish"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "up to 3 active wishes")
        self.assertEqual(UserWish.objects.filter(author=self.user, status=UserWish.STATUS_ACTIVE).count(), 3)

    def test_wish_author_and_admin_can_edit_but_other_users_cannot(self):
        wish = UserWish.objects.create(author=self.user, title="Original", description="Old details")

        self.client.force_login(self.user)
        owner_page = self.client.get(f"/new-plans-wishes/?section=wishes&edit_wish={wish.id}")
        self.assertContains(owner_page, 'name="action" value="update_wish"')
        owner_save = self.client.post("/new-plans-wishes/", {
            "action": "update_wish",
            "wish_id": wish.id,
            "title": "Owner edit",
            "description": "Updated by owner",
        })
        self.assertEqual(owner_save.status_code, 302)
        wish.refresh_from_db()
        self.assertEqual((wish.title, wish.description), ("Owner edit", "Updated by owner"))

        self.client.force_login(self.other_user)
        other_page = self.client.get(f"/new-plans-wishes/?section=wishes&edit_wish={wish.id}")
        self.assertNotContains(other_page, 'name="action" value="update_wish"')
        other_save = self.client.post("/new-plans-wishes/", {
            "action": "update_wish",
            "wish_id": wish.id,
            "title": "Unauthorized edit",
            "description": "Should not save",
        })
        self.assertEqual(other_save.status_code, 403)
        wish.refresh_from_db()
        self.assertEqual(wish.title, "Owner edit")

        self.client.force_login(self.admin)
        admin_page = self.client.get(f"/new-plans-wishes/?section=wishes&edit_wish={wish.id}")
        self.assertContains(admin_page, 'name="action" value="update_wish"')
        admin_save = self.client.post("/new-plans-wishes/", {
            "action": "update_wish",
            "wish_id": wish.id,
            "title": "Admin edit",
            "description": "Updated by admin",
        })
        self.assertEqual(admin_save.status_code, 302)
        wish.refresh_from_db()
        self.assertEqual((wish.title, wish.description), ("Admin edit", "Updated by admin"))

    def test_wishes_are_anonymous_except_for_admin_and_can_be_liked(self):
        wish = UserWish.objects.create(author=self.user, title="Dark mode")
        self.client.force_login(self.other_user)

        response = self.client.get("/new-plans-wishes/")
        self.assertContains(response, "Dark mode")
        self.assertNotContains(response, "Wish Owner")

        like_response = self.client.post(
            "/new-plans-wishes/",
            {"action": "toggle_like", "wish_id": wish.id},
        )
        self.assertEqual(like_response.status_code, 302)
        self.assertTrue(WishLike.objects.filter(wish=wish, user=self.other_user).exists())

        self.client.force_login(self.admin)
        admin_response = self.client.get("/new-plans-wishes/")
        self.assertContains(admin_response, "Wish Owner")
        self.assertContains(admin_response, "Like Person")

        self.client.force_login(self.user)
        own_wish_response = self.client.post(
            "/new-plans-wishes/",
            {"action": "toggle_like", "wish_id": wish.id},
        )
        self.assertEqual(own_wish_response.status_code, 302)
        self.assertFalse(WishLike.objects.filter(wish=wish, user=self.user).exists())

    def test_admin_can_turn_a_wish_into_a_prioritised_plan(self):
        wish = UserWish.objects.create(author=self.user, title="Weekly progress chart", description="Show a simple trend.")
        self.client.force_login(self.admin)

        response = self.client.post(
            "/new-plans-wishes/",
            {"action": "add_plan", "source_wish": wish.id, "urgency": "gold"},
        )

        self.assertEqual(response.status_code, 302)
        wish.refresh_from_db()
        self.assertEqual(wish.status, UserWish.STATUS_PLANNED)
        plan = PlannedChange.objects.get(source_wish=wish)
        self.assertEqual(plan.title, "Weekly progress chart")
        self.assertEqual(plan.urgency, PlannedChange.URGENCY_GOLD)

        self.client.force_login(self.user)
        like_response = self.client.post(
            "/new-plans-wishes/",
            {"action": "toggle_plan_like", "plan_id": plan.id},
        )
        self.assertEqual(like_response.status_code, 302)
        self.assertTrue(PlanLike.objects.filter(plan=plan, user=self.user).exists())

        self.client.force_login(self.admin)
        delete_response = self.client.post(
            "/new-plans-wishes/",
            {"action": "delete_plan", "plan_id": plan.id},
        )
        self.assertEqual(delete_response.status_code, 302)
        wish.refresh_from_db()
        self.assertEqual(wish.status, UserWish.STATUS_PLANNED)
        self.assertFalse(PlannedChange.objects.filter(id=plan.id).exists())

    def test_plans_are_sorted_by_medal_then_oldest_first(self):
        older_gold = PlannedChange.objects.create(title="Older gold", urgency=PlannedChange.URGENCY_GOLD)
        newer_gold = PlannedChange.objects.create(title="Newer gold", urgency=PlannedChange.URGENCY_GOLD)
        silver = PlannedChange.objects.create(title="Silver", urgency=PlannedChange.URGENCY_SILVER)
        no_medal = PlannedChange.objects.create(title="No medal")
        PlannedChange.objects.filter(id=older_gold.id).update(created_at=timezone.now() - timedelta(days=4))
        PlannedChange.objects.filter(id=newer_gold.id).update(created_at=timezone.now() - timedelta(days=2))
        self.client.force_login(self.user)

        response = self.client.get("/new-plans-wishes/")
        ordered_titles = [plan.title for plan in response.context["planned_changes"]]
        self.assertEqual(ordered_titles, ["Older gold", "Newer gold", "Silver", "No medal"])

    def test_admin_can_edit_a_plan(self):
        plan = PlannedChange.objects.create(title="Old title", description="Old details", urgency=PlannedChange.URGENCY_BRONZE)
        self.client.force_login(self.admin)

        edit_page = self.client.get(f"/new-plans-wishes/?section=plans&edit={plan.id}")
        self.assertContains(edit_page, "Old title")
        self.assertContains(edit_page, "Save")

        response = self.client.post("/new-plans-wishes/", {
            "action": "update_plan",
            "plan_id": plan.id,
            "title": "Updated title",
            "description": "Updated details",
            "urgency": PlannedChange.URGENCY_GOLD,
        })
        self.assertEqual(response.status_code, 302)
        plan.refresh_from_db()
        self.assertEqual(plan.title, "Updated title")
        self.assertEqual(plan.urgency, PlannedChange.URGENCY_GOLD)


class TrackTimerTests(TestCase):
    def test_timer_page_is_available_from_dashboard(self):
        user = get_user_model().objects.create_user(username="timer-user", password="secret")
        self.client.force_login(user)

        dashboard = self.client.get("/")
        self.assertEqual(dashboard.status_code, 200)
        self.assertContains(dashboard, "Coach tools")
        self.assertContains(dashboard, "Go to Coach tools")

        tools = self.client.get("/coach-tools/")
        self.assertEqual(tools.status_code, 200)
        self.assertContains(tools, "Timer")
        self.assertNotContains(tools, "Match overview")
        self.assertNotContains(tools, "PR-database")

        timer = self.client.get("/timer/")
        self.assertEqual(timer.status_code, 200)
        self.assertContains(timer, "Track Timer")
        self.assertContains(timer, "1600m")
        self.assertContains(timer, 'id="timerTarget"')
        self.assertContains(timer, 'id="targetPaceLine"')
        self.assertContains(timer, "Target")
        self.assertContains(timer, "min/km")
        self.assertContains(timer, "Athlete 3")
        self.assertNotContains(timer, "Athlete 4")
        self.assertContains(timer, "track-measure-line")

    def test_coach_tools_only_user_is_limited_to_coach_tools(self):
        user = get_user_model().objects.create_user(username="coachtools", password="secret")
        self.client.force_login(user)

        dashboard = self.client.get("/")
        self.assertEqual(dashboard.status_code, 200)
        self.assertContains(dashboard, "Coach tools dashboard")
        self.assertContains(dashboard, "Go to Coach tools")
        self.assertNotContains(dashboard, "Go to planning")
        self.assertNotContains(dashboard, "Open Polar")
        self.assertNotContains(dashboard, "Go to admin")

        planning = self.client.get("/planning/")
        self.assertEqual(planning.status_code, 302)
        self.assertEqual(planning["Location"], "/coach-tools/")

        tools = self.client.get("/coach-tools/")
        self.assertEqual(tools.status_code, 200)
        self.assertContains(tools, "Timer")
        self.assertNotContains(tools, "Match overview")
        self.assertNotContains(tools, "PR-database")

        create_response = self.client.post("/coach-tools/match-overview/new/")
        self.assertEqual(create_response.status_code, 302)
        self.assertTrue(MatchOverview.objects.filter(owner=user).exists())

    def test_coach_tools_only_user_uses_iain_match_data(self):
        owner = get_user_model().objects.create_user(username="Iain_somers", password="secret", is_staff=True)
        user = get_user_model().objects.create_user(username="coachtools", password="secret")
        match = MatchOverview.objects.create(owner=owner, name="Shared match")
        self.client.force_login(user)

        list_response = self.client.get("/coach-tools/match-overview/")
        self.assertContains(list_response, "Shared match")

        create_response = self.client.post("/coach-tools/match-overview/new/")
        self.assertEqual(create_response.status_code, 302)
        self.assertEqual(MatchOverview.objects.filter(owner=owner).count(), 2)
        self.assertFalse(MatchOverview.objects.filter(owner=user).exists())

        detail = self.client.get(f"/coach-tools/match-overview/{match.id}/")
        self.assertEqual(detail.status_code, 200)

    def test_evaluations_coach_creates_and_athlete_fills_questionnaire(self):
        coach = get_user_model().objects.create_user(username="eval-coach", password="secret", is_staff=True)
        athlete_user = get_user_model().objects.create_user(username="eval_athlete", password="secret")
        athlete = Athlete.objects.create(owner=coach, name="eval athlete", birth_year=2000, gender="X")
        self.client.force_login(coach)

        dashboard = self.client.get("/")
        self.assertContains(dashboard, "Evaluations")

        create_response = self.client.post(
            "/evaluations/",
            {
                "title": "Wellbeing",
                "description": "Short check",
                "questions": "How do you feel?\nAny pain?",
                "matrix_title": "Development",
                "matrix_columns": "2025\n2026",
                "matrix_rows": "Strength\nEndurance",
                "is_active": "on",
            },
        )

        self.assertEqual(create_response.status_code, 302)
        questionnaire = EvaluationQuestionnaire.objects.get(title="Wellbeing")
        self.assertEqual(questionnaire.questions.count(), 3)
        matrix_question = questionnaire.questions.get(question_type=EvaluationQuestion.TYPE_MATRIX)
        self.assertEqual(matrix_question.matrix_columns, ["2025", "2026"])
        self.assertEqual(matrix_question.matrix_rows, ["Strength", "Endurance"])

        self.client.force_login(athlete_user)
        athlete_list = self.client.get("/evaluations/")
        self.assertContains(athlete_list, "Wellbeing")

        fill_page = self.client.get(f"/evaluations/{questionnaire.id}/")
        self.assertContains(fill_page, "evaluation-matrix-answer")
        self.assertContains(fill_page, "resizeMatrixAnswer")

        fill_response = self.client.post(
            f"/evaluations/{questionnaire.id}/",
            {
                f"question_{questionnaire.questions.first().id}": "Good",
                f"question_{questionnaire.questions.filter(question_type='text').last().id}": "No pain",
                f"question_{matrix_question.id}_0_0": "Solid",
                f"question_{matrix_question.id}_0_1": "Improved",
                f"question_{matrix_question.id}_1_1": "Strong",
            },
        )

        self.assertEqual(fill_response.status_code, 302)
        response = EvaluationResponse.objects.get(questionnaire=questionnaire, athlete=athlete)
        self.assertIn("Good", response.answers.values())
        self.assertEqual(response.answers[str(matrix_question.id)]["0:1"], "Improved")

        self.client.force_login(coach)
        coach_list = self.client.get("/evaluations/")
        self.assertContains(coach_list, "1 filled")
        self.assertContains(coach_list, f"questionnaireCollapse{questionnaire.id}")
        self.assertContains(coach_list, f"filledQuestionnaireCollapse{questionnaire.id}")
        self.assertContains(coach_list, "eval athlete")
        self.assertContains(coach_list, "No pain")

        filled_list = self.client.get(f"/evaluations/?filled={questionnaire.id}")
        self.assertContains(filled_list, "eval athlete")
        self.assertContains(filled_list, "No pain")

        coach_detail = self.client.get(f"/evaluations/?filled={questionnaire.id}&response={response.id}")
        self.assertContains(coach_detail, "eval athlete")
        self.assertContains(coach_detail, "Good")
        self.assertContains(coach_detail, "No pain")
        self.assertContains(coach_detail, "Development")
        self.assertContains(coach_detail, "Improved")

        delete_response = self.client.post(
            "/evaluations/",
            {"delete_questionnaire": str(questionnaire.id)},
        )
        self.assertEqual(delete_response.status_code, 302)
        self.assertFalse(EvaluationQuestionnaire.objects.filter(id=questionnaire.id).exists())
        self.assertFalse(EvaluationResponse.objects.filter(id=response.id).exists())

    def test_evaluation_questionnaire_can_target_groups_and_individual_athletes(self):
        coach = get_user_model().objects.create_user(username="audience-coach", password="secret", is_staff=True)
        first_user = get_user_model().objects.create_user(username="audience-first", password="secret")
        second_user = get_user_model().objects.create_user(username="audience-second", password="secret")
        first = Athlete.objects.create(owner=coach, name="Audience First", birth_year=2000, gender="X")
        second = Athlete.objects.create(owner=coach, name="Audience Second", birth_year=2001, gender="X")
        questionnaire = EvaluationQuestionnaire.objects.create(
            owner=coach,
            title="Selected audience",
            available_to_all=False,
        )
        questionnaire.available_to_athletes.add(first)
        EvaluationQuestion.objects.create(questionnaire=questionnaire, text="How are you?")

        self.client.force_login(first_user)
        self.assertContains(self.client.get("/evaluations/"), "Selected audience")
        self.assertEqual(self.client.get(f"/evaluations/{questionnaire.id}/").status_code, 200)

        self.client.force_login(second_user)
        self.assertNotContains(self.client.get("/evaluations/"), "Selected audience")
        self.assertEqual(self.client.get(f"/evaluations/{questionnaire.id}/").status_code, 404)

        self.client.force_login(coach)
        create_response = self.client.post(
            "/evaluations/",
            {
                "title": "One athlete only",
                "questions": "How was training?",
                "audience_mode": "selected",
                "available_athletes": [str(second.id)],
                "is_active": "on",
            },
        )
        self.assertEqual(create_response.status_code, 302)
        created = EvaluationQuestionnaire.objects.get(title="One athlete only")
        self.assertFalse(created.available_to_all)
        self.assertQuerySetEqual(created.available_to_athletes.all(), [second], transform=lambda item: item)

    def test_evaluation_title_and_audience_edit_preserves_submitted_answers(self):
        coach = get_user_model().objects.create_user(username="evaluation-edit-coach", password="secret", is_staff=True)
        first_user = get_user_model().objects.create_user(username="evaluation-edit-first", password="secret")
        second_user = get_user_model().objects.create_user(username="evaluation-edit-second", password="secret")
        first = Athlete.objects.create(owner=coach, name="Evaluation Edit First", birth_year=2000, gender="X")
        second = Athlete.objects.create(owner=coach, name="Evaluation Edit Second", birth_year=2001, gender="X")
        questionnaire = EvaluationQuestionnaire.objects.create(
            owner=coach,
            title="Original title",
            available_to_all=False,
        )
        questionnaire.available_to_athletes.add(first)
        question = EvaluationQuestion.objects.create(questionnaire=questionnaire, text="How did it go?")
        old_response = EvaluationResponse.objects.create(
            questionnaire=questionnaire,
            athlete=first,
            answers={str(question.id): "I felt good"},
        )

        self.client.force_login(coach)
        edit_page = self.client.get(f"/evaluations/?edit={questionnaire.id}")
        self.assertContains(edit_page, "Edit questionnaire")
        self.assertContains(edit_page, "Original title")
        self.assertContains(edit_page, "Evaluation Edit First")
        self.assertContains(edit_page, "Save changes")

        update = self.client.post(
            "/evaluations/",
            {
                "update_questionnaire": str(questionnaire.id),
                "title": "Updated title",
                "audience_mode": "selected",
                "available_athletes": [str(second.id)],
                "is_active": "on",
            },
        )
        self.assertEqual(update.status_code, 302)
        questionnaire.refresh_from_db()
        self.assertEqual(questionnaire.title, "Updated title")
        self.assertQuerySetEqual(questionnaire.available_to_athletes.all(), [second], transform=lambda item: item)
        self.assertTrue(EvaluationResponse.objects.filter(pk=old_response.pk).exists())
        self.assertEqual(EvaluationResponse.objects.get(pk=old_response.pk).answers[str(question.id)], "I felt good")

        self.client.force_login(first_user)
        self.assertNotContains(self.client.get("/evaluations/"), "Updated title")
        self.assertEqual(self.client.get(f"/evaluations/{questionnaire.id}/").status_code, 404)
        self.client.force_login(second_user)
        self.assertContains(self.client.get("/evaluations/"), "Updated title")
        self.client.force_login(coach)
        self.assertContains(self.client.get(f"/evaluations/?filled={questionnaire.id}"), "Evaluation Edit First")

    def test_evaluation_copy_sources_require_edit_access_and_copy_structure_only(self):
        coach = get_user_model().objects.create_user(username="copy-target", password="secret", is_staff=True)
        editable = get_user_model().objects.create_user(username="copy-editable", password="secret", is_staff=True)
        view_only = get_user_model().objects.create_user(username="copy-view-only", password="secret", is_staff=True)
        CoachAccess.objects.create(owner=editable, grantee=coach, can_edit=True)
        CoachAccess.objects.create(owner=view_only, grantee=coach, can_edit=False)
        source = EvaluationQuestionnaire.objects.create(owner=editable, title="English SEAS")
        text_question = EvaluationQuestion.objects.create(questionnaire=source, text="How do you feel?", order=1)
        EvaluationQuestion.objects.create(
            questionnaire=source,
            text="Progress",
            order=2,
            question_type=EvaluationQuestion.TYPE_MATRIX,
            matrix_columns=["2025", "2026"],
            matrix_rows=["Strength"],
        )
        source_athlete = Athlete.objects.create(owner=editable, name="Copy source athlete", birth_year=2000, gender="X")
        EvaluationResponse.objects.create(questionnaire=source, athlete=source_athlete, answers={str(text_question.id): "Private answer"})
        hidden = EvaluationQuestionnaire.objects.create(owner=view_only, title="No edit access")

        self.client.force_login(coach)
        copy_page = self.client.get(f"/evaluations/?new=1&copy={source.id}")
        self.assertContains(copy_page, "English SEAS")
        self.assertNotContains(copy_page, "No edit access")
        self.assertContains(copy_page, "Available to")

        response = self.client.post(
            "/evaluations/",
            {
                "title": "English SEAS copy",
                "description": "Translated version",
                "questions": "How do you feel?",
                "matrix_title": "Progress",
                "matrix_columns": "2025\n2026",
                "matrix_rows": "Strength",
                "audience_mode": "all",
                "is_active": "on",
            },
        )
        self.assertEqual(response.status_code, 302)
        copied = EvaluationQuestionnaire.objects.get(owner=coach, title="English SEAS copy")
        self.assertEqual(copied.questions.count(), 2)
        self.assertEqual(copied.questions.get(question_type=EvaluationQuestion.TYPE_MATRIX).matrix_columns, ["2025", "2026"])
        self.assertFalse(copied.responses.exists())
        self.assertTrue(EvaluationQuestionnaire.objects.filter(pk=source.pk, owner=editable).exists())
        self.assertTrue(EvaluationQuestionnaire.objects.filter(pk=hidden.pk, owner=view_only).exists())

    def test_pr_database_lists_records_with_freshness_colors(self):
        user = get_user_model().objects.create_user(username="pr-db-coach", password="secret", is_staff=True)
        fresh = MatchAthleteRecord.objects.create(
            owner=user,
            athlete_name="Fresh Athlete",
            records=_parse_match_athlete_records("40 meter\t7,05\t20/06/2026"),
        )
        stale = MatchAthleteRecord.objects.create(
            owner=user,
            athlete_name="Stale Athlete",
            records=_parse_match_athlete_records("600 meter\t2:25,13\t13/09/2025"),
        )
        MatchAthleteRecord.objects.create(
            owner=user,
            athlete_name="Id Only Athlete",
            atletiek_nu_id="911547",
            records={},
        )
        MatchAthleteRecord.objects.filter(id=stale.id).update(updated_at=timezone.now() - timedelta(days=100))
        self.client.force_login(user)

        response = self.client.get("/coach-tools/pr-database/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "PR-database")
        self.assertContains(response, f'href="/coach-tools/pr-database/{fresh.id}/"')
        self.assertContains(response, "Fresh Athlete")
        self.assertContains(response, "match-pr-fresh")
        self.assertContains(response, "Stale Athlete")
        self.assertContains(response, "match-pr-stale")
        self.assertNotContains(response, "0 PRs")
        self.assertContains(response, "Atletiek.nu fetch list")
        self.assertContains(response, "Id Only Athlete\t911547")

    def test_pr_database_detail_shows_current_prs(self):
        user = get_user_model().objects.create_user(username="pr-db-detail-coach", password="secret", is_staff=True)
        record = MatchAthleteRecord.objects.create(
            owner=user,
            athlete_name="Elodie Costerus",
            records=_parse_match_athlete_records(
                "40 meter\t7,05\t20/06/2026\n"
                "Verspringen\n"
                "Ontbrekende windmeting\t2,97\n"
                "n/a\t04/10/2025"
            ),
        )
        self.client.force_login(user)

        response = self.client.get(f"/coach-tools/pr-database/{record.id}/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Elodie Costerus")
        self.assertContains(response, "Last PR update")
        self.assertContains(response, "40 meter")
        self.assertContains(response, "7.05")
        self.assertContains(response, "Verspringen")
        self.assertContains(response, "2.97")

    def test_pr_database_import_updates_only_known_athlete_pbs(self):
        user = get_user_model().objects.create_user(username="pr-db-import-coach", password="secret", is_staff=True)
        MatchAthleteRecord.objects.create(
            owner=user,
            athlete_name="Logan Bosch",
            records=_parse_match_athlete_records(
                "40 meter\t8,20\t20/06/2026\n"
                "Vortex\t20,00\t20/06/2026"
            ),
        )
        self.client.force_login(user)

        response = self.client.post("/coach-tools/pr-database/add-pbs/", {
            "results_text": """
U8 Mannen - Meerkamp
# Naam 40m 600m Vortex Ver Punten totaal
11 Nederland<br><span class='subtext'>Europe</span> Logan Bosch 7,93 2:27,42 19,36 2,41 1155
12 Nederland<br><span class='subtext'>Europe</span> Unknown Runner 7,70 2:20,00 21,00 2,60 1300
""",
        })

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "<strong>3</strong> PBs updated")
        self.assertContains(response, "Missing athletes")
        self.assertContains(response, "Unknown Runner")
        self.assertFalse(MatchAthleteRecord.objects.filter(owner=user, athlete_name="Unknown Runner").exists())
        record = MatchAthleteRecord.objects.get(owner=user, athlete_name="Logan Bosch")
        self.assertEqual(record.records["40meter"]["value"], "7.93")
        self.assertEqual(record.records["600meter"]["value"], "2:27.42")
        self.assertEqual(record.records["vortexwerpen"]["value"], "20.00")
        self.assertEqual(record.records["verspringen"]["value"], "2.41")

    def test_pr_database_import_accepts_local_atletiek_fetch_output(self):
        user = get_user_model().objects.create_user(username="pr-db-batch-coach", password="secret", is_staff=True)
        self.client.force_login(user)

        response = self.client.post("/coach-tools/pr-database/add-pbs/", {
            "action": "import_fetched_prs",
            "results_text": """
MILA_ATLETIEK_PB_EXPORT_V1
ATHLETE	Fenna Coevoet	911547
60 meter
9,54	03/04/2026
Verspringen
3,93	24/01/2026
END
""",
        })

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "<strong>2</strong> PBs updated")
        record = MatchAthleteRecord.objects.get(owner=user, athlete_name="Fenna Coevoet")
        self.assertEqual(record.atletiek_nu_id, "911547")
        self.assertEqual(record.records["60meter"]["value"], "9.54")
        self.assertEqual(record.records["verspringen"]["display_date"], "01/2026")

    def test_pr_database_import_auto_detects_space_separated_fetch_output(self):
        user = get_user_model().objects.create_user(username="pr-db-space-batch-coach", password="secret", is_staff=True)
        self.client.force_login(user)

        response = self.client.post("/coach-tools/pr-database/add-pbs/", {
            "action": "process_results",
            "results_text": """
MILA_ATLETIEK_PB_EXPORT_V1
ATHLETE Aurora Somers 906160
80 meter
11,11	01/09/2026
END
""",
        })

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "<strong>1</strong> PB updated")
        record = MatchAthleteRecord.objects.get(owner=user, athlete_name="Aurora Somers")
        self.assertEqual(record.atletiek_nu_id, "906160")
        self.assertEqual(record.records["80meter"]["value"], "11.11")


class MatchOverviewTests(TestCase):
    def test_match_overview_page_processes_pasted_atletiek_data(self):
        user = get_user_model().objects.create_user(
            username="match-coach",
            password="secret",
            is_staff=True,
        )
        self.client.force_login(user)

        create_response = self.client.post("/coach-tools/match-overview/new/")
        self.assertEqual(create_response.status_code, 302)
        match = MatchOverview.objects.get(owner=user)

        schedule = """
| [19:00](x) | [Groep 1](x) | [Verspringen](x) | |
| [19:30](x) | | [80 meter horden](x) | |
| [21:50](x) | | [80 meter](x) | |
| [22:00](x) | | [100 meter](x) | |
"""
        participants = """
26 Nederland<br><span class='subtext'>Europe</span> Aurora Somers AV Atverni 80m
 80mH
80 meter
80 meter horden
U16 Vrouwen
199 Nederland<br><span class='subtext'>Europe</span> Lene Prins AV Atverni 1000m
 Speer
1000 meter
U16 Vrouwen
"""

        response = self.client.post(f"/coach-tools/match-overview/{match.id}/", {
            "name": "Test match",
            "schedule_text": schedule,
            "participants_text": participants,
            "action": "process",
        })

        self.assertEqual(response.status_code, 200)
        match.refresh_from_db()
        self.assertEqual(match.name, "Test match")
        self.assertEqual(len(match.rows), 2)
        self.assertEqual(match.rows[0]["event_name"], "80 meter horden")
        self.assertEqual(match.rows[0]["event_detail"], "")
        self.assertNotContains(response, "id=\"scheduleText\"")
        self.assertNotContains(response, "id=\"participantsText\"")
        rows = response.context["rows"]
        self.assertEqual(len(rows), 2)
        self.assertEqual([row["athlete"] for row in rows], ["Aurora Somers", "Aurora Somers"])
        self.assertEqual([row["event"] for row in rows], ["80 meter horden", "80 meter"])
        self.assertContains(response, "80 meter horden")
        self.assertContains(response, "80 meter")

    def test_match_overview_notes_are_saved(self):
        user = get_user_model().objects.create_user(
            username="match-notes-coach",
            password="secret",
            is_staff=True,
        )
        match = MatchOverview.objects.create(
            owner=user,
            name="Notes match",
            schedule_text="19:30\t\t80 meter horden\t 4 series",
            participants_text="26\tAurora Somers\tAV Atverni\t80mH\n80 meter horden\nU16 Vrouwen",
            rows=[{
                "time": "19:30",
                "athlete": "Aurora Somers",
                "category": "U16 Vrouwen",
                "event": "80 meter horden",
                "note": "",
            }],
        )
        self.client.force_login(user)

        response = self.client.post(f"/coach-tools/match-overview/{match.id}/", {
            "action": "save_notes",
            "result_0": "13.42",
            "note_0": "PR candidate",
            "done_0": "1",
            "pb_0": "1",
        })

        self.assertEqual(response.status_code, 302)
        match.refresh_from_db()
        self.assertEqual(match.rows[0]["result"], "13.42")
        self.assertEqual(match.rows[0]["note"], "PR candidate")
        self.assertEqual(match.rows[0]["done"], True)
        self.assertEqual(match.rows[0]["pb"], True)

        detail = self.client.get(f"/coach-tools/match-overview/{match.id}/")
        self.assertContains(detail, "13.42")
        self.assertContains(detail, "PR candidate")
        self.assertContains(detail, "checked")
        self.assertContains(detail, "matchNotesForm")
        self.assertContains(detail, "Saving...")
        self.assertNotContains(detail, "Before race")
        self.assertNotContains(detail, "PR, SB, DNS, note")
        self.assertNotContains(detail, "Save notes")
        self.assertNotContains(detail, "<th>Category</th>")
        self.assertNotContains(detail, "<th>Pre-note</th>")
        self.assertContains(detail, "<th>PR</th>")
        self.assertContains(detail, "<th>Result</th>")
        self.assertContains(detail, "<th>Trainer notes</th>")
        self.assertContains(detail, "<th>Done?</th>")
        self.assertNotContains(detail, "id=\"scheduleText\"")

    def test_match_overview_can_be_deleted_from_list(self):
        user = get_user_model().objects.create_user(
            username="match-delete-coach",
            password="secret",
            is_staff=True,
        )
        match = MatchOverview.objects.create(owner=user, name="Delete me")
        keep_match = MatchOverview.objects.create(owner=user, name="Keep me")
        self.client.force_login(user)

        list_response = self.client.get("/coach-tools/match-overview/")
        self.assertContains(list_response, "Delete me")
        self.assertContains(list_response, "Del")

        response = self.client.post(f"/coach-tools/match-overview/{match.id}/delete/")

        self.assertEqual(response.status_code, 302)
        self.assertFalse(MatchOverview.objects.filter(id=match.id).exists())
        self.assertTrue(MatchOverview.objects.filter(id=keep_match.id).exists())

    def test_match_parser_keeps_multiple_events_as_separate_rows(self):
        schedule = _parse_match_schedule("""
| [19:30](x) | | [80 meter horden](x) | |
| [21:50](x) | | [80 meter](x) | |
""")
        rows = _parse_match_participants("""
26 Nederland<br><span class='subtext'>Europe</span> Aurora Somers AV Atverni 80m
 80mH
80 meter
80 meter horden
U16 Vrouwen
""", schedule)

        self.assertEqual([row["time"] for row in rows], ["19:30", "21:50"])
        self.assertEqual([row["athlete"] for row in rows], ["Aurora Somers", "Aurora Somers"])

    def test_match_parser_accepts_tab_schedule_and_partial_bib_rows(self):
        schedule = _parse_match_schedule("""
18:45		110 meter horden	 3 series
19:05		100 meter horden	 4 series
19:00	Groep 1 aanvang 1,03m	Hoogspringen
Hoog 1	 13 atleten
21:30	Groep 3	Verspringen
Ver 1	 16 atleten
21:15		400 meter	 7 series
""")
        rows = _parse_match_participants("""
Aimee Bonouvrie	AV Atverni	 100mH
 Ver
100 meter horden
Verspringen groep 3
U18 Vrouwen
522	 Thomas Pronk	AV Atverni	 400m
 Hoog
400 meter
Hoogspringen groep 2 aanvang 1,23m
U18 Mannen
""", schedule)

        self.assertEqual([row["athlete"] for row in rows], ["Aimee Bonouvrie", "Thomas Pronk", "Aimee Bonouvrie"])
        self.assertEqual([row["event"] for row in rows], ["100 meter horden", "400 meter", "Verspringen Groep 3"])

    def test_match_parser_ignores_short_only_abbreviations(self):
        schedule = _parse_match_schedule("""
19:30		80 meter horden	 4 series
21:50		80 meter	 3 series
""")
        rows = _parse_match_participants("""
26	Nederland<br><span class='subtext'>Europe</span> Aurora Somers	AV Atverni	 80m
 80mH
U16 Vrouwen
""", schedule)

        self.assertEqual(rows, [])

    def test_match_parser_does_not_cross_match_groups_between_events(self):
        schedule = _parse_match_schedule("""
19:00	Groep 1	Kogelstoten	 16 atleten
20:15	Groep 2	Kogelstoten	 17 atleten
21:30	Groep 3	Kogelstoten	 17 atleten
19:00	Groep 1 aanvang 1,03m	Hoogspringen
21:30	Groep 3	Verspringen
""")
        rows = _parse_match_participants("""
99	Nederland<br><span class='subtext'>Europe</span> Fenna Coevoet	AV Atverni	 Kogel
 Hoog
 Ver
Kogelstoten groep 2
Hoogspringen groep 1 aanvang 1,03m
Verspringen groep 3
U14 Vrouwen
""", schedule)

        kogel_rows = [row for row in rows if row["event"].startswith("Kogelstoten")]
        self.assertEqual(len(kogel_rows), 1)
        self.assertEqual(kogel_rows[0]["time"], "20:15")
        self.assertEqual(kogel_rows[0]["event"], "Kogelstoten Groep 2")
        self.assertEqual(kogel_rows[0]["event_name"], "Kogelstoten")
        self.assertEqual(kogel_rows[0]["event_detail"], "Groep 2")

    def test_match_parser_supports_multievent_group_schedule_rows(self):
        schedule = _parse_match_schedule("""
10:05	U10 - V Groep 2	Verspringen
Ver 2	 18 atleten
10:40	U10-V - Groep 1	Verspringen
Ver 2	 18 atleten
11:40	U10-V - Groep 1
U10 - V Groep 2	40 meter	 5 series
12:25	U10-V - Groep 1	Kogelstoten	 18 atleten
13:00	U10 - V Groep 2	Kogelstoten	 18 atleten
14:40	U10-V - Groep 1
U10 - V Groep 2	1000 meter	 2 series
""")
        rows = _parse_match_participants("""
Elodie Costerus	AV Atverni	Meerkamp
U10-V - Groep 1
U10 - V Groep 2
U10 Vrouwen
""", schedule)

        self.assertEqual(
            [(row["time"], row["event_name"], row["event_detail"]) for row in rows],
            [
                ("10:05", "Verspringen", "U10 - V Groep 2"),
                ("11:40", "40 meter", "U10 - V Groep 2"),
                ("13:00", "Kogelstoten", "U10 - V Groep 2"),
                ("14:40", "1000 meter", "U10 - V Groep 2"),
            ],
        )

    def test_match_parser_matches_multievent_combined_race_rows_for_top_group(self):
        schedule = _parse_match_schedule("""
10:40	U8-M - Groep 1
U8-M Groep 2	40 meter	 5 series
11:15	U8-M - Groep 1	Vortexwerpen
Vortex 1	 17 atleten
13:40	U8-M - Groep 1
U8-M Groep 2	600 meter	 2 series
""")
        rows = _parse_match_participants("""
569	Nederland<br><span class='subtext'>Europe</span> Logan Bosch	AV Atverni	Meerkamp
U8-M - Groep 1
U8 Mannen
""", schedule)

        self.assertEqual(
            [(row["time"], row["event_name"], row["event_detail"]) for row in rows],
            [
                ("10:40", "40 meter", "U8-M - Groep 1"),
                ("11:15", "Vortexwerpen", "U8-M - Groep 1"),
                ("13:40", "600 meter", "U8-M - Groep 1"),
            ],
        )

    def test_match_athlete_records_parse_atletiek_pr_block(self):
        records = _parse_match_athlete_records("""
40 meter	7,05
+1,3 m/s	20/06/2026
Nederland<br><span class="subtext">Europe</span> Nieuwegein
600 meter	2:25,13	13/09/2025
Nederland<br><span class="subtext">Europe</span> Zeist
Vortex	16,36	30/05/2026
Nederland<br><span class="subtext">Europe</span> Utrecht
Verspringen
Ontbrekende windmeting	2,97
n/a	04/10/2025
Nederland<br><span class="subtext">Europe</span> Nieuwegein
""")

        self.assertEqual(records["verspringen"]["label"], "2,97 (04/10/2025)")
        self.assertEqual(records["40meter"]["label"], "7,05 (20/06/2026)")
        self.assertEqual(records["vortexwerpen"]["label"], "16,36 (30/05/2026)")

    def test_match_athlete_records_parse_profile_events_without_bleeding_dates(self):
        records = _parse_match_athlete_records("""
200 meter 22,64 03/02/2024
Metz
300 meter 40,14 07/05/2016
Lisse
400 meter 49,17 02/03/2024
Glasgow
400 meter horden
76.2cm 50,95 14/07/2024
La Chaux-De-Fonds
""")

        self.assertEqual(records["200meter"]["label"], "22,64 (03/02/2024)")
        self.assertEqual(records["300meter"]["label"], "40,14 (07/05/2016)")
        self.assertEqual(records["400meter"]["label"], "49,17 (02/03/2024)")
        self.assertEqual(records["400meterhorden"]["label"], "50,95 (14/07/2024)")

    def test_match_athlete_records_keep_shot_put_weights_separate(self):
        records = _parse_match_athlete_records("""
Kogelstoten
2kg	3,87	20/06/2026
Nieuwegein
Kogelstoten
3kg	3,21	01/09/2026
Zeist
Kogelslingeren
4kg	18,00	02/09/2026
Utrecht
""")

        self.assertEqual(records["kogelstoten2kg"]["event"], "Kogelstoten 2kg")
        self.assertEqual(records["kogelstoten2kg"]["label"], "3,87 (20/06/2026)")
        self.assertEqual(records["kogelstoten3kg"]["event"], "Kogelstoten 3kg")
        self.assertEqual(records["kogelstoten3kg"]["label"], "3,21 (01/09/2026)")
        self.assertEqual(records["kogelslingeren4kg"]["event"], "Kogelslingeren 4kg")

    def test_match_athlete_records_parse_markdown_weighted_field_rows(self):
        records = _parse_match_athlete_records("""
| Kogelstoten<br>3kg | **8,14** | **06/06/2026**<br>** Hilversum ** |
| :----------------- | :------- | :------------------------------------------ |
| Discuswerpen | **17,22** | **06/06/2026**<br>** Hilversum ** |
""")

        self.assertEqual(records["kogelstoten3kg"]["event"], "Kogelstoten 3kg")
        self.assertEqual(records["kogelstoten3kg"]["value"], "8.14")
        self.assertEqual(records["kogelstoten3kg"]["display_date"], "06/2026")
        self.assertEqual(records["discuswerpen"]["event"], "Discuswerpen")
        self.assertEqual(records["discuswerpen"]["value"], "17.22")

    def test_match_athlete_prs_can_be_imported_from_match_row(self):
        user = get_user_model().objects.create_user(
            username="match-pr-coach",
            password="secret",
            is_staff=True,
        )
        match = MatchOverview.objects.create(
            owner=user,
            name="PR match",
            rows=[{
                "time": "10:05",
                "athlete": "Elodie Costerus",
                "category": "U10 Vrouwen",
                "event": "Verspringen U10 - V Groep 2",
                "event_name": "Verspringen",
                "event_detail": "U10 - V Groep 2",
                "pre_note": "",
                "note": "",
                "pb": False,
            }],
        )
        self.client.force_login(user)

        response = self.client.post(f"/coach-tools/match-overview/{match.id}/", {
            "action": "save_prs",
            "athlete_name": "Elodie Costerus",
            "records_text": """
Verspringen
Ontbrekende windmeting	2,97
n/a	04/10/2025
Nederland<br><span class="subtext">Europe</span> Nieuwegein
""",
        })

        self.assertEqual(response.status_code, 302)
        record = MatchAthleteRecord.objects.get(owner=user, athlete_name="Elodie Costerus")
        self.assertEqual(record.records["verspringen"]["label"], "2,97 (04/10/2025)")
        self.assertEqual(record.records["verspringen"]["display_date"], "10/2025")
        match.refresh_from_db()

        detail = self.client.get(f"/coach-tools/match-overview/{match.id}/")
        self.assertContains(detail, "2,97")
        self.assertContains(detail, "10/2025")
        self.assertNotContains(detail, "PR 2,97")
        self.assertContains(detail, "matchAthletePrModal")
        self.assertContains(detail, "matchFetchPrButton")
        self.assertContains(detail, "Opening Atletiek.nu fetch. This can take a moment.")
        self.assertNotContains(detail, "button.disabled = true")

    def test_match_athlete_prs_can_be_fetched_from_atletiek_id(self):
        user = get_user_model().objects.create_user(
            username="match-pr-fetch-coach",
            password="secret",
            is_staff=True,
        )
        match = MatchOverview.objects.create(
            owner=user,
            name="PR fetch match",
            rows=[{
                "time": "10:05",
                "athlete": "Elodie Costerus",
                "category": "U10 Vrouwen",
                "event": "Verspringen U10 - V Groep 2",
                "event_name": "Verspringen",
                "event_detail": "U10 - V Groep 2",
                "pre_note": "",
                "note": "",
                "pb": False,
            }],
        )
        self.client.force_login(user)

        with patch("core.views.coach._fetch_atletiek_nu_records", return_value=({
            "verspringen": {
                "event": "Verspringen",
                "value": "3.28",
                "label": "3,28 (12/09/2026)",
                "date": "12/09/2026",
                "display_date": "09/2026",
                "context": "",
            },
        }, "https://www.atletiek.nu/atleet/profiel/2912083/#records", "")):
            response = self.client.post(f"/coach-tools/match-overview/{match.id}/", {
                "action": "fetch_prs",
                "athlete_name": "Elodie Costerus",
                "atletiek_nu_id": "2912083",
            })

        self.assertEqual(response.status_code, 302)
        record = MatchAthleteRecord.objects.get(owner=user, athlete_name="Elodie Costerus")
        self.assertEqual(record.atletiek_nu_id, "2912083")
        self.assertEqual(record.records["verspringen"]["value"], "3.28")

        detail = self.client.get(f"/coach-tools/match-overview/{match.id}/")
        self.assertContains(detail, "Fetched 1 PRs from Atletiek.nu for Elodie Costerus.")
        self.assertContains(detail, "3,28")
        self.assertContains(detail, "2912083")

    def test_match_athlete_pr_fetch_failure_shows_message(self):
        user = get_user_model().objects.create_user(
            username="match-pr-fetch-error-coach",
            password="secret",
            is_staff=True,
        )
        match = MatchOverview.objects.create(
            owner=user,
            name="PR fetch error match",
            rows=[{
                "time": "10:05",
                "athlete": "Elodie Costerus",
                "category": "U10 Vrouwen",
                "event": "Verspringen U10 - V Groep 2",
                "event_name": "Verspringen",
                "event_detail": "U10 - V Groep 2",
                "pre_note": "",
                "note": "",
                "pb": False,
            }],
        )
        self.client.force_login(user)

        with patch("core.views.coach._fetch_atletiek_nu_records", return_value=({}, "https://www.atletiek.nu/atleet/profiel/2912083/#records", "Atletiek.nu fetch failed: Playwright is not installed.")):
            response = self.client.post(f"/coach-tools/match-overview/{match.id}/", {
                "action": "fetch_prs",
                "athlete_name": "Elodie Costerus",
                "atletiek_nu_id": "2912083",
            })

        self.assertEqual(response.status_code, 302)
        record = MatchAthleteRecord.objects.get(owner=user, athlete_name="Elodie Costerus")
        self.assertEqual(record.atletiek_nu_id, "2912083")
        self.assertEqual(record.records, {})
        match.refresh_from_db()
        self.assertEqual(len(match.rows), 1)
        self.assertEqual(match.rows[0]["athlete"], "Elodie Costerus")
        detail = self.client.get(f"/coach-tools/match-overview/{match.id}/")
        self.assertContains(detail, "Saved Atletiek.nu ID 2912083 for Elodie Costerus.")
        self.assertContains(detail, "Atletiek.nu fetch failed: Playwright is not installed.")
        self.assertContains(detail, "2912083")

    def test_match_athlete_pr_display_survives_notes_autosave(self):
        user = get_user_model().objects.create_user(
            username="match-pr-autosave-coach",
            password="secret",
            is_staff=True,
        )
        match = MatchOverview.objects.create(
            owner=user,
            name="PR autosave match",
            rows=[
                {
                    "time": "10:05",
                    "athlete": "Logan Bosch",
                    "category": "U8 Mannen",
                    "event": "Verspringen U8-M - Groep 1",
                    "event_name": "Verspringen",
                    "event_detail": "U8-M - Groep 1",
                    "pre_note": "",
                    "note": "",
                    "pb": False,
                },
                {
                    "time": "11:15",
                    "athlete": "Logan Bosch",
                    "category": "U8 Mannen",
                    "event": "Vortexwerpen U8-M - Groep 1",
                    "event_name": "Vortexwerpen",
                    "event_detail": "U8-M - Groep 1",
                    "pre_note": "",
                    "note": "",
                    "pb": False,
                },
            ],
        )
        self.client.force_login(user)
        MatchAthleteRecord.objects.create(
            owner=user,
            athlete_name="Logan Bosch",
            records=_parse_match_athlete_records("""
Verspringen	2,97	04/10/2025
Vortex	16,36	30/05/2026
"""),
        )

        response = self.client.post(f"/coach-tools/match-overview/{match.id}/", {
            "action": "save_notes",
            "result_0": "2,91",
            "note_0": "",
            "done_0": "1",
            "result_1": "17,02",
            "note_1": "",
        })

        self.assertEqual(response.status_code, 302)
        match.refresh_from_db()
        self.assertEqual(match.rows[0]["result"], "2,91")
        self.assertEqual(match.rows[0]["done"], True)
        self.assertEqual(match.rows[1]["result"], "17,02")
        self.assertEqual(match.rows[1]["done"], False)
        detail = self.client.get(f"/coach-tools/match-overview/{match.id}/")
        self.assertContains(detail, "2,97")
        self.assertContains(detail, "10/2025")
        self.assertContains(detail, "16,36")
        self.assertContains(detail, "05/2026")
        self.assertContains(detail, "match-done-row")

    def test_match_athlete_names_show_pr_record_age_status(self):
        user = get_user_model().objects.create_user(
            username="match-pr-status-coach",
            password="secret",
            is_staff=True,
        )
        match = MatchOverview.objects.create(
            owner=user,
            name="PR status match",
            rows=[
                {
                    "time": "10:00",
                    "athlete": "Fresh Athlete",
                    "event": "40 meter",
                    "event_name": "40 meter",
                    "event_detail": "",
                    "note": "",
                    "pb": False,
                },
                {
                    "time": "10:05",
                    "athlete": "Recent Athlete",
                    "event": "40 meter",
                    "event_name": "40 meter",
                    "event_detail": "",
                    "note": "",
                    "pb": False,
                },
                {
                    "time": "10:10",
                    "athlete": "Aging Athlete",
                    "event": "40 meter",
                    "event_name": "40 meter",
                    "event_detail": "",
                    "note": "",
                    "pb": False,
                },
                {
                    "time": "10:15",
                    "athlete": "Stale Athlete",
                    "event": "40 meter",
                    "event_name": "40 meter",
                    "event_detail": "",
                    "note": "",
                    "pb": False,
                },
                {
                    "time": "10:20",
                    "athlete": "Never Athlete",
                    "event": "40 meter",
                    "event_name": "40 meter",
                    "event_detail": "",
                    "note": "",
                    "pb": False,
                },
            ],
        )
        for name in ("Fresh Athlete", "Recent Athlete", "Aging Athlete", "Stale Athlete"):
            MatchAthleteRecord.objects.create(
                owner=user,
                athlete_name=name,
                records=_parse_match_athlete_records("40 meter\t7,05\t20/06/2026"),
            )
        MatchAthleteRecord.objects.filter(owner=user, athlete_name="Recent Athlete").update(updated_at=timezone.now() - timedelta(days=20))
        MatchAthleteRecord.objects.filter(owner=user, athlete_name="Aging Athlete").update(updated_at=timezone.now() - timedelta(days=55))
        MatchAthleteRecord.objects.filter(owner=user, athlete_name="Stale Athlete").update(updated_at=timezone.now() - timedelta(days=100))
        self.client.force_login(user)

        detail = self.client.get(f"/coach-tools/match-overview/{match.id}/")

        self.assertContains(detail, 'match-athlete-btn match-pr-fresh')
        self.assertContains(detail, 'match-athlete-btn match-pr-recent')
        self.assertContains(detail, 'match-athlete-btn match-pr-aging')
        self.assertContains(detail, 'match-athlete-btn match-pr-stale" data-bs-toggle="modal" data-bs-target="#matchAthletePrModal" data-athlete="Stale Athlete"')
        self.assertContains(detail, 'match-athlete-btn match-pr-stale" data-bs-toggle="modal" data-bs-target="#matchAthletePrModal" data-athlete="Never Athlete"')


class PlanningOverviewTests(TestCase):
    def test_daily_overview_other_counts_evaluated_training_slots_with_quality_color(self):
        coach = get_user_model().objects.create_user(
            username="evaluation-quality-coach", password="secret", is_staff=True
        )
        athlete = Athlete.objects.create(
            owner=coach,
            name="Evaluation Quality Athlete",
            birth_year=2000,
            gender="X",
        )
        plan = TrainingPlan.objects.create(
            owner=coach,
            name="Evaluation quality plan",
            plan_kind=TrainingPlan.PLAN_KIND_TRAINER,
        )
        PlanMembership.objects.create(plan=plan, athlete=athlete)
        today = date.today()
        for offset in (1, 2, 3):
            slot = TrainingSlot.objects.create(
                plan=plan,
                date=today - timedelta(days=offset),
                slot_index=1,
            )
            slot.segments.create(type="CORE", text="Easy run", order=0)
        AthleteDayCheck.objects.create(
            athlete=athlete,
            date=today - timedelta(days=1),
            slot_index=1,
            status=AthleteDayCheck.STATUS_DONE_AS_PLANNED,
            checked=True,
            rpe=6,
            comment="Good",
            updated_by=coach,
        )

        self.client.force_login(coach)
        response = self.client.get("/coach/daily-overview-other/")

        self.assertEqual(response.status_code, 200)
        row = response.context["athlete_rows"][0]
        self.assertEqual(row["evaluated_count"], 1)
        self.assertEqual(row["evaluated_color"], "orange")
        self.assertContains(response, "Evaluated")

    def test_vital_switch_keeps_vitals_open_instead_of_info_quality(self):
        coach = get_user_model().objects.create_user(
            username="vital-switch-coach", password="secret", is_staff=True
        )
        self.client.force_login(coach)
        for vital in ("sleep_hours", "sleep_quality", "morning_hr", "hrv"):
            with self.subTest(vital=vital):
                response = self.client.get("/coach/daily-overview-other/", {"vital": vital})
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, '<details class="overview-block" open>\n    <summary>Vitals')
                self.assertContains(response, '<details class="overview-block">\n    <summary>Info Quality')

    def test_athlete_team_follows_coach_team(self):
        coach = get_user_model().objects.create_user(
            username="team-coach", password="secret", is_staff=True
        )
        atverni, _ = Team.objects.get_or_create(name="Atverni")
        llg, _ = Team.objects.get_or_create(name="LLG")
        CoachSettings.objects.create(user=coach, team=atverni)

        athlete = Athlete.objects.create(
            owner=coach,
            name="Team Athlete",
            birth_year=2000,
            gender="X",
        )
        self.assertEqual(athlete.team_id, atverni.id)

        settings = CoachSettings.objects.get(user=coach)
        settings.team = llg
        settings.save()
        athlete.refresh_from_db()
        self.assertEqual(athlete.team_id, llg.id)

    def test_coach_planning_overview_is_grouped(self):
        user = get_user_model().objects.create_user(
            username="planning-coach",
            password="secret",
            is_staff=True,
        )
        self.client.force_login(user)

        response = self.client.get("/planning/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Coach plannings")
        self.assertContains(response, "Views")
        self.assertContains(response, "Standards")
        self.assertContains(response, "Year Planner")
        self.assertContains(response, "Standard Strength")

    def test_daily_overview_other_shows_selected_vital_average(self):
        coach = get_user_model().objects.create_user(
            username="vitals-overview-coach",
            password="secret",
            is_staff=True,
        )
        athlete = Athlete.objects.create(
            owner=coach,
            name="Vital Athlete",
            birth_year=2000,
            gender="X",
        )
        second_athlete = Athlete.objects.create(
            owner=coach,
            name="Not Enough Vital Athlete",
            birth_year=2001,
            gender="X",
        )
        today = date.today()
        for offset, value in enumerate((7, 8, 9)):
            AthleteDailyVital.objects.create(
                athlete=athlete,
                date=today - timedelta(days=offset),
                sleep_hours=value,
            )
        for offset, value in enumerate((7, 8)):
            AthleteDailyVital.objects.create(
                athlete=second_athlete,
                date=today - timedelta(days=offset),
                sleep_hours=value,
            )

        self.client.force_login(coach)
        response = self.client.get("/coach/daily-overview-other/?vital=sleep_hours&show_na=1")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Sleep length")
        self.assertContains(response, "Vital Athlete")
        self.assertContains(response, "Not Enough Vital Athlete")
        self.assertContains(response, "8.0 h")
        self.assertContains(response, "NA")
        for key in ("sleep_hours", "sleep_quality", "morning_hr", "hrv"):
            self.assertContains(response, f"vital={key}")

        filtered = self.client.get("/coach/daily-overview-other/?vital=sleep_hours")
        self.assertEqual([row["athlete"].id for row in filtered.context["vital_rows"]], [athlete.id])
        self.assertFalse(filtered.context["show_na"])
        self.assertTrue(response.context["show_na"])
        for key in ("sleep_hours", "sleep_quality", "morning_hr", "hrv"):
            self.assertContains(response, f'vital={key}&amp;show_na=1')
        no_values = self.client.get("/coach/daily-overview-other/?vital=hrv")
        self.assertEqual(no_values.context["vital_rows"], [])
        shown_na = self.client.get("/coach/daily-overview-other/?vital=hrv&show_na=1")
        self.assertEqual(len(shown_na.context["vital_rows"]), 2)
        self.assertTrue(all(row["value"] == "NA" for row in shown_na.context["vital_rows"]))

    def test_daily_overview_other_shows_hr_zone_matrix_and_hides_empty_athletes(self):
        coach = get_user_model().objects.create_user(
            username="hr-zones-overview-coach",
            password="secret",
            is_staff=True,
        )
        Athlete.objects.create(
            owner=coach,
            name="Single HR Athlete",
            birth_year=2000,
            gender="X",
            zone_hr_bpm={"1": "145", "2": "160", "3": "175", "4": "185", "5": "190"},
        )
        Athlete.objects.create(
            owner=coach,
            name="Aligned HR Athlete",
            birth_year=2000,
            gender="X",
            zone_hr_bpm={"1": "0-145", "2": "146-160", "3": "161-175", "4": "176-185", "5": "186-190"},
        )
        Athlete.objects.create(
            owner=coach,
            name="Misaligned HR Athlete",
            birth_year=2000,
            gender="X",
            zone_hr_bpm={"1": "0-145", "2": "150-160"},
        )
        Athlete.objects.create(
            owner=coach,
            name="No HR Athlete",
            birth_year=2000,
            gender="X",
        )

        self.client.force_login(coach)
        response = self.client.get("/coach/daily-overview-other/?vital=hr_zones")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "HR zones")
        self.assertContains(response, "0-145")
        self.assertContains(response, "146-160")
        self.assertContains(response, "Single HR Athlete")
        self.assertContains(response, "hr-zone-misaligned", html=False)
        self.assertEqual(len(response.context["hr_zone_rows"]), 3)
        self.assertNotIn(
            "No HR Athlete",
            [row["athlete"].name for row in response.context["hr_zone_rows"]],
        )

        shown_na = self.client.get("/coach/daily-overview-other/?vital=hr_zones&show_na=1")
        self.assertEqual(len(shown_na.context["hr_zone_rows"]), 4)
        self.assertContains(shown_na, "No HR Athlete")
        self.assertContains(shown_na, ">NA<", html=False)

    def test_focus_points_page_lists_active_coach_athletes(self):
        coach = get_user_model().objects.create_user(
            username="focus-points-coach", password="secret", is_staff=True
        )
        CoachSettings.objects.create(user=coach, focus_points_enabled=True)
        Athlete.objects.create(owner=coach, name="Zoe Athlete", birth_year=2000, gender="X")
        Athlete.objects.create(owner=coach, name="Anna Athlete", birth_year=2000, gender="X")
        self.client.force_login(coach)

        planning = self.client.get("/planning/")
        self.assertContains(planning, "Focus Points and Desired Improvements")

        response = self.client.get("/planning/focus-points/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Anna Athlete")
        self.assertContains(response, "Zoe Athlete")
        self.assertContains(response, "Comment coaches")
        self.assertContains(response, "Overwrite")
        self.assertContains(response, "Overwrite other coaches")
        self.assertContains(response, 'aria-label="Add your comment for Endurance Z1–Z3"')
        self.assertContains(response, 'data-column-label="Plan"')
        self.assertContains(response, 'data-column-label="Progress"')
        self.assertContains(response, "focus-points-controls")
        self.assertContains(response, "focus-points-import")
        self.assertNotContains(response, "Leave this empty to remove your own comment.")

    def test_athlete_can_view_and_edit_only_own_desired_improvement_comments(self):
        coach = get_user_model().objects.create_user(
            username="desired-points-coach", password="secret", is_staff=True
        )
        athlete_user = get_user_model().objects.create_user(
            username="Desired Points Athlete", password="secret"
        )
        athlete = Athlete.objects.create(
            owner=coach,
            name="Desired Points Athlete",
            birth_year=2000,
            gender="X",
            see_desired_improvement_points=True,
        )
        CoachSettings.objects.create(user=coach, focus_points_enabled=True)
        setting = AthleteFocusPoint.objects.create(
            athlete=athlete,
            point_key="speed",
            priority=1,
            athlete_comment="Keep relaxed shoulders.",
            plan_text="Weekly sprint progression.",
            progress_text="Consistency improving.",
        )
        FocusPointComment.objects.create(
            athlete=athlete,
            coach=coach,
            point_key="speed",
            comment="Coach-only note.",
        )

        self.client.force_login(athlete_user)
        planning = self.client.get("/planning/")
        self.assertContains(planning, "Focus Points and Desired Improvements")
        page = self.client.get("/planning/focus-points/")
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, "Comments athletes")
        self.assertNotContains(page, ">Plan<", html=False)
        self.assertNotContains(page, ">Prio<", html=False)
        self.assertNotContains(page, ">Progress<", html=False)
        self.assertContains(page, "Keep relaxed shoulders.")
        self.assertNotContains(page, "Coach-only note.")
        self.assertNotContains(page, "Comment coaches")

        saved = self.client.post("/planning/focus-points/", {
            "athlete_id": str(athlete.id),
            "action": "athlete_comment",
            "point_key": "speed",
            "comment": "New athlete note.",
        })
        self.assertEqual(saved.status_code, 302)
        setting.refresh_from_db()
        self.assertEqual(setting.athlete_comment, "New athlete note.")

        self.client.force_login(coach)
        toggle = self.client.post("/planning/focus-points/", {
            "athlete_id": str(athlete.id),
            "action": "toggle_plan_visibility",
            "show_to_athlete": "on",
        })
        self.assertEqual(toggle.status_code, 302)
        athlete.refresh_from_db()
        self.assertTrue(athlete.show_plan_to_athlete)
        coach_page = self.client.get(f"/planning/focus-points/?athlete={athlete.id}")
        self.assertContains(coach_page, "New athlete note.")
        self.assertContains(coach_page, "Coach-only note.")
        self.assertContains(coach_page, "Show to athlete")

        self.client.force_login(athlete_user)
        shown_page = self.client.get("/planning/focus-points/")
        self.assertContains(shown_page, "Plan")
        self.assertContains(shown_page, "Prio")
        self.assertContains(shown_page, "Progress")
        self.assertContains(shown_page, "Weekly sprint progression.")
        self.assertContains(shown_page, "Consistency improving.")
        self.assertNotContains(shown_page, "Coach-only note.")
        self.assertNotContains(shown_page, "desired-points-coach")

    def test_focus_point_comments_are_per_coach_but_plan_and_progress_are_shared(self):
        coach = get_user_model().objects.create_user(
            username="Iain_Somers", password="secret", is_staff=True,
            first_name="Iain", last_name="Somers",
        )
        other_coach = get_user_model().objects.create_user(
            username="Tomasz_Olsthoorn_Lewandowski", password="secret", is_staff=True,
            first_name="Tomasz", last_name="Olsthoorn",
        )
        athlete = Athlete.objects.create(owner=coach, name="Focus Athlete", birth_year=2000, gender="X")
        CoachSettings.objects.create(user=coach, focus_points_enabled=True)
        key = "endurance_z1_z3"
        FocusPointComment.objects.create(
            athlete=athlete, coach=other_coach, point_key=key, comment="Needs more easy mileage."
        )
        self.client.force_login(coach)

        saved = self.client.post("/planning/focus-points/", {
            "athlete_id": str(athlete.id),
            "point_key": key,
            "comment": "Build consistently.",
        })
        self.assertRedirects(saved, f"/planning/focus-points/?athlete={athlete.id}&saved=1")
        self.assertEqual(FocusPointComment.objects.filter(athlete=athlete, point_key=key).count(), 2)
        page = self.client.get(f"/planning/focus-points/?athlete={athlete.id}")
        self.assertContains(page, "TL:")
        self.assertContains(page, "IS:")
        self.assertNotContains(page, "TO:")
        self.assertContains(page, "Needs more easy mileage.")

        for column, text in (("plan", "Build the weekly progression."), ("progress", "Improving steadily.")):
            saved_column = self.client.post("/planning/focus-points/", {
                "athlete_id": str(athlete.id),
                "action": "shared_note",
                "point_key": key,
                "column": column,
                "comment": text,
            })
            self.assertEqual(saved_column.status_code, 302)
            setting = AthleteFocusPoint.objects.get(athlete=athlete, point_key=key)
            self.assertEqual(getattr(setting, f"{column}_text"), text)

        page = self.client.get(f"/planning/focus-points/?athlete={athlete.id}")
        self.assertContains(page, "Build the weekly progression.")
        self.assertContains(page, "Improving steadily.")
        self.assertContains(page, 'class="focus-priority-column"')

        # A second editable coach overwrites the one shared value, without a coach prefix.
        second_editor = get_user_model().objects.create_user(
            username="shared-note-editor", password="secret", is_staff=True,
        )
        CoachAccess.objects.create(owner=coach, grantee=second_editor, can_edit=True)
        self.client.force_login(second_editor)
        session = self.client.session
        session["active_coach_owner_id"] = coach.id
        session.save()
        replaced_plan = self.client.post("/planning/focus-points/", {
            "athlete_id": str(athlete.id),
            "action": "shared_note",
            "point_key": key,
            "column": "plan",
            "comment": "Updated plan for everyone.",
        })
        self.assertEqual(replaced_plan.status_code, 302)
        setting.refresh_from_db()
        self.assertEqual(setting.plan_text, "Updated plan for everyone.")
        shared_page = self.client.get(f"/planning/focus-points/?athlete={athlete.id}")
        self.assertContains(shared_page, "Updated plan for everyone.")
        self.assertNotContains(shared_page, "TL: Updated plan")

        self.client.force_login(coach)
        replaced = self.client.post("/planning/focus-points/", {
            "athlete_id": str(athlete.id),
            "point_key": key,
            "comment": "Only this comment remains.",
            "overwrite_all": "on",
        })
        self.assertRedirects(replaced, f"/planning/focus-points/?athlete={athlete.id}&saved=1")
        remaining = FocusPointComment.objects.filter(athlete=athlete, point_key=key)
        self.assertEqual(remaining.count(), 1)
        self.assertEqual(remaining.get().coach_id, coach.id)
        self.assertEqual(remaining.get().comment, "Only this comment remains.")

    def test_focus_point_edit_rights_are_required_for_shared_coach_comments(self):
        owner = get_user_model().objects.create_user(
            username="focus-shared-owner", password="secret", is_staff=True
        )
        editor = get_user_model().objects.create_user(
            username="focus-shared-editor", password="secret", is_staff=True
        )
        athlete = Athlete.objects.create(owner=owner, name="Shared Focus Athlete", birth_year=2000, gender="X")
        CoachSettings.objects.create(user=owner, focus_points_enabled=True)
        access = CoachAccess.objects.create(owner=owner, grantee=editor, can_edit=True)
        self.client.force_login(editor)
        session = self.client.session
        session["active_coach_owner_id"] = owner.id
        session.save()

        editable = self.client.get(f"/planning/focus-points/?athlete={athlete.id}")
        self.assertEqual(editable.status_code, 200)
        self.assertContains(editable, "Add comment")
        saved = self.client.post("/planning/focus-points/", {
            "athlete_id": str(athlete.id),
            "point_key": "speed",
            "comment": "Shared edit note.",
        })
        self.assertEqual(saved.status_code, 302)
        self.assertTrue(FocusPointComment.objects.filter(athlete=athlete, coach=editor, comment="Shared edit note.").exists())

        access.can_edit = False
        access.save(update_fields=["can_edit"])
        view_only = self.client.get(f"/planning/focus-points/?athlete={athlete.id}")
        self.assertEqual(view_only.status_code, 200)
        self.assertContains(view_only, "View only")
        denied = self.client.post("/planning/focus-points/", {
            "athlete_id": str(athlete.id),
            "point_key": "speed",
            "comment": "Should not save.",
        })
        self.assertEqual(denied.status_code, 403)
        import_denied = self.client.post("/planning/focus-points/", {
            "athlete_id": str(athlete.id),
            "action": "import_comments",
            "confirm_replace": "on",
        })
        self.assertEqual(import_denied.status_code, 403)

    def test_focus_point_priority_and_other_labels_are_shared_per_athlete(self):
        owner = get_user_model().objects.create_user(
            username="focus-shared-owner", password="secret", is_staff=True
        )
        editor = get_user_model().objects.create_user(
            username="focus-shared-editor", password="secret", is_staff=True
        )
        athlete = Athlete.objects.create(owner=owner, name="Shared Focus Athlete", birth_year=2000, gender="X")
        CoachSettings.objects.create(user=owner, focus_points_enabled=True)
        self.client.force_login(owner)

        initial = self.client.get(f"/planning/focus-points/?athlete={athlete.id}")
        self.assertContains(initial, "Other 1")
        self.assertContains(initial, "focus-priority-trigger")
        self.assertNotContains(initial, '<select name="priority"', html=False)
        for payload in (
            {"action": "priority", "point_key": "speed", "priority": "1"},
            {"action": "priority", "point_key": "endurance_z1_z3", "priority": "2"},
            {"action": "priority", "point_key": "races_tactics", "priority": "3"},
            {"action": "label", "point_key": "other_1", "custom_label": "Running form"},
        ):
            payload["athlete_id"] = str(athlete.id)
            self.assertEqual(self.client.post("/planning/focus-points/", payload).status_code, 302)

        access = CoachAccess.objects.create(owner=owner, grantee=editor, can_edit=True)
        self.client.force_login(editor)
        session = self.client.session
        session["active_coach_owner_id"] = owner.id
        session.save()
        shared_update = self.client.post("/planning/focus-points/", {
            "athlete_id": str(athlete.id),
            "action": "label",
            "point_key": "other_1",
            "custom_label": "Stride mechanics",
        })
        self.assertEqual(shared_update.status_code, 302)
        shared_priority = self.client.post("/planning/focus-points/", {
            "athlete_id": str(athlete.id),
            "action": "priority",
            "point_key": "injuries",
            "priority": "1",
        })
        self.assertEqual(shared_priority.status_code, 302)

        page = self.client.get(f"/planning/focus-points/?athlete={athlete.id}")
        self.assertContains(page, "Stride mechanics")
        self.assertContains(page, "🥇")
        self.assertContains(page, "🥈")
        self.assertContains(page, "🥉")
        setting = AthleteFocusPoint.objects.get(athlete=athlete, point_key="speed")
        self.assertEqual(setting.priority, 2)
        self.assertEqual(
            AthleteFocusPoint.objects.get(athlete=athlete, point_key="endurance_z1_z3").priority,
            3,
        )
        self.assertIsNone(
            AthleteFocusPoint.objects.get(athlete=athlete, point_key="races_tactics").priority
        )
        self.assertEqual(
            AthleteFocusPoint.objects.get(athlete=athlete, point_key="injuries").priority,
            1,
        )
        label = AthleteFocusPoint.objects.get(athlete=athlete, point_key="other_1")
        self.assertEqual(label.custom_label, "Stride mechanics")

    def test_focus_point_xlsx_import_replaces_only_importing_coach_focus_comments(self):
        coach = get_user_model().objects.create_user(username="xlsx-coach", password="secret", is_staff=True)
        other_coach = get_user_model().objects.create_user(
            username="xlsx-other-coach", password="secret", is_staff=True
        )
        athlete = Athlete.objects.create(owner=coach, name="Cari Hughes", birth_year=2000, gender="X")
        CoachSettings.objects.create(user=coach, focus_points_enabled=True)
        FocusPointComment.objects.create(
            athlete=athlete, coach=coach, point_key="speed", comment="Old speed comment"
        )
        FocusPointComment.objects.create(
            athlete=athlete, coach=coach, point_key="endurance_z1_z3", comment="Old endurance comment"
        )
        FocusPointComment.objects.create(
            athlete=athlete, coach=coach, point_key="speed__plan", comment="Keep the plan comment"
        )
        FocusPointComment.objects.create(
            athlete=athlete, coach=other_coach, point_key="speed", comment="Keep another coach's comment"
        )
        row = ["Cari Hughes", None, None, "Updated speed comment", None, None, None, None, None, None]
        workbook = SimpleUploadedFile(
            "Standard Comments PACE.xlsx", _focus_comments_xlsx([row]),
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        self.client.force_login(coach)

        response = self.client.post("/planning/focus-points/", {
            "athlete_id": str(athlete.id),
            "action": "import_comments",
            "confirm_replace": "on",
            "comments_workbook": workbook,
        })

        self.assertRedirects(
            response,
            f"/planning/focus-points/?athlete={athlete.id}&imported=1&comments=1",
        )
        self.assertTrue(FocusPointComment.objects.filter(
            athlete=athlete, coach=coach, point_key="endurance_z1_z3", comment="Old endurance comment"
        ).exists())
        self.assertTrue(FocusPointComment.objects.filter(
            athlete=athlete, coach=coach, point_key="speed", comment="Updated speed comment"
        ).exists())
        self.assertTrue(FocusPointComment.objects.filter(
            athlete=athlete, coach=coach, point_key="speed__plan", comment="Keep the plan comment"
        ).exists())
        self.assertTrue(FocusPointComment.objects.filter(
            athlete=athlete, coach=other_coach, point_key="speed", comment="Keep another coach's comment"
        ).exists())

    def test_focus_point_xlsx_import_rejects_unmatched_names_without_changing_comments(self):
        coach = get_user_model().objects.create_user(username="xlsx-scope-coach", password="secret", is_staff=True)
        athlete = Athlete.objects.create(owner=coach, name="In Scope", birth_year=2000, gender="X")
        CoachSettings.objects.create(user=coach, focus_points_enabled=True)
        existing = FocusPointComment.objects.create(
            athlete=athlete, coach=coach, point_key="speed", comment="Must remain"
        )
        row = ["Not In Scope", None, None, "New comment", None, None, None, None, None, None]
        workbook = SimpleUploadedFile(
            "comments.xlsx", _focus_comments_xlsx([row]),
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        self.client.force_login(coach)

        response = self.client.post("/planning/focus-points/", {
            "athlete_id": str(athlete.id),
            "action": "import_comments",
            "confirm_replace": "on",
            "comments_workbook": workbook,
        })

        self.assertRedirects(
            response,
            f"/planning/focus-points/?athlete={athlete.id}&import_error=Not+found+among+athletes+you+can+access%3A+Not+In+Scope",
        )
        error_page = self.client.get(response.url)
        self.assertContains(error_page, "Not found among athletes you can access")
        existing.refresh_from_db()
        self.assertEqual(existing.comment, "Must remain")

    def test_detailed_camps_are_coach_configurable(self):
        user = get_user_model().objects.create_user(
            username="camp-settings-coach",
            password="secret",
            is_staff=True,
        )
        self.client.force_login(user)

        dashboard = self.client.get("/")
        self.assertContains(dashboard, "Settings")

        settings_page = self.client.get("/settings/")
        self.assertEqual(settings_page.status_code, 200)
        self.assertContains(settings_page, "Planning Camps")
        self.assertNotContains(settings_page, "Shared coach whereabouts in Year Planner")

        planning_before = self.client.get("/planning/")
        self.assertNotContains(planning_before, "Details Camps")

        response = self.client.post(
            "/settings/",
            {
                "detailed_camps_enabled": "on",
            },
        )
        self.assertRedirects(response, "/settings/")
        saved_settings = CoachSettings.objects.get(user=user)
        self.assertTrue(saved_settings.detailed_camps_enabled)

        planning_after = self.client.get("/planning/")
        self.assertContains(planning_after, "Details Camps")
        self.assertEqual(self.client.get("/planning/detailed-camps/").status_code, 200)

    def test_evaluations_module_can_be_disabled_for_coach_and_athletes(self):
        coach = get_user_model().objects.create_user(
            username="evaluation-toggle-coach", password="secret", is_staff=True
        )
        athlete_user = get_user_model().objects.create_user(
            username="evaltoggleathlete", password="secret"
        )
        Athlete.objects.create(
            owner=coach,
            name="Eval Toggle Athlete",
            birth_year=2000,
            gender="X",
        )

        self.client.force_login(coach)
        settings_page = self.client.get("/settings/")
        self.assertContains(settings_page, "Evaluations")
        self.assertContains(settings_page, "evaluations-enabled")

        response = self.client.post("/settings/", {})
        self.assertRedirects(response, "/settings/")
        self.assertFalse(CoachSettings.objects.get(user=coach).evaluations_enabled)
        self.assertNotContains(self.client.get("/"), "Open evaluations")
        self.assertRedirects(self.client.get("/evaluations/"), "/")

        self.client.force_login(athlete_user)
        self.assertNotContains(self.client.get("/"), "Open evaluations")
        self.assertRedirects(self.client.get("/evaluations/"), "/")

        self.client.force_login(coach)
        response = self.client.post("/settings/", {"evaluations_enabled": "on"})
        self.assertRedirects(response, "/settings/")
        self.assertTrue(CoachSettings.objects.get(user=coach).evaluations_enabled)
        self.assertContains(self.client.get("/"), 'href="/evaluations/"')

    def test_coach_can_toggle_session_km_in_settings(self):
        coach = get_user_model().objects.create_user(
            username="session-km-settings-coach",
            password="secret",
            is_staff=True,
        )
        self.client.force_login(coach)

        settings_page = self.client.get("/settings/")
        self.assertContains(settings_page, "See session km")
        self.assertContains(settings_page, 'name="see_session_km"')
        self.assertContains(settings_page, 'id="see-session-km" name="see_session_km" checked')

        disabled = self.client.post("/settings/", {})
        self.assertRedirects(disabled, "/settings/")
        self.assertFalse(CoachSettings.objects.get(user=coach).see_session_km)

        enabled = self.client.post("/settings/", {"see_session_km": "on"})
        self.assertRedirects(enabled, "/settings/")
        self.assertTrue(CoachSettings.objects.get(user=coach).see_session_km)

    def test_coach_can_select_pause_mode_and_invalid_option_is_rejected(self):
        coach = get_user_model().objects.create_user(
            username="pause-mode-settings-coach",
            password="secret",
            is_staff=True,
        )
        self.client.force_login(coach)

        settings_page = self.client.get("/settings/")
        self.assertContains(settings_page, "P(ause)mode")
        self.assertContains(settings_page, 'name="pause_mode"')
        self.assertContains(settings_page, '<option value="always_static" selected>Static unless &quot;ap&quot;</option>', html=True)
        self.assertContains(settings_page, 'Active unless &quot;pp&quot;')

        response = self.client.post("/settings/", {"pause_mode": "active_unless_pp"})
        self.assertRedirects(response, "/settings/")
        settings = CoachSettings.objects.get(user=coach)
        self.assertEqual(settings.pause_mode, CoachSettings.PAUSE_MODE_ACTIVE_UNLESS_PP)

        invalid = self.client.post("/settings/", {"pause_mode": "unsupported"})
        self.assertRedirects(invalid, "/settings/")
        settings.refresh_from_db()
        self.assertEqual(settings.pause_mode, CoachSettings.PAUSE_MODE_ACTIVE_UNLESS_PP)

    def test_athlete_pause_mode_is_coach_only_and_overrides_coach_default(self):
        coach = get_user_model().objects.create_user(
            username="athlete-pause-mode-coach",
            password="secret",
            is_staff=True,
        )
        athlete = Athlete.objects.create(
            owner=coach,
            name="Athlete pause mode",
            birth_year=2000,
            gender="X",
        )
        coach_settings = CoachSettings.objects.create(
            user=coach,
            pause_mode=CoachSettings.PAUSE_MODE_ALWAYS_STATIC,
        )
        self.client.force_login(coach)

        coach_view = self.client.get(f"/coach/athletes/{athlete.id}/edit/")
        self.assertEqual(coach_view.status_code, 200)
        self.assertContains(coach_view, 'name="pause_mode"')
        self.assertContains(coach_view, '<option value="always_static" selected>Static unless &quot;ap&quot;</option>', html=True)

        response = self.client.post(
            f"/coach/athletes/{athlete.id}/edit/",
            {
                "name": athlete.name,
                "birth_year": athlete.birth_year,
                "gender": athlete.gender,
                "pause_mode": CoachSettings.PAUSE_MODE_ACTIVE_UNLESS_PP,
                "z1_pace": "5:00", "z2_pace": "4:30", "z3_pace": "4:00",
                "z4_pace": "3:40", "z5_pace": "3:20",
            },
        )
        self.assertEqual(response.status_code, 302)
        athlete.refresh_from_db()
        self.assertEqual(athlete.pause_mode, CoachSettings.PAUSE_MODE_ACTIVE_UNLESS_PP)

        # The athlete self-view has no linked account in this legacy fixture;
        # visibility is enforced by the template's ``not self_view`` guard.

    def test_other_coach_cannot_change_owner_settings(self):
        owner = get_user_model().objects.create_user(
            username="settings-owner", password="secret", is_staff=True
        )
        grantee = get_user_model().objects.create_user(
            username="settings-grantee", password="secret", is_staff=True
        )
        CoachAccess.objects.create(owner=owner, grantee=grantee, can_edit=True)
        CoachSettings.objects.create(user=owner, evaluations_enabled=True)

        self.client.force_login(grantee)
        session = self.client.session
        session["active_coach_owner_id"] = owner.id
        session.save()

        settings_page = self.client.get("/settings/")
        self.assertEqual(settings_page.status_code, 200)
        self.assertContains(settings_page, "evaluation-sharing-matrix")
        self.assertContains(settings_page, "settings-grantee")
        self.assertNotContains(settings_page, "Save settings")
        self.assertContains(settings_page, "evaluation-share-")
        self.assertContains(settings_page, "disabled")

        response = self.client.post("/settings/", {"evaluations_enabled": "off"})
        self.assertEqual(response.status_code, 403)
        self.assertTrue(CoachSettings.objects.get(user=owner).evaluations_enabled)

    def test_evaluation_sharing_matrix_limits_shared_coach_views(self):
        owner = get_user_model().objects.create_user(
            username="evaluation-sharing-owner", password="secret", is_staff=True
        )
        grantee = get_user_model().objects.create_user(
            username="evaluation-sharing-grantee", password="secret", is_staff=True
        )
        athlete = Athlete.objects.create(
            owner=owner,
            name="Evaluation Sharing Athlete",
            birth_year=2000,
            gender="X",
        )
        CoachAccess.objects.create(owner=owner, grantee=grantee, can_edit=False)
        CoachSettings.objects.create(user=owner, evaluation_sharing_enabled=True)
        plan = TrainingPlan.objects.create(
            owner=owner,
            name="Evaluation sharing plan",
            plan_kind=TrainingPlan.PLAN_KIND_TRAINER,
        )
        PlanMembership.objects.create(plan=plan, athlete=athlete)
        today = date.today()
        slot = TrainingSlot.objects.create(plan=plan, date=today, slot_index=1)
        slot.segments.create(type="CORE", text="Easy run", order=0)
        AthleteDayCheck.objects.create(
            athlete=athlete,
            date=today,
            slot_index=1,
            status=AthleteDayCheck.STATUS_DONE_AS_PLANNED,
            checked=True,
            rpe=6,
            comment="Good",
            updated_by=athlete.owner,
        )
        AthleteWeekReport.objects.create(athlete=athlete, week_start=today - timedelta(days=today.weekday()))
        AthleteDailyVital.objects.create(athlete=athlete, date=today, sleep_hours=8)

        self.client.force_login(owner)
        settings_page = self.client.get("/settings/")
        self.assertContains(settings_page, "Evaluation sharing")
        self.assertContains(settings_page, "evaluation-sharing-grantee")
        saved = self.client.post(
            "/settings/",
            {
                "evaluations_enabled": "on",
                "evaluation_sharing_enabled": "on",
                f"evaluation-share-{grantee.id}-training": "on",
            },
        )
        self.assertRedirects(saved, "/settings/")
        share = CoachEvaluationSharing.objects.get(owner=owner, grantee=grantee)
        self.assertTrue(share.training)
        self.assertFalse(share.week)
        self.assertFalse(share.vitals)

        self.client.force_login(grantee)
        self.client.post("/", {"coach_view_owner": str(owner.id)})

        ayc = self.client.get(f"/athlete/year/?athlete={athlete.id}&year={today.year}&hide=none")
        self.assertTrue(ayc.context["show_training_reports"])
        self.assertFalse(ayc.context["show_week_reports"])
        self.assertFalse(ayc.context["show_daily_vitals"])

        dco = self.client.get(f"/coach/daily-overview/?date={today.isoformat()}&ok=1")
        self.assertIsNotNone(dco.context["rows"][0]["check1"])
        dco_other = self.client.get("/coach/daily-overview-other/")
        self.assertEqual(dco_other.context["athlete_rows"][0]["pending_count"], 0)

        flex = self.client.get(
            f"/flex-planner/?start={today.isoformat()}&weeks=1&athletes={athlete.id}"
        )
        flex_checks = [
            cell.get("check")
            for week in flex.context["week_rows"]
            for row in week["athlete_rows"]
            for cell in row["am_cells"] + row["pm_cells"]
        ]
        self.assertTrue(any(flex_checks))

    def test_shared_coach_keeps_legacy_evaluation_visibility_until_sharing_is_enabled(self):
        owner = get_user_model().objects.create_user(
            username="legacy-evaluation-owner", password="secret", is_staff=True
        )
        grantee = get_user_model().objects.create_user(
            username="legacy-evaluation-grantee", password="secret", is_staff=True
        )
        athlete = Athlete.objects.create(
            owner=owner,
            name="Legacy Evaluation Athlete",
            birth_year=2000,
            gender="X",
        )
        CoachAccess.objects.create(owner=owner, grantee=grantee, can_edit=False)

        self.client.force_login(grantee)
        self.client.post("/", {"coach_view_owner": str(owner.id)})

        response = self.client.get(
            f"/athlete/year/?athlete={athlete.id}&year={date.today().year}&hide=none"
        )
        self.assertTrue(response.context["show_training_reports"])

    def test_live_training_schedule_sharing_requires_both_coaches(self):
        receiving_coach = get_user_model().objects.create_user(
            username="live-sharing-receiver", password="secret", is_staff=True
        )
        sending_coach = get_user_model().objects.create_user(
            username="live-sharing-sender", password="secret", is_staff=True
        )
        athlete = Athlete.objects.create(
            owner=receiving_coach,
            name="Live Sharing Athlete",
            birth_year=2000,
            gender="X",
        )
        block = AthleteBasePlanningBlock.objects.create(
            athlete=athlete,
            planning_kind=AthleteBasePlanningBlock.KIND_BASE,
            start_month=1,
            start_day=1,
            end_month=12,
            end_day=31,
        )
        slot = AthleteBasePlanningSlot.objects.create(
            block=block,
            weekday=0,
            slot_index=1,
            mode=AthleteBasePlanningSlot.MODE_REST,
        )
        shared_plan = TrainingPlan.objects.create(
            owner=sending_coach,
            name="Sender live schedule",
            plan_kind=TrainingPlan.PLAN_KIND_TRAINER,
        )
        CoachAccess.objects.create(owner=sending_coach, grantee=receiving_coach, can_edit=False)
        CoachSettings.objects.create(user=receiving_coach, live_sharing_training_schedules=True)
        self.client.force_login(receiving_coach)

        before_sender_opt_in = self.client.get(
            f"/planning/base/?athlete={athlete.id}"
        )
        self.assertNotContains(before_sender_opt_in, "Sender live schedule")

        CoachSettings.objects.create(user=sending_coach, live_sharing_training_schedules=True)
        after_both_opt_in = self.client.get(f"/planning/base/?athlete={athlete.id}")
        self.assertContains(after_both_opt_in, "Sender live schedule")

        saved = self.client.post(
            "/planning/base/",
            {
                "athlete_id": str(athlete.id),
                "action": "autosave_slot",
                "slot_id": str(slot.id),
                "mode": AthleteBasePlanningSlot.MODE_TRAINER,
                "trainer_plan": str(shared_plan.id),
            },
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(saved.status_code, 200)
        future_block = AthleteBasePlanningBlock.objects.get(
            athlete=athlete,
            effective_from=date.today() + timedelta(days=1),
        )
        future_slot = future_block.slots.get(weekday=0, slot_index=1)
        self.assertEqual(future_slot.trainer_plan_id, shared_plan.id)
        slot.refresh_from_db()
        self.assertIsNone(slot.trainer_plan_id)

        CoachSettings.objects.get(user=sending_coach).delete()
        hidden_after_opt_out = self.client.get(f"/planning/base/?athlete={athlete.id}")
        self.assertNotContains(hidden_after_opt_out, "Sender live schedule")

    def test_athlete_ayc_still_shows_assigned_shared_trainer_schedule(self):
        receiving_coach = get_user_model().objects.create_user(
            username="ayc-sharing-receiver", password="secret", is_staff=True
        )
        sending_coach = get_user_model().objects.create_user(
            username="ayc-sharing-sender", password="secret", is_staff=True
        )
        athlete_user = get_user_model().objects.create_user(
            username="Assigned Shared Athlete", password="secret"
        )
        athlete = Athlete.objects.create(
            owner=receiving_coach,
            name="Assigned Shared Athlete",
            birth_year=2000,
            gender="X",
        )
        shared_plan = TrainingPlan.objects.create(
            owner=sending_coach,
            name="Assigned shared schedule",
            plan_kind=TrainingPlan.PLAN_KIND_TRAINER,
        )
        PlanMembership.objects.create(plan=shared_plan, athlete=athlete)
        day = date.today()
        source_slot = TrainingSlot.objects.create(
            plan=shared_plan,
            date=day,
            slot_index=1,
        )
        source_slot.segments.create(type="CORE", text="Assigned group session", order=0)
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
            weekday=day.weekday(),
            slot_index=1,
            mode=AthleteBasePlanningSlot.MODE_TRAINER,
            trainer_plan=shared_plan,
        )
        CoachAccess.objects.create(owner=sending_coach, grantee=receiving_coach, can_edit=False)
        CoachSettings.objects.create(user=receiving_coach, live_sharing_training_schedules=True)
        CoachSettings.objects.create(user=sending_coach, live_sharing_training_schedules=True)

        self.client.force_login(athlete_user)
        response = self.client.get(f"/athlete/year/?year={day.year}&hide=none")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Assigned group session")

        base_planning = self.client.get(f"/planning/base/?athlete={athlete.id}")
        self.assertEqual(base_planning.status_code, 200)
        self.assertContains(base_planning, "Assigned shared schedule")
        self.assertNotContains(base_planning, "Shared schedule unavailable")

    def test_detailed_camps_group_athletes_and_coaches_by_name(self):
        coach = get_user_model().objects.create_user(
            username="camp-overview-coach",
            password="secret",
            is_staff=True,
        )
        accessible_coach = get_user_model().objects.create_user(
            username="camp-accessible-coach",
            password="secret",
            is_staff=True,
        )
        CoachAccess.objects.create(owner=accessible_coach, grantee=coach, can_edit=True)
        CoachSettings.objects.create(user=coach, detailed_camps_enabled=True)
        first_athlete = Athlete.objects.create(
            owner=coach,
            name="Camp Athlete One",
            birth_year=2000,
            gender="X",
        )
        second_athlete = Athlete.objects.create(
            owner=coach,
            name="Camp Athlete Two",
            birth_year=2000,
            gender="X",
        )
        first_range = YearPlannerWhereabout.objects.create(
            owner=coach,
            athlete=first_athlete,
            start_date=date(2026, 10, 7),
            end_date=date(2026, 11, 4),
            whereabouts_type="camp",
            note="Font R",
        )
        YearPlannerWhereabout.objects.create(
            owner=coach,
            athlete=second_athlete,
            start_date=date(2026, 10, 7),
            end_date=date(2026, 11, 5),
            whereabouts_type="camp",
            note=" font   r ",
        )
        YearPlannerWhereabout.objects.create(
            owner=coach,
            start_date=date(2026, 10, 6),
            end_date=date(2026, 11, 5),
            whereabouts_type="camp",
            note="FONT R",
        )
        YearPlannerWhereabout.objects.create(
            owner=accessible_coach,
            start_date=date(2026, 10, 8),
            end_date=date(2026, 11, 3),
            whereabouts_type="camp",
            note="Font R",
        )
        self.client.force_login(coach)

        overview = self.client.get("/planning/detailed-camps/")
        self.assertEqual(overview.status_code, 200)
        self.assertEqual(overview.context["camps"][0]["participant_count"], 4)
        self.assertContains(overview, "Font R")

        detail = self.client.get("/planning/detailed-camps/camp/?camp=font+r")
        self.assertEqual(detail.status_code, 200)
        self.assertContains(detail, "Camp Athlete One")
        self.assertContains(detail, "Camp Athlete Two")
        self.assertContains(detail, "camp-overview-coach")
        self.assertContains(detail, "camp-accessible-coach")
        self.assertContains(detail, "05 Nov 2026")
        self.assertContains(detail, "data-camp-copy")
        self.assertContains(detail, "data-camp-sort")

        saved = self.client.post("/planning/detailed-camps/camp/?camp=font+r", {
            "participant_type": "Athlete",
            "participant_id": first_athlete.id,
            "arrival_date": "2026-10-08",
            "departure_date": "2026-11-06",
            "arrival_flight_number": "KL1234",
            "arrival_flight_time": "10:25",
            "departure_flight_number": "KL4321",
            "departure_flight_time": "18:45",
            "rental_car_info": "Hertz 123",
            "accommodation": "Hotel Font",
        }, HTTP_X_REQUESTED_WITH="XMLHttpRequest")
        self.assertEqual(saved.status_code, 200)
        self.assertEqual(saved.json(), {"ok": True})
        first_range.refresh_from_db()
        self.assertEqual(first_range.start_date, date(2026, 10, 8))
        self.assertEqual(first_range.end_date, date(2026, 11, 6))
        self.assertEqual(first_range.arrival_flight_number, "KL1234")
        self.assertEqual(first_range.arrival_flight_time.isoformat(), "10:25:00")
        self.assertEqual(first_range.departure_flight_number, "KL4321")
        self.assertEqual(first_range.departure_flight_time.isoformat(), "18:45:00")
        self.assertEqual(first_range.rental_car_info, "Hertz 123")
        self.assertEqual(first_range.accommodation, "Hotel Font")

        deleted = self.client.post("/planning/detailed-camps/camp/?camp=font+r", {
            "action": "delete_participant",
            "participant_type": "Athlete",
            "participant_id": first_athlete.id,
        })
        self.assertRedirects(deleted, "/planning/detailed-camps/camp/?camp=font+r")
        self.assertFalse(YearPlannerWhereabout.objects.filter(id=first_range.id).exists())
        self.assertTrue(YearPlannerWhereabout.objects.filter(owner=coach, athlete=second_athlete, note=" font   r ").exists())

    def test_coach_can_rename_camp_across_all_participants(self):
        coach = get_user_model().objects.create_user(username="camp-rename-coach", password="secret", is_staff=True)
        shared_coach = get_user_model().objects.create_user(username="camp-rename-shared", password="secret", is_staff=True)
        CoachAccess.objects.create(owner=shared_coach, grantee=coach, can_edit=True)
        CoachSettings.objects.create(user=coach, detailed_camps_enabled=True)
        athlete = Athlete.objects.create(owner=coach, name="Rename Camp Athlete", birth_year=2000, gender="X")
        own_range = YearPlannerWhereabout.objects.create(
            owner=coach, athlete=athlete, start_date=date(2026, 10, 7), end_date=date(2026, 10, 10),
            whereabouts_type="camp", note="Autumn Camp",
        )
        coach_range = YearPlannerWhereabout.objects.create(
            owner=shared_coach, start_date=date(2026, 10, 8), end_date=date(2026, 10, 11),
            whereabouts_type="camp", note="autumn camp",
        )
        self.client.force_login(coach)

        detail = self.client.get("/planning/detailed-camps/camp/?camp=autumn+camp")
        self.assertEqual(detail.status_code, 200)
        self.assertContains(detail, "data-camp-title-trigger")

        renamed = self.client.post("/planning/detailed-camps/camp/?camp=autumn+camp", {
            "action": "rename_camp", "name": "  Spring   Training Camp  ",
        })
        self.assertRedirects(renamed, "/planning/detailed-camps/camp/?camp=spring+training+camp&saved=1")
        own_range.refresh_from_db()
        coach_range.refresh_from_db()
        self.assertEqual(own_range.note, "Spring Training Camp")
        self.assertEqual(coach_range.note, "Spring Training Camp")

    def test_camp_rename_requires_edit_access_to_every_participant(self):
        coach = get_user_model().objects.create_user(username="camp-rename-limited", password="secret", is_staff=True)
        view_only_coach = get_user_model().objects.create_user(username="camp-rename-view", password="secret", is_staff=True)
        CoachAccess.objects.create(owner=view_only_coach, grantee=coach, can_edit=False)
        CoachSettings.objects.create(user=coach, detailed_camps_enabled=True)
        athlete = Athlete.objects.create(owner=coach, name="Limited Camp Athlete", birth_year=2000, gender="X")
        YearPlannerWhereabout.objects.create(
            owner=coach, athlete=athlete, start_date=date(2026, 10, 7), end_date=date(2026, 10, 10),
            whereabouts_type="camp", note="Shared Camp",
        )
        view_only_range = YearPlannerWhereabout.objects.create(
            owner=view_only_coach, start_date=date(2026, 10, 8), end_date=date(2026, 10, 11),
            whereabouts_type="camp", note="Shared Camp",
        )
        self.client.force_login(coach)

        detail = self.client.get("/planning/detailed-camps/camp/?camp=shared+camp")
        self.assertEqual(detail.status_code, 200)
        self.assertNotContains(detail, '<button type="button" class="camp-title-edit-trigger"')
        renamed = self.client.post("/planning/detailed-camps/camp/?camp=shared+camp", {
            "action": "rename_camp", "name": "Renamed Camp",
        })
        self.assertEqual(renamed.status_code, 403)
        view_only_range.refresh_from_db()
        self.assertEqual(view_only_range.note, "Shared Camp")

    def test_athlete_can_edit_own_details_camp_when_whereabouts_enabled(self):
        coach = get_user_model().objects.create_user(username="camp-athlete-coach", password="secret", is_staff=True)
        athlete = Athlete.objects.create(
            owner=coach, name="Camp Editable Athlete", birth_year=2000, gender="X",
            year_planner_whereabouts_enabled=True,
        )
        other = Athlete.objects.create(owner=coach, name="Camp Other Athlete", birth_year=2000, gender="X")
        own_range = YearPlannerWhereabout.objects.create(
            owner=coach, athlete=athlete, start_date=date(2026, 10, 7), end_date=date(2026, 10, 10),
            whereabouts_type="camp", note="Athlete Camp",
        )
        YearPlannerWhereabout.objects.create(
            owner=coach, athlete=other, start_date=date(2026, 10, 7), end_date=date(2026, 10, 10),
            whereabouts_type="camp", note="Athlete Camp",
        )
        athlete_user = get_user_model().objects.create_user(username="Camp Editable Athlete", password="secret")
        self.client.force_login(athlete_user)

        detail = self.client.get("/planning/detailed-camps/camp/?camp=athlete+camp")
        self.assertEqual(detail.status_code, 200)
        self.assertContains(detail, 'name="arrival_date"')
        self.assertNotContains(detail, 'name="action" value="delete_participant"')

        saved = self.client.post("/planning/detailed-camps/camp/?camp=athlete+camp", {
            "participant_type": "Athlete", "participant_id": athlete.id,
            "arrival_date": "2026-10-08", "departure_date": "2026-10-11",
            "arrival_flight_number": "KL123", "arrival_flight_time": "10:25",
            "departure_flight_number": "KL321", "departure_flight_time": "18:45",
            "rental_car_info": "Rental", "accommodation": "Hotel",
        }, HTTP_X_REQUESTED_WITH="XMLHttpRequest")
        self.assertEqual(saved.status_code, 200)
        self.assertEqual(saved.json(), {"ok": True})
        own_range.refresh_from_db()
        self.assertEqual(own_range.start_date, date(2026, 10, 8))
        self.assertEqual(own_range.end_date, date(2026, 10, 11))
        self.assertEqual(own_range.arrival_flight_number, "KL123")

        deleted = self.client.post("/planning/detailed-camps/camp/?camp=athlete+camp", {
            "action": "delete_participant", "participant_type": "Athlete", "participant_id": athlete.id,
        })
        self.assertEqual(deleted.status_code, 403)

    def test_create_camp_and_add_athletes_writes_year_planner_whereabouts(self):
        coach = get_user_model().objects.create_user(username="camp-create-coach", password="secret", is_staff=True)
        CoachSettings.objects.create(user=coach, detailed_camps_enabled=True)
        first = Athlete.objects.create(owner=coach, name="First Camp Athlete", birth_year=2000, gender="X")
        second = Athlete.objects.create(owner=coach, name="Second Camp Athlete", birth_year=2000, gender="X")
        self.client.force_login(coach)

        created = self.client.post("/planning/detailed-camps/", {
            "action": "create_camp",
            "name": "Training Camp",
            "start_date": "2026-10-07",
            "end_date": "2026-11-04",
            "athlete_ids": [str(first.id)],
        })
        self.assertRedirects(created, "/planning/detailed-camps/camp/?camp=training+camp")
        self.assertTrue(YearPlannerWhereabout.objects.filter(owner=coach, athlete=first, note="Training Camp").exists())

        added = self.client.post("/planning/detailed-camps/camp/?camp=training+camp", {
            "action": "add_participants",
            "athlete_ids": [str(second.id)],
            "coach_ids": [str(coach.id)],
        })
        self.assertRedirects(added, "/planning/detailed-camps/camp/?camp=training+camp")
        second_range = YearPlannerWhereabout.objects.get(owner=coach, athlete=second, note="Training Camp")
        self.assertEqual(second_range.start_date, date(2026, 10, 7))
        self.assertEqual(second_range.end_date, date(2026, 11, 4))
        self.assertTrue(YearPlannerWhereabout.objects.filter(
            owner=coach,
            athlete__isnull=True,
            whereabouts_type="camp",
            note="Training Camp",
        ).exists())


class PolarPlanMismatchTests(TestCase):
    def test_v4_samples_are_normalized_for_matching(self):
        exercise = _polar_v4_normalize_exercise_samples({
            "distanceMeters": 1200,
            "durationMillis": 120000,
            "samples": {
                "samples": [
                    {"type": "SPEED", "intervalMillis": 1000, "values": [10, 12]},
                    {"type": "HEART_RATE", "intervalMillis": 1000, "values": [145, 150]},
                ],
            },
        })

        self.assertEqual([sample["sample_type"] for sample in exercise["samples"]], ["1", "0"])
        self.assertEqual(exercise["samples"][0]["recording_rate"], 1.0)
        activities = _polar_v4_sample_activities([{
            "identifier": {"id": "session-1"},
            "sport": "RUNNING",
            "exercises": [exercise],
        }])
        self.assertEqual(len(activities), 1)
        self.assertEqual(activities[0]["distance_m"], 1200)
        self.assertEqual(activities[0]["duration_seconds"], 120)
        self.assertIn("samples", activities[0]["raw"])

    def test_v4_auto_laps_are_used_when_manual_laps_are_absent(self):
        session = {
            "id": "auto-session",
            "distanceMeters": 3200,
            "durationMillis": 1200000,
            "exercises": [{
                "laps": {
                    "autoLaps": [
                        {"distanceMeters": 1000, "durationMillis": 360000},
                        {"distanceMeters": 1000, "durationMillis": 370000},
                        {"distanceMeters": 1000, "durationMillis": 380000},
                    ]
                }
            }],
        }

        suggestion = _build_polar_v4_lap_suggestion("3km z2", [session])

        self.assertIsNotNone(suggestion)
        self.assertEqual(suggestion["mode"], "polar_v4_auto_laps")
        self.assertEqual(suggestion["lap_source"], "automatic")
        self.assertEqual(len(suggestion["splits"]), 3)
        self.assertEqual(suggestion["confidence"], 0.65)

    def test_type_a_recognises_timed_blocks_with_short_recoveries(self):
        description = type_a_description([
            {"distanceMeters": 1674.6, "durationMillis": 600282},
            {"distanceMeters": 147.2, "durationMillis": 90125},
            {"distanceMeters": 1803.2, "durationMillis": 600375},
            {"distanceMeters": 154.9, "durationMillis": 90000},
            {"distanceMeters": 2938.2, "durationMillis": 900501},
            {"distanceMeters": 168.3, "durationMillis": 90000},
        ])
        self.assertIn("Main: 10'", description)
        self.assertIn("10'", description)
        self.assertIn("15'", description)
        self.assertIn("recovery avg 90 s", description)

    def test_type_a_training_fields_strip_summary_only_text(self):
        fields = type_a_training_fields(
            "WU: 1650 m Z1 · Main: 10' Z1 (5:58/km) + 10' Z1 (5:33/km), recovery avg 90 s · CD: none"
        )
        self.assertEqual(fields["wu"], "1650 m Z1")
        self.assertEqual(fields["main"], "10' Z1 (5:58/km) + 10' Z1 (5:33/km)")
        self.assertEqual(fields["cd"], "")
        self.assertEqual(type_a_training_fields("Continuous run: 12.4 km Z1 (5:20/km)")["main"], "12.4 km Z1 (5:20/km)")

    def test_v4_manual_laps_remain_preferred_over_auto_laps(self):
        session = {
            "id": "mixed-session",
            "exercises": [{
                "laps": {
                    "laps": [{"distanceMeters": 400, "durationMillis": 90000}],
                    "autoLaps": [{"distanceMeters": 1000, "durationMillis": 360000}],
                }
            }],
        }

        suggestion = _build_polar_v4_lap_suggestion("400m z3", [session])

        self.assertEqual(suggestion["mode"], "polar_v4_laps")
        self.assertEqual(suggestion["lap_source"], "manual")
        self.assertEqual(len(suggestion["splits"]), 1)

    def test_planned_interval_structure_keeps_multiple_simple_repeat_blocks(self):
        structure = _planned_interval_structure("7*1000m z3 // 3*500m z3")

        self.assertEqual(structure["pattern_type"], "distance")
        self.assertEqual(structure["reps_total"], 10)
        self.assertEqual(structure["pattern_m"], ([1000] * 7) + ([500] * 3))
        self.assertEqual(structure["core_distance_m"], 8500)

    def test_planned_pause_duration_uses_ten_minute_cutoff_and_meter_pause_is_not_time(self):
        self.assertEqual(_planned_interval_structure("3*1000m z2 p1")["pause_s"], 60)
        self.assertEqual(_planned_interval_structure("3*1000m z2 p=11")["pause_s"], 11)
        self.assertEqual(_planned_interval_structure("3*1000m z2 p=50m")["pause_s"], 0)

    def test_planned_interval_structure_accepts_extra_repeat_asterisk(self):
        structure = _planned_interval_structure("7*1000m z3 // 3**500m z3")

        self.assertEqual(structure["reps_total"], 10)
        self.assertEqual(structure["pattern_m"], ([1000] * 7) + ([500] * 3))

    def test_planned_interval_structure_keeps_bookends_around_multiple_repeat_blocks(self):
        structure = _planned_interval_structure("2000m z1 // 7*1000m z3 // 3*500m z3 // 1000m z1")

        self.assertEqual(structure["pattern_m"], ([1000] * 7) + ([500] * 3))
        self.assertEqual(structure["lead_in_m"], 2000)
        self.assertEqual(structure["lead_out_m"], 1000)

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
        self.assertNotIn("access_token", connection.raw_token_response)

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

    def test_ayc_suggest_input_shows_placeholder_without_watch_fetch(self):
        source = get_template("core/athlete_year_calendar.html").template.source
        self.assertIn('id="suggestInputBtn"', source)
        self.assertIn('>Polar A<', source)
        self.assertIn('>Polar B<', source)
        self.assertIn('>Garmin C<', source)
        self.assertIn('id="suggestInputPlaceholder"', source)
        self.assertIn('id="suggestInputPlaceholderClose"', source)
        self.assertIn('id="suggestInputPlaceholderBody"', source)
        self.assertIn('addEventListener("click", showSuggestInputPlaceholder)', source)
        self.assertIn("/integrations/polar/type-a-ayc/", source)
        self.assertNotIn("Suggest alternative plan", source)
        self.assertIn('id="aypWatchResultSection"', source)
        self.assertIn('id="deleteWatchInputBtn"', source)

    def test_planner_whereabout_dots_include_overlapping_types(self):
        coach = get_user_model().objects.create_user(
            username="whereabout-dot-coach", password="secret", is_staff=True
        )
        athlete = Athlete.objects.create(
            owner=coach, name="Whereabout Dot Athlete", birth_year=2000, gender="X"
        )
        YearPlannerWhereabout.objects.create(
            owner=coach, athlete=athlete, start_date=date(2026, 10, 7), end_date=date(2026, 10, 9),
            whereabouts_type="camp", note="Camp",
        )
        YearPlannerWhereabout.objects.create(
            owner=coach, athlete=athlete, start_date=date(2026, 10, 8), end_date=date(2026, 10, 8),
            whereabouts_type="travel", note="Travel",
        )
        dots = _whereabout_dots(coach, [athlete.id], date(2026, 10, 7), date(2026, 10, 10))
        self.assertEqual([item["type"] for item in dots[(athlete.id, date(2026, 10, 8))]], ["camp", "travel"])
        self.assertEqual([item["type"] for item in dots[(athlete.id, date(2026, 10, 7))]], ["camp"])

    def test_planner_whereabout_dots_do_not_leak_between_athletes_or_scopes(self):
        coach = get_user_model().objects.create_user(
            username="whereabout-isolation-coach", password="secret", is_staff=True
        )
        robin = Athlete.objects.create(owner=coach, name="Robin", birth_year=2000, gender="X")
        sara = Athlete.objects.create(owner=coach, name="Sara", birth_year=2000, gender="X")
        day = date(2026, 10, 27)
        YearPlannerWhereabout.objects.create(
            owner=coach, athlete=sara, start_date=day, end_date=day,
            whereabouts_type="camp", note="Sara camp",
        )
        YearPlannerWhereabout.objects.create(
            owner=coach, start_date=day, end_date=day,
            whereabouts_type="travel", note="Coach travel",
        )

        robin_dots = _whereabout_dots(coach, [robin.id], day, day + timedelta(days=1))
        both_dots = _whereabout_dots(coach, [robin.id, sara.id], day, day + timedelta(days=1))

        self.assertNotIn((robin.id, day), robin_dots)
        self.assertNotIn((robin.id, day), both_dots)
        self.assertEqual([item["type"] for item in both_dots[(sara.id, day)]], ["camp"])

        self.client.force_login(coach)
        flex_page = self.client.get(
            f"/flex-planner/?start={day.isoformat()}&weeks=1&athletes={robin.id}"
        )
        flex_cell = next(
            cell
            for week in flex_page.context["week_rows"]
            for cell in week["athlete_rows"][0]["am_cells"]
            if cell["day"] == day
        )
        self.assertEqual(flex_cell["whereabouts"], [])

        ayc_page = self.client.get(f"/athlete/year/?year={day.year}&athlete={robin.id}&hide=none")
        ayc_cell = next(
            cell
            for week in ayc_page.context["week_rows"]
            for cell in week["cells1"]
            if cell["day"] == day
        )
        self.assertEqual(ayc_cell["whereabouts"], [])

    def test_ayc_type_a_endpoint_returns_polar_integration_output(self):
        coach = get_user_model().objects.create_user(
            username="Wilbert van Vliet", password="secret", is_staff=True
        )
        athlete = Athlete.objects.create(owner=coach, name="Wilbert van Vliet", birth_year=1980, gender="M")
        PolarConnection.objects.create(user=coach, member_id="type-a-ayc-member", v4_access_token="token")
        self.client.force_login(coach)
        session = {
            "startTime": "2026-10-22T10:00:00",
            "distanceMeters": 3800,
            "durationMillis": 1200000,
            "exercises": [{
                "distanceMeters": 3800,
                "durationMillis": 1200000,
                "sport": {"id": "1"},
                "laps": {"laps": [{"distanceMeters": 3800, "durationMillis": 1200000}]},
            }],
        }
        with patch("core.views.coach._polar_v4_sessions_for_day", return_value=([session], "")):
            response = self.client.get(
                f"/integrations/polar/type-a-ayc/?athlete={athlete.id}&date=2026-10-22"
            )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["ok"])
        self.assertEqual(response.json()["results"][0]["parts"][0]["description_label"], "Generated description")

    def test_ayc_watch_c_uses_only_selected_athletes_saved_garmin_laps(self):
        from core.models import GarminActivity

        coach = get_user_model().objects.create_user(
            username="garmin-watch-c-coach", password="secret", is_staff=True
        )
        athlete = Athlete.objects.create(owner=coach, name="Garmin Athlete", birth_year=1980, gender="M")
        other = Athlete.objects.create(owner=coach, name="Other Garmin Athlete", birth_year=1981, gender="M")
        activity_date = date(2026, 10, 22)
        activity_start = timezone.make_aware(datetime.combine(activity_date, time(9)))
        parsed_data = {
            "session": {"total_distance": 3000, "total_elapsed_time": 1200},
            "total_distance_m": 3000,
            "total_elapsed_s": 1200,
            "laps": [
                {"distance": 500, "elapsed_time": 200, "avg_heart_rate": 150},
                {"distance": 500, "elapsed_time": 200, "avg_heart_rate": 151},
                {"distance": 500, "elapsed_time": 200, "avg_heart_rate": 152},
                {"distance": 500, "elapsed_time": 200, "avg_heart_rate": 153},
                {"distance": 500, "elapsed_time": 200, "avg_heart_rate": 154},
                {"distance": 500, "elapsed_time": 200, "avg_heart_rate": 155},
            ],
        }
        GarminActivity.objects.create(
            athlete=athlete, activity_start=activity_start, original_filename="athlete.fit",
            file_hash="a" * 64, raw_file=b"fit", parsed_data=parsed_data,
        )
        GarminActivity.objects.create(
            athlete=other, activity_start=activity_start, original_filename="other.fit",
            file_hash="b" * 64, raw_file=b"fit", parsed_data=parsed_data,
        )
        self.client.force_login(coach)
        mock_results = [{"parts": [{"watch_loads": []}]}]
        with patch("core.views.polar_raw.translate_model_b", return_value=mock_results) as translate:
            response = self.client.get(
                f"/integrations/garmin/type-c-ayc/?athlete={athlete.id}&date={activity_date.isoformat()}"
            )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["ok"])
        self.assertEqual(response.json()["model"], "C")
        self.assertEqual(len(translate.call_args.args[0]), 1)
        self.assertEqual(translate.call_args.args[0][0]["name"], "athlete.fit")
        laps = translate.call_args.args[0][0]["laps"]["laps"]
        self.assertEqual(len(laps), 6)
        self.assertEqual(laps[0]["distanceMeters"], 500)
        self.assertEqual(laps[0]["durationMillis"], 200000)
        self.assertEqual(len(response.json()["results"][0]["parts"][0]["watch_loads"]), 6)

    def test_ayc_watch_c_rejects_garmin_files_for_unavailable_athletes(self):
        coach = get_user_model().objects.create_user(
            username="garmin-watch-c-access", password="secret", is_staff=True
        )
        other_coach = get_user_model().objects.create_user(
            username="garmin-watch-c-other", password="secret", is_staff=True
        )
        athlete = Athlete.objects.create(owner=other_coach, name="Private Athlete", birth_year=1980, gender="M")
        self.client.force_login(coach)
        response = self.client.get(
            f"/integrations/garmin/type-c-ayc/?athlete={athlete.id}&date=2026-10-22"
        )
        self.assertEqual(response.status_code, 404)

    def test_ayc_watch_c_does_not_save_warmup_loads_when_model_b_says_none(self):
        from core.models import GarminActivity

        coach = get_user_model().objects.create_user(
            username="garmin-watch-c-no-wu", password="secret", is_staff=True
        )
        athlete = Athlete.objects.create(owner=coach, name="No Warmup Athlete", birth_year=1980, gender="M")
        activity_date = date(2026, 10, 22)
        GarminActivity.objects.create(
            athlete=athlete,
            activity_start=timezone.make_aware(datetime.combine(activity_date, time(9))),
            original_filename="no-warmup.fit",
            file_hash="c" * 64,
            raw_file=b"fit",
            parsed_data={
                "session": {"total_distance": 2000, "total_elapsed_time": 900},
                "laps": [{"distance": 1000, "elapsed_time": 500}, {"distance": 1000, "elapsed_time": 400}],
            },
        )
        self.client.force_login(coach)
        translated = [{"parts": [{"training_fields": {"wu": "", "main": "2x1000m Z2", "cd": ""}}]}]
        inferred_loads = [
            {"segment": "WU", "zone": "1", "meters": 1000, "seconds": 500},
            {"segment": "CORE", "zone": "2", "meters": 1000, "seconds": 400},
        ]
        with (
            patch("core.views.polar_raw.translate_model_b", return_value=translated),
            patch("core.views.polar_raw.type_a_watch_loads", return_value=inferred_loads),
        ):
            response = self.client.get(
                f"/integrations/garmin/type-c-ayc/?athlete={athlete.id}&date={activity_date.isoformat()}"
            )
        self.assertEqual(response.status_code, 200)
        saved_loads = response.json()["results"][0]["parts"][0]["watch_loads"]
        self.assertEqual([load["segment"] for load in saved_loads], ["CORE", "CORE"])

    def test_ayc_watch_c_merges_same_distance_zone_change_into_one_series(self):
        from core.models import GarminActivity

        coach = get_user_model().objects.create_user(
            username="garmin-watch-c-one-series", password="secret", is_staff=True
        )
        athlete = Athlete.objects.create(owner=coach, name="One Series Athlete", birth_year=1980, gender="M")
        activity_date = date(2026, 10, 13)
        GarminActivity.objects.create(
            athlete=athlete,
            activity_start=timezone.make_aware(datetime.combine(activity_date, time(19))),
            original_filename="one-series.fit",
            file_hash="d" * 64,
            raw_file=b"fit",
            parsed_data={
                "session": {"total_distance": 7100, "total_elapsed_time": 2500},
                "laps": [{"distance": 1000, "elapsed_time": 250} for _ in range(12)],
            },
        )
        self.client.force_login(coach)
        old_main = "3×1000 m Z2 (4:20) p20 + 1000 m Z3 (4:09) p30 + 1000 m Z3 (3:49) p10"
        translated = [{"parts": [{
            "description": f"WU: none · Main: {old_main} · CD: 1700 m Z1",
            "training_fields": {"wu": "", "main": old_main, "cd": "1700 m Z1"},
        }]}]
        laps = [
            {"segment": "CORE", "zone": "2", "meters": 1010, "seconds": 268.155},
            {"segment": "CORE", "zone": "1", "meters": 20, "seconds": 119.124},
            {"segment": "CORE", "zone": "2", "meters": 1000, "seconds": 260.334},
            {"segment": "CORE", "zone": "1", "meters": 40, "seconds": 119.8},
            {"segment": "CORE", "zone": "2", "meters": 1000, "seconds": 256.66},
            {"segment": "CORE", "zone": "1", "meters": 20, "seconds": 130.693},
            {"segment": "CORE", "zone": "3", "meters": 990, "seconds": 246.038},
            {"segment": "CORE", "zone": "1", "meters": 30, "seconds": 141.142},
            {"segment": "CORE", "zone": "3", "meters": 1000, "seconds": 229.244},
            {"segment": "CORE", "zone": "1", "meters": 290, "seconds": 141.277},
            {"segment": "CD", "zone": "1", "meters": 1600, "seconds": 497.159},
            {"segment": "CD", "zone": "1", "meters": 100, "seconds": 134.201},
        ]
        with (
            patch("core.views.polar_raw.translate_model_b", return_value=translated),
            patch("core.views.polar_raw.type_a_watch_loads", return_value=laps),
        ):
            response = self.client.get(
                f"/integrations/garmin/type-c-ayc/?athlete={athlete.id}&date={activity_date.isoformat()}"
            )
        self.assertEqual(response.status_code, 200)
        part = response.json()["results"][0]["parts"][0]
        self.assertEqual(part["training_fields"]["main"], "5×1000 m Z2>Z3 (4:12)")
        self.assertEqual(part["description"], "WU: none · Main: 5×1000 m Z2>Z3 (4:12) · CD: 1700 m Z1")

    def test_ayc_watch_c_orders_main_segments_chronologically_from_laps(self):
        from core.models import GarminActivity

        coach = get_user_model().objects.create_user(
            username="garmin-watch-c-chronology", password="secret", is_staff=True
        )
        athlete = Athlete.objects.create(owner=coach, name="Chronology Athlete", birth_year=1980, gender="M")
        activity_date = date(2026, 10, 29)
        GarminActivity.objects.create(
            athlete=athlete,
            activity_start=timezone.make_aware(datetime.combine(activity_date, time(19))),
            original_filename="chronology.fit",
            file_hash="e" * 64,
            raw_file=b"fit",
            parsed_data={
                "session": {"total_distance": 7100, "total_elapsed_time": 2500},
                "laps": [{"distance": 1000, "elapsed_time": 250} for _ in range(8)],
            },
        )
        self.client.force_login(coach)
        old_main = "950 m Z4 (3:47) p280 + 800 m Z5 (3:12) + 1200 m Z2 (4:30) p50"
        translated = [{"parts": [{
            "description": f"WU: none · Main: {old_main} · CD: 1700 m Z1",
            "training_fields": {"wu": "", "main": old_main, "cd": "1700 m Z1"},
        }]}]
        laps = [
            {"segment": "CORE", "zone": "2", "meters": 1210, "seconds": 268.155},
            {"segment": "CORE", "zone": "1", "meters": 20, "seconds": 119.124},
            {"segment": "CORE", "zone": "2", "meters": 1200, "seconds": 323.779},
            {"segment": "CORE", "zone": "1", "meters": 50, "seconds": 280.972},
            {"segment": "CORE", "zone": "4", "meters": 970, "seconds": 219.945},
            {"segment": "CORE", "zone": "1", "meters": 1130, "seconds": 430.593},
            {"segment": "CORE", "zone": "1", "meters": 40, "seconds": 326.383},
            {"segment": "CORE", "zone": "5", "meters": 800, "seconds": 153.32},
            {"segment": "CORE", "zone": "1", "meters": 50, "seconds": 277.232},
            {"segment": "CD", "zone": "1", "meters": 1600, "seconds": 492.393},
        ]
        with (
            patch("core.views.polar_raw.translate_model_b", return_value=translated),
            patch("core.views.polar_raw.type_a_watch_loads", return_value=laps),
        ):
            response = self.client.get(
                f"/integrations/garmin/type-c-ayc/?athlete={athlete.id}&date={activity_date.isoformat()}"
            )
        self.assertEqual(response.status_code, 200)
        part = response.json()["results"][0]["parts"][0]
        expected_main = "2×1200 m Z2 (4:30) p50 + 950 m Z4 (3:47) p280 + 800 m Z5 (3:12)"
        self.assertEqual(part["training_fields"]["main"], expected_main)
        self.assertEqual(part["description"], f"WU: none · Main: {expected_main} · CD: 1700 m Z1")

    def test_ayc_watch_c_restores_first_rep_zone_range_and_removes_cd_overlap(self):
        from core.models import GarminActivity

        coach = get_user_model().objects.create_user(
            username="garmin-watch-c-first-rep", password="secret", is_staff=True
        )
        athlete = Athlete.objects.create(owner=coach, name="First Rep Athlete", birth_year=1980, gender="M")
        activity_date = date(2026, 10, 20)
        GarminActivity.objects.create(
            athlete=athlete,
            activity_start=timezone.make_aware(datetime.combine(activity_date, time(19))),
            original_filename="first-rep.fit",
            file_hash="f" * 64,
            raw_file=b"fit",
            parsed_data={
                "session": {"total_distance": 7050, "total_elapsed_time": 2700},
                "laps": [{"distance": 1200, "elapsed_time": 270} for _ in range(8)],
            },
        )
        self.client.force_login(coach)
        old_main = (
            "3×1200 m Z2 (4:10) p30 + 150 m Z5 (2:45) + "
            "150 m Z5 (2:52) + 1600 m Z1 (5:33)"
        )
        translated = [{"parts": [{
            "description": f"WU: none · Main: {old_main} · CD: 1700 m Z1",
            "training_fields": {"wu": "", "main": old_main, "cd": "1700 m Z1"},
        }]}]
        laps = [
            {"segment": "CORE", "zone": "2", "meters": 1190, "seconds": 278.387},
            {"segment": "CORE", "zone": "1", "meters": 30, "seconds": 119.931},
            {"segment": "CORE", "zone": "2", "meters": 1200, "seconds": 299.869},
            {"segment": "CORE", "zone": "1", "meters": 30, "seconds": 133.768},
            {"segment": "CORE", "zone": "2", "meters": 1200, "seconds": 306.788},
            {"segment": "CORE", "zone": "1", "meters": 30, "seconds": 119.922},
            {"segment": "CORE", "zone": "3", "meters": 1200, "seconds": 273.342},
            {"segment": "CORE", "zone": "1", "meters": 30, "seconds": 197.906},
            {"segment": "CORE", "zone": "5", "meters": 160, "seconds": 26.455},
            {"segment": "CORE", "zone": "1", "meters": 100, "seconds": 124.873},
            {"segment": "CORE", "zone": "5", "meters": 150, "seconds": 25.760},
            {"segment": "CORE", "zone": "1", "meters": 30, "seconds": 112.735},
            {"segment": "CD", "zone": "1", "meters": 1600, "seconds": 532.270},
            {"segment": "CD", "zone": "1", "meters": 100, "seconds": 100.654},
        ]
        with (
            patch("core.views.polar_raw.translate_model_b", return_value=translated),
            patch("core.views.polar_raw.type_a_watch_loads", return_value=laps),
        ):
            response = self.client.get(
                f"/integrations/garmin/type-c-ayc/?athlete={athlete.id}&date={activity_date.isoformat()}"
            )
        self.assertEqual(response.status_code, 200)
        part = response.json()["results"][0]["parts"][0]
        main = part["training_fields"]["main"]
        self.assertTrue(main.startswith("4×1200 m Z2>Z3"), main)
        self.assertIn("2×150 m Z5 (2:48)", main)
        self.assertNotIn("150 m Z5 (2:45)", main)
        self.assertNotIn("150 m Z5 (2:52)", main)
        self.assertNotIn("1600 m Z1", main)
        self.assertEqual(part["description"], f"WU: none · Main: {main} · CD: 1700 m Z1")


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

    def test_trainer_planner_shows_x_and_can_delete_training(self):
        coach = get_user_model().objects.create_user(
            username="trainer-delete-coach",
            password="secret",
            is_staff=True,
        )
        plan = TrainingPlan.objects.create(
            owner=coach,
            name="Delete training plan",
            plan_kind=TrainingPlan.PLAN_KIND_TRAINER,
        )
        training_day = date(2026, 9, 28)
        slot = TrainingSlot.objects.create(
            plan=plan,
            athlete=None,
            date=training_day,
            slot_index=1,
        )
        TrainingSegment.objects.create(slot=slot, type="CORE", text="40' z1", order=1)
        self.client.force_login(coach)

        detail = self.client.get(
            f"/planning/trainer/{plan.id}/?date={training_day:%Y-%m-%d}&weeks=1"
        )
        self.assertEqual(detail.status_code, 200)
        self.assertContains(detail, "data-trainer-delete-btn", html=False)
        self.assertContains(detail, "Delete training")
        self.assertContains(detail, "cleanupTrainerModalBackdrop", html=False)
        self.assertContains(detail, 'document.body.classList.remove("modal-open")', html=False)

        delete_response = self.client.post(
            f"/slot-modal/{training_day:%Y/%m/%d}/1/?plan={plan.id}",
            {"action": "delete"},
        )
        self.assertEqual(delete_response.status_code, 200)
        self.assertFalse(TrainingSlot.objects.filter(id=slot.id).exists())



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

    def test_year_planner_shows_selected_athlete_without_basis(self):
        _, athlete = self._coach_and_athlete()

        response = self.client.get(f"/planning/year/?period=current_next&athletes={athlete.id}")

        self.assertEqual(response.status_code, 200)
        self.assertFalse(any(row["scope"] == "basis" for row in response.context["rows"]))
        self.assertContains(response, "Year Athlete")
        self.assertContains(response, "Whereabouts")

    def test_year_planner_shows_and_saves_coach_whereabouts_by_access(self):
        coach, _ = self._coach_and_athlete()
        editable_coach = get_user_model().objects.create_user(
            username="editable-coach",
            password="secret",
            is_staff=True,
        )
        view_only_coach = get_user_model().objects.create_user(
            username="view-only-coach",
            password="secret",
            is_staff=True,
        )
        CoachAccess.objects.create(owner=editable_coach, grantee=coach, can_edit=True)
        CoachAccess.objects.create(owner=view_only_coach, grantee=coach, can_edit=False)
        YearPlannerWhereabout.objects.create(
            owner=view_only_coach,
            start_date=date(2026, 9, 7),
            end_date=date(2026, 9, 10),
            whereabouts_type="camp",
            note="View camp",
        )

        page = self.client.get(
            f"/planning/year/?year=2026&period=season&coaches={editable_coach.id}&coaches={view_only_coach.id}"
        )
        self.assertContains(page, "editable-coach")
        self.assertContains(page, "view-only-coach")
        self.assertContains(page, "View camp")
        self.assertContains(page, f"coach-{editable_coach.id}")
        self.assertContains(page, "(whereabouts only)")
        rendered_coach_rows = [
            row
            for chunk in page.context["chunks"]
            for row in chunk["rows"]
            if row["scope"] == f"coach-{view_only_coach.id}"
        ]
        self.assertTrue(rendered_coach_rows[0]["is_coach"])
        self.assertFalse(rendered_coach_rows[0]["read_only"])

        saved = self.client.post(
            "/planning/year/whereabout/",
            data=json.dumps({
                "scope": f"coach-{editable_coach.id}",
                "start_date": "2026-09-12",
                "end_date": "2026-09-15",
                "whereabouts": "travel",
                "note": "Travel",
            }),
            content_type="application/json",
        )
        self.assertEqual(saved.status_code, 200)
        self.assertTrue(YearPlannerWhereabout.objects.filter(
            owner=editable_coach,
            athlete__isnull=True,
            basis_plan__isnull=True,
            note="Travel",
        ).exists())

        saved_view_only = self.client.post(
            "/planning/year/whereabout/",
            data=json.dumps({
                "scope": f"coach-{view_only_coach.id}",
                "start_date": "2026-09-12",
                "end_date": "2026-09-15",
                "whereabouts": "travel",
                "note": "Not allowed",
            }),
            content_type="application/json",
        )
        self.assertEqual(saved_view_only.status_code, 200)
        self.assertTrue(YearPlannerWhereabout.objects.filter(
            owner=view_only_coach,
            athlete__isnull=True,
            basis_plan__isnull=True,
            note="Not allowed",
        ).exists())

    def test_year_planner_does_not_preselect_athletes(self):
        _, athlete = self._coach_and_athlete()

        response = self.client.get("/planning/year/?period=current_next")

        self.assertEqual(response.status_code, 200)
        self.assertFalse(any(row["scope"] == "basis" for row in response.context["rows"]))
        self.assertFalse(any(row["scope"] == f"athlete-{athlete.id}" for row in response.context["rows"]))
        self.assertNotContains(response, f'value="{athlete.id}"\n                checked')
        self.assertContains(response, "year-layout-stack")

    def test_year_planner_can_show_basis_below_all_choice(self):
        coach, athlete = self._coach_and_athlete()
        plan = TrainingPlan.objects.create(
            owner=coach,
            name="Basis group",
            plan_kind=TrainingPlan.PLAN_KIND_TRAINER,
        )

        response = self.client.get(
            f"/planning/year/?period=current_next&athlete_group=plan-{plan.id}&basis=1"
        )

        self.assertEqual(response.status_code, 200)


        self.assertTrue(response.context["show_basis"])
        self.assertTrue(any(row["scope"] == f"basis-plan-{plan.id}" for row in response.context["rows"]))
        self.assertContains(response, "Basis - Basis group")
        html = response.content.decode()
        selector = html.split('<div class="year-athlete-list">', 1)[1].split("</div>", 1)[0]
        self.assertLess(selector.index("All"), selector.index("Basis - Basis group"))

        all_groups = self.client.get("/planning/year/?period=current_next&basis=1")
        self.assertFalse(all_groups.context["show_basis"])
        self.assertNotContains(all_groups, "Basis - Basis group")

    def test_year_planner_stacked_layout_renders_chunks(self):
        _, athlete = self._coach_and_athlete()

        response = self.client.get(f"/planning/year/?year=2026&period=season&layout=stack&zoom=3&athletes={athlete.id}")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Sep 2026 - Nov 2026")
        self.assertContains(response, "year-layout-stack")

    def test_athlete_year_planner_is_hidden_by_default(self):
        _, athlete = self._coach_and_athlete()
        athlete_user = get_user_model().objects.create_user(username="Year_Athlete", password="secret")
        self.client.force_login(athlete_user)

        planning = self.client.get("/planning/")
        response = self.client.get("/planning/year/")

        self.assertEqual(planning.status_code, 200)
        self.assertNotContains(planning, "Season planning")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], "/planning/")

    def test_athlete_year_planner_shows_only_self_when_enabled(self):
        coach, athlete = self._coach_and_athlete()
        athlete.year_planner_training_enabled = True
        athlete.save(update_fields=["year_planner_training_enabled"])
        other = Athlete.objects.create(owner=coach, name="Other Year Athlete", birth_year=2002, gender="X")
        YearPlannerEntry.objects.create(owner=coach, athlete=athlete, date=date(2026, 9, 7), training_type="aerobe")
        YearPlannerEntry.objects.create(owner=coach, athlete=other, date=date(2026, 9, 7), training_type="taper")
        athlete_user = get_user_model().objects.create_user(username="Year_Athlete", password="secret")
        self.client.force_login(athlete_user)

        planning = self.client.get("/planning/")
        response = self.client.get("/planning/year/?year=2026&period=season&athletes={}".format(other.id))

        self.assertEqual(planning.status_code, 200)
        self.assertContains(planning, "Season planning")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["selected_ids"], [athlete.id])
        self.assertFalse(response.context["show_basis"])
        self.assertContains(response, "Year Athlete")
        self.assertNotContains(response, "Other Year Athlete")
        self.assertNotContains(response, '<label class="form-label mb-0">Athletes</label>', html=True)
        self.assertNotContains(response, 'title="Copy training row"')
        self.assertContains(response, "year-read-only")
        self.assertContains(response, "year-training-aerobe")

    def test_athlete_year_planner_never_shows_other_athletes_or_coaches(self):
        coach, athlete = self._coach_and_athlete()
        athlete.year_planner_whereabouts_enabled = True
        athlete.save(update_fields=["year_planner_whereabouts_enabled"])
        CoachSettings.objects.create(user=coach, year_planner_shared_whereabouts_enabled=True)
        other = Athlete.objects.create(owner=coach, name="Shared Year Athlete", birth_year=2002, gender="X")
        YearPlannerEntry.objects.create(
            owner=coach, athlete=other, date=date(2026, 9, 7), training_type="aerobe"
        )
        related_coach = get_user_model().objects.create_user(
            username="related-year-coach",
            password="secret",
            is_staff=True,
        )
        CoachAccess.objects.create(owner=related_coach, grantee=coach, can_edit=False)
        YearPlannerWhereabout.objects.create(
            owner=coach,
            athlete=other,
            start_date=date(2026, 9, 7),
            end_date=date(2026, 9, 9),
            whereabouts_type="camp",
            note="Shared athlete camp",
        )
        YearPlannerWhereabout.objects.create(
            owner=coach,
            athlete=athlete,
            start_date=date(2026, 9, 7),
            end_date=date(2026, 9, 9),
            whereabouts_type="camp",
            note="My own camp",
        )
        YearPlannerWhereabout.objects.create(
            owner=related_coach,
            start_date=date(2026, 9, 10),
            end_date=date(2026, 9, 12),
            whereabouts_type="travel",
            note="Related coach travel",
        )
        athlete_user = get_user_model().objects.create_user(username="Year_Athlete", password="secret")
        self.client.force_login(athlete_user)

        response = self.client.get(
            f"/planning/year/?year=2026&period=season&coaches={related_coach.id}"
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["selected_ids"], [athlete.id])
        self.assertNotContains(response, "Shared Year Athlete")
        self.assertNotContains(response, "Shared athlete camp")
        self.assertContains(response, "My own camp")
        self.assertNotContains(response, "Related coach travel")
        self.assertFalse(any(row["scope"] == f"athlete-{other.id}" for row in response.context["rows"]))
        self.assertFalse(any(row.get("is_coach") for row in response.context["rows"]))
        self.assertEqual(response.context["coaches"], [])

    def test_year_planner_saves_base_and_athlete_entries(self):
        coach, athlete = self._coach_and_athlete()
        plan = TrainingPlan.objects.create(
            owner=coach,
            name="Basis save group",
            plan_kind=TrainingPlan.PLAN_KIND_TRAINER,
        )

        base_response = self.client.post(
            "/planning/year/entry/",
            data=json.dumps({
                "scope": f"basis-plan-{plan.id}",
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
        self.assertTrue(YearPlannerEntry.objects.filter(owner=coach, athlete__isnull=True, basis_plan=plan, training_type="aerobe").exists())
        self.assertTrue(YearPlannerEntry.objects.filter(owner=coach, athlete=athlete, training_type="taper").exists())

    def test_year_planner_keeps_basis_data_separate_per_trainer_group(self):
        coach, _ = self._coach_and_athlete()
        first_plan = TrainingPlan.objects.create(
            owner=coach,
            name="First group",
            plan_kind=TrainingPlan.PLAN_KIND_TRAINER,
        )
        second_plan = TrainingPlan.objects.create(
            owner=coach,
            name="Second group",
            plan_kind=TrainingPlan.PLAN_KIND_TRAINER,
        )

        for plan, training in ((first_plan, "aerobe"), (second_plan, "taper")):
            response = self.client.post(
                "/planning/year/entry/",
                data=json.dumps({
                    "scope": f"basis-plan-{plan.id}",
                    "date": "2026-09-07",
                    "training": training,
                }),
                content_type="application/json",
            )
            self.assertEqual(response.status_code, 200)

        self.assertEqual(
            YearPlannerEntry.objects.get(owner=coach, basis_plan=first_plan, date=date(2026, 9, 7)).training_type,
            "aerobe",
        )
        self.assertEqual(
            YearPlannerEntry.objects.get(owner=coach, basis_plan=second_plan, date=date(2026, 9, 7)).training_type,
            "taper",
        )

        first_view = self.client.get(
            f"/planning/year/?year=2026&period=season&athlete_group=plan-{first_plan.id}&basis=1"
        )
        self.assertContains(first_view, "Basis - First group")
        self.assertContains(first_view, "year-training-aerobe")
        self.assertNotContains(first_view, "Basis - Second group")

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

    def test_year_planner_allows_overlapping_whereabout_ranges(self):
        coach, athlete = self._coach_and_athlete()
        YearPlannerWhereabout.objects.create(
            owner=coach,
            athlete=athlete,
            start_date=date(2026, 9, 1),
            end_date=date(2026, 9, 17),
            whereabouts_type="camp",
            note="Altitude camp",
        )

        response = self.client.post(
            "/planning/year/whereabout/",
            data=json.dumps({
                "scope": f"athlete-{athlete.id}",
                "start_date": "2026-09-08",
                "end_date": "2026-09-08",
                "whereabouts": "test",
                "note": "Blood test",
            }),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(YearPlannerWhereabout.objects.filter(owner=coach, athlete=athlete).count(), 2)
        self.assertTrue(YearPlannerWhereabout.objects.filter(owner=coach, athlete=athlete, whereabouts_type="camp").exists())
        page = self.client.get(f"/planning/year/?year=2026&period=season&athletes={athlete.id}")
        self.assertContains(page, "Blood test")

    def test_year_planner_saves_whereabout_ranges_in_batch(self):
        coach, athlete = self._coach_and_athlete()
        YearPlannerWhereabout.objects.create(
            owner=coach,
            athlete=athlete,
            start_date=date(2026, 9, 3),
            end_date=date(2026, 9, 4),
            whereabouts_type="medical",
            note="Old",
        )

        response = self.client.post(
            "/planning/year/whereabout/",
            data=json.dumps({
                "scope": f"athlete-{athlete.id}",
                "replace": True,
                "ranges": [
                    {
                        "start_date": "2026-09-01",
                        "end_date": "2026-09-10",
                        "whereabouts": "camp",
                        "note": "Camp",
                    },
                    {
                        "start_date": "2026-09-15",
                        "end_date": "2026-09-15",
                        "whereabouts": "test",
                        "note": "Test",
                    },
                ],
            }),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(len(payload["ranges"]), 2)
        self.assertEqual(YearPlannerWhereabout.objects.filter(owner=coach, athlete=athlete).count(), 2)
        self.assertTrue(YearPlannerWhereabout.objects.filter(owner=coach, athlete=athlete, whereabouts_type="camp").exists())
        self.assertTrue(YearPlannerWhereabout.objects.filter(owner=coach, athlete=athlete, whereabouts_type="test").exists())
        self.assertFalse(YearPlannerWhereabout.objects.filter(owner=coach, athlete=athlete, whereabouts_type="medical").exists())

    def test_year_planner_empty_whereabout_batch_replace_clears_period(self):
        coach, athlete = self._coach_and_athlete()
        YearPlannerWhereabout.objects.create(
            owner=coach,
            athlete=athlete,
            start_date=date(2026, 9, 3),
            end_date=date(2026, 9, 4),
            whereabouts_type="medical",
            note="Old",
        )
        YearPlannerWhereabout.objects.create(
            owner=coach,
            athlete=athlete,
            start_date=date(2026, 10, 3),
            end_date=date(2026, 10, 4),
            whereabouts_type="camp",
            note="Keep",
        )

        response = self.client.post(
            "/planning/year/whereabout/",
            data=json.dumps({
                "scope": f"athlete-{athlete.id}",
                "replace": True,
                "replace_start": "2026-09-01",
                "replace_end": "2026-09-30",
                "ranges": [],
            }),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["ranges"], [])
        self.assertFalse(YearPlannerWhereabout.objects.filter(owner=coach, athlete=athlete, whereabouts_type="medical").exists())
        self.assertTrue(YearPlannerWhereabout.objects.filter(owner=coach, athlete=athlete, whereabouts_type="camp").exists())

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


class LoginThrottleTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = get_user_model().objects.create_user(
            username="login-user",
            password="correct-password-123",
        )

    def tearDown(self):
        cache.clear()

    def test_valid_login_still_works(self):
        response = self.client.post(
            "/login/",
            {"username": "login-user", "password": "correct-password-123"},
        )
        self.assertRedirects(response, "/", fetch_redirect_response=False)

    def test_repeated_failures_are_temporarily_throttled(self):
        request_kwargs = {"HTTP_X_FORWARDED_FOR": "198.51.100.20"}
        for _ in range(5):
            response = self.client.post(
                "/login/",
                {"username": "login-user", "password": "wrong-password"},
                **request_kwargs,
            )
            self.assertEqual(response.status_code, 200)
        response = self.client.post(
            "/login/",
            {"username": "login-user", "password": "correct-password-123"},
            **request_kwargs,
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(any(
            "Too many unsuccessful login attempts" in error
            for error in response.context["form"].non_field_errors()
        ))

    def test_admin_login_uses_the_same_throttle(self):
        request_kwargs = {"HTTP_X_FORWARDED_FOR": "198.51.100.21"}
        for _ in range(5):
            self.client.post(
                "/admin/login/",
                {"username": "login-user", "password": "wrong-password", "next": "/admin/"},
                **request_kwargs,
            )
        response = self.client.post(
            "/admin/login/",
            {"username": "login-user", "password": "correct-password-123", "next": "/admin/"},
            **request_kwargs,
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(any(
            "Too many unsuccessful login attempts" in error
            for error in response.context["form"].non_field_errors()
        ))


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

    def test_base_planning_copy_options_are_limited_to_active_coach(self):
        admin = get_user_model().objects.create_user(
            username="base-copy-admin", password="secret", is_staff=True, is_superuser=True
        )
        active_coach = get_user_model().objects.create_user(
            username="base-copy-active", password="secret", is_staff=True
        )
        unrelated_coach = get_user_model().objects.create_user(
            username="base-copy-unrelated", password="secret", is_staff=True
        )
        CoachAccess.objects.create(owner=active_coach, grantee=admin, can_edit=True)
        target = Athlete.objects.create(owner=active_coach, name="Active target", birth_year=2000, gender="X")
        source = Athlete.objects.create(owner=active_coach, name="Active source", birth_year=2000, gender="X")
        unrelated = Athlete.objects.create(owner=unrelated_coach, name="Unrelated athlete", birth_year=2000, gender="X")
        self.client.force_login(admin)
        session = self.client.session
        session["active_coach_owner_id"] = active_coach.id
        session.save()

        page = self.client.get(f"/planning/base/?athlete={target.id}")

        self.assertEqual(page.status_code, 200)
        self.assertContains(page, f'<option value="{source.id}">Active source</option>', html=False)
        self.assertNotContains(page, f'<option value="{unrelated.id}">Unrelated athlete</option>', html=False)

        rejected_copy = self.client.post(
            "/planning/base/",
            {
                "athlete_id": str(target.id),
                "kind": AthleteBasePlanningBlock.KIND_BASE,
                "action": "copy_from",
                "copy_from_athlete_id": str(unrelated.id),
            },
        )

        self.assertEqual(rejected_copy.status_code, 200)
        self.assertContains(rejected_copy, "Choose a valid athlete to copy from.")
        self.assertFalse(AthleteBasePlanningBlock.objects.filter(athlete=target).exists())

    def test_active_pause_distance_supports_time_meters_sets_and_ignored_markers(self):
        _, _, athlete = self._user_plan_and_athlete()
        active = CoachSettings.PAUSE_MODE_ACTIVE_UNLESS_PP
        speed = athlete.get_zone_speed_mps()["1"]

        self.assertEqual(_ayc_pause_distance_m("3x1000m p1", 3, athlete, active), 2 * 60 * speed)
        # Historical segments may still carry the model default or another
        # stale reps value; explicit repeat notation must determine the pauses.
        self.assertAlmostEqual(_ayc_pause_distance_m("4*1200m z2>z3 p2 (5:30-->5:00)", 1, athlete, active), 3 * 2 * 60 * speed)
        self.assertAlmostEqual(_ayc_pause_distance_m("4*1200m z2>z3 p2", 9, athlete, active), 3 * 2 * 60 * speed)
        self.assertEqual(_ayc_pause_distance_m("3x(4x1000m) p=1", 12, athlete, active), 9 * 60 * speed)
        self.assertEqual(_ayc_pause_distance_m("4x200m p=50m", 4, athlete, active), 150)
        self.assertEqual(_ayc_pause_distance_m("4x200m p10", 4, athlete, active), 3 * 10 * 60 * speed)
        self.assertEqual(_ayc_pause_distance_m("4x200m p11", 4, athlete, active), 3 * 11 * speed)
        self.assertEqual(_ayc_pause_distance_m("4x200m sp1 pp1", 4, athlete, active), 0)
        self.assertEqual(_ayc_pause_distance_m("4x200m p", 4, athlete, active), 0)
        self.assertEqual(_ayc_pause_distance_m("4x200m p1", 4, athlete, CoachSettings.PAUSE_MODE_ALWAYS_STATIC), 0)
        static = CoachSettings.PAUSE_MODE_ALWAYS_STATIC
        self.assertAlmostEqual(_ayc_pause_distance_m("4x200m ap1", 4, athlete, static), 3 * 60 * speed)
        self.assertEqual(_ayc_pause_distance_m("4x200m ap=50m", 4, athlete, static), 150)
        self.assertAlmostEqual(_ayc_pause_distance_m("4x200m ap11", 4, athlete, static), 3 * 11 * speed)
        self.assertAlmostEqual(_ayc_pause_distance_m("4x200m ap1", 4, athlete, active), 3 * 60 * speed)
        self.assertEqual(_ayc_pause_distance_m("4x200m sp1 pp1", 4, athlete, static), 0)

    def test_active_pauses_are_added_to_z1_session_loads_only_when_enabled(self):
        _, plan, athlete = self._user_plan_and_athlete()
        slot = TrainingSlot.objects.create(plan=plan, athlete=athlete, date=date.today(), slot_index=1)
        TrainingSegment.objects.create(
            slot=slot,
            order=1,
            type="CORE",
            text="3x1000m p1",
            distance_m=1000,
            norm_distance_m=3000,
            # Simulate an older saved row whose repetition metadata was not
            # refreshed when its training text was edited.
            reps=1,
            zone="2",
        )
        active_loads = _ayc_slot_loads_for_totals(
            slot, athlete, CoachSettings.PAUSE_MODE_ACTIVE_UNLESS_PP
        )
        pause_load = next(load for load in active_loads if load.get("zone") == "1")
        self.assertEqual(pause_load["meters"], 2 * 60 * athlete.get_zone_speed_mps()["1"])
        self.assertFalse(any(load.get("zone") == "1" for load in _ayc_slot_loads_for_totals(
            slot, athlete, CoachSettings.PAUSE_MODE_ALWAYS_STATIC
        )))
        from core.stats import athlete_week_stats
        week_start = date.today() - timedelta(days=date.today().weekday())
        weekly = athlete_week_stats(plan, athlete, week_start, CoachSettings.PAUSE_MODE_ACTIVE_UNLESS_PP)
        self.assertEqual(weekly["zones"]["1"]["distance_m"], 336)

        segment = slot.segments.get(type="CORE")
        segment.text = "3x1000m ap1"
        segment.save(update_fields=["text"])
        static_loads = _ayc_slot_loads_for_totals(
            slot, athlete, CoachSettings.PAUSE_MODE_ALWAYS_STATIC
        )
        self.assertAlmostEqual(
            next(load for load in static_loads if load.get("zone") == "1")["meters"],
            2 * 60 * athlete.get_zone_speed_mps()["1"],
        )
        static_weekly = athlete_week_stats(plan, athlete, week_start, CoachSettings.PAUSE_MODE_ALWAYS_STATIC)
        self.assertEqual(static_weekly["zones"]["1"]["distance_m"], 336)

    def test_ayc_edit_clears_watch_actual_loads(self):
        _, plan, athlete = self._user_plan_and_athlete()
        day = date.today()
        slot = TrainingSlot.objects.create(
            plan=plan,
            athlete=athlete,
            date=day,
            slot_index=1,
            source="watch_b",
            watch_loads=[{"zone": "2", "meters": 12600}],
        )
        TrainingSegment.objects.create(
            slot=slot,
            order=1,
            type="CORE",
            text="12.6km z2",
            distance_m=12600,
            norm_distance_m=12600,
            reps=1,
            zone="2",
        )

        response = self.client.post(
            "/athlete/year/",
            {
                "date": day.isoformat(),
                "slot_index": "1",
                "plan": str(plan.id),
                "athlete": str(athlete.id),
                "slot_text": "5km z1",
                "wu_text": "",
                "mob_text": "",
                "sprint_text": "",
                "core_text": "5km z1",
                "core2_text": "",
                "alt_text": "",
                "cd_text": "",
            },
        )

        self.assertIn(response.status_code, (200, 204))
        slot.refresh_from_db()
        self.assertEqual(slot.source, "planned")
        self.assertEqual(slot.watch_loads, [])
        self.assertEqual(_ayc_slot_session_km(slot, athlete), "5.0")

    def test_ayc_non_main_edit_keeps_actual_main_and_recalculates_edited_wu(self):
        _, plan, athlete = self._user_plan_and_athlete()
        athlete.auto_wucd_enabled = False
        athlete.save(update_fields=["auto_wucd_enabled"])
        day = date.today()
        slot = TrainingSlot.objects.create(
            plan=plan,
            athlete=athlete,
            date=day,
            slot_index=1,
            source="watch_b",
            watch_loads=[
                {"segment": "WU", "zone": "1", "meters": 3800, "seconds": 1200},
                {"segment": "CORE", "zone": "2", "meters": 6000, "seconds": 1500},
            ],
        )
        slot.segments.create(type="WU", text="3800m z1", distance_m=3800, norm_distance_m=3800, zone="1")
        slot.segments.create(type="CORE", text="6x1000m z2 p1", distance_m=1000, norm_distance_m=6000, reps=6, zone="2")

        response = self.client.post(
            "/athlete/year/",
            {
                "date": day.isoformat(),
                "slot_index": "1",
                "plan": str(plan.id),
                "athlete": str(athlete.id),
                "slot_text": "",
                "wu_text": "4800m z1",
                "mob_text": "",
                "sprint_text": "",
                "core_text": "6x1000m z2 p1",
                "core2_text": "",
                "alt_text": "",
                "cd_text": "",
            },
        )

        self.assertIn(response.status_code, (200, 204))
        slot.refresh_from_db()
        self.assertEqual(slot.source, "watch_b")
        self.assertEqual(
            slot.watch_loads,
            [{"segment": "CORE", "zone": "2", "meters": 6000, "seconds": 1500}],
        )
        self.assertEqual(
            _ayc_slot_session_km(slot, athlete, CoachSettings.PAUSE_MODE_ALWAYS_STATIC),
            "10.8",
        )
        core_segment = slot.segments.get(type="CORE")
        wu_segment = slot.segments.get(type="WU")
        self.assertTrue(_watch_segment_loads(core_segment))
        self.assertFalse(_watch_segment_loads(wu_segment))

    def test_ayc_edit_targets_watch_override_when_cell_plan_is_source_plan(self):
        _, source_plan, athlete = self._user_plan_and_athlete()
        flex_plan = TrainingPlan.objects.create(
            owner=source_plan.owner,
            name=f"Flex Planner {source_plan.owner_id}",
        )
        day = date.today()
        watch_slot = TrainingSlot.objects.create(
            plan=flex_plan,
            athlete=athlete,
            date=day,
            slot_index=2,
            source="watch_b",
            watch_loads=[{"zone": "2", "meters": 6500}],
        )
        TrainingSegment.objects.create(
            slot=watch_slot,
            order=1,
            type="CORE",
            text="6x1000m p1",
            distance_m=1000,
            norm_distance_m=6000,
            reps=6,
            zone="2",
        )

        response = self.client.post(
            "/athlete/year/",
            {
                "date": day.isoformat(),
                "slot_index": "2",
                # The AYC cell may submit the underlying source plan id.
                "plan": str(source_plan.id),
                "athlete": str(athlete.id),
                "slot_text": "5km z1",
                "wu_text": "",
                "mob_text": "",
                "sprint_text": "",
                "core_text": "5km z1",
                "core2_text": "",
                "alt_text": "",
                "cd_text": "",
            },
        )

        self.assertIn(response.status_code, (200, 204))
        watch_slot.refresh_from_db()
        self.assertEqual(watch_slot.plan_id, flex_plan.id)
        self.assertEqual(watch_slot.source, "planned")
        self.assertEqual(watch_slot.watch_loads, [])
        self.assertEqual(_ayc_slot_session_km(watch_slot, athlete), "5.0")
        self.assertFalse(
            TrainingSlot.objects.filter(
                plan=source_plan,
                athlete=athlete,
                date=day,
                slot_index=2,
            ).exists()
        )

    def test_ayc_edit_creates_personal_override_for_shared_watch_source(self):
        _, plan, athlete = self._user_plan_and_athlete()
        day = date.today()
        shared_watch = TrainingSlot.objects.create(
            plan=plan,
            athlete=None,
            date=day,
            slot_index=1,
            source="watch_b",
            watch_loads=[{"zone": "2", "meters": 6500}],
        )
        TrainingSegment.objects.create(
            slot=shared_watch,
            order=1,
            type="CORE",
            text="6x1000m p1",
            distance_m=1000,
            norm_distance_m=6000,
            reps=6,
            zone="2",
        )

        response = self.client.post(
            "/athlete/year/",
            {
                "date": day.isoformat(),
                "slot_index": "1",
                "plan": str(plan.id),
                "athlete": str(athlete.id),
                "slot_text": "5km z1",
                "wu_text": "",
                "mob_text": "",
                "sprint_text": "",
                "core_text": "5km z1",
                "core2_text": "",
                "alt_text": "",
                "cd_text": "",
            },
        )

        self.assertIn(response.status_code, (200, 204))
        shared_watch.refresh_from_db()
        personal = TrainingSlot.objects.get(
            plan=plan, athlete=athlete, date=day, slot_index=1
        )
        self.assertEqual(shared_watch.source, "watch_b")
        self.assertEqual(shared_watch.watch_loads[0]["meters"], 6500)
        self.assertEqual(personal.source, "planned")
        self.assertEqual(personal.watch_loads, [])
        self.assertEqual(_ayc_slot_session_km(personal, athlete), "5.0")

    def test_ayc_edit_counts_added_cd_distance_in_planned_total(self):
        _, plan, athlete = self._user_plan_and_athlete()
        day = date.today()

        response = self.client.post(
            "/athlete/year/",
            {
                "date": day.isoformat(),
                "slot_index": "1",
                "plan": str(plan.id),
                "athlete": str(athlete.id),
                "slot_text": "",
                "wu_text": "3800m z1",
                "mob_text": "",
                "sprint_text": "",
                "core_text": "3x2000m z2 p107 - 2x1000m z2 p40",
                "core2_text": "",
                "alt_text": "",
                "cd_text": "1000m",
            },
        )

        self.assertIn(response.status_code, (200, 204))
        slot = TrainingSlot.objects.get(plan=plan, athlete=athlete, date=day, slot_index=1)
        self.assertEqual(_ayc_slot_session_km(slot, athlete, CoachSettings.PAUSE_MODE_ALWAYS_STATIC), "12.8")

    def test_watch_slot_modal_marks_main_confirmation_required(self):
        _, plan, athlete = self._user_plan_and_athlete()
        plan.name = "Flex Planner test"
        plan.save(update_fields=["name"])
        day = date.today()
        slot = TrainingSlot.objects.create(
            plan=plan,
            athlete=athlete,
            date=day,
            slot_index=1,
            source="watch_b",
            watch_loads=[{"zone": "2", "meters": 6500}],
        )
        TrainingSegment.objects.create(
            slot=slot,
            order=1,
            type="CORE",
            text="6x1000m p1",
            distance_m=1000,
            norm_distance_m=6000,
            reps=6,
            zone="2",
        )

        response = self.client.get(
            f"/slot-modal/{day:%Y/%m/%d}/1/?plan={plan.id}&athlete={athlete.id}&source=athlete_year"
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'data-watch-slot="1"')

    def test_trainer_planning_print_uses_selected_week_range(self):
        user = get_user_model().objects.create_user(
            username="trainer-print-coach", password="secret", is_staff=True
        )
        plan = TrainingPlan.objects.create(
            owner=user, name="Printable plan", plan_kind=TrainingPlan.PLAN_KIND_TRAINER
        )
        self.client.force_login(user)

        response = self.client.get(
            f"/planning/trainer/{plan.id}/?date=2026-10-12&weeks=3"
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Print weeks")
        self.assertContains(response, "@page { size: A4 landscape")
        self.assertEqual(response.context["visible_weeks"], 3)

    def test_dco_print_is_available_after_athlete_selection(self):
        user = get_user_model().objects.create_user(
            username="dco-print-coach", password="secret", is_staff=True
        )
        athlete = Athlete.objects.create(
            owner=user, name="DCO Print Athlete", birth_year=2000, gender="X"
        )
        self.client.force_login(user)

        selection = self.client.get(
            "/coach/daily-overview/?date=2026-10-13&selection=selection"
        )
        result = self.client.get(
            f"/coach/daily-overview/?date=2026-10-13&selection=selection&athletes={athlete.id}&slots=both&ok=1"
        )

        self.assertNotContains(selection, "onclick=\"window.print()\"")
        self.assertContains(result, "Print")
        self.assertContains(result, "DCO Print Athlete")
        self.assertContains(result, "daily-print-grid")

    def test_ayc_session_km_includes_running_segments_but_excludes_alternative(self):
        _, plan, athlete = self._user_plan_and_athlete()
        day = date.today()
        slot = TrainingSlot.objects.create(plan=plan, athlete=athlete, date=day, slot_index=1)
        segment_data = [
            ("WU", "1km z1", 1000, 1, "1"),
            ("SPR", "4*100m", 100, 4, "1"),
            ("CORE", "3km z2", 3000, 1, "2"),
            ("CORE2", "2km z3", 2000, 1, "3"),
            ("CD", "500m z1", 500, 1, "1"),
            ("ALT", "5km z1", 5000, 1, "1"),
        ]
        for order, (segment_type, text, distance_m, reps, zone) in enumerate(segment_data, start=1):
            TrainingSegment.objects.create(
                slot=slot,
                order=order,
                type=segment_type,
                text=text,
                distance_m=distance_m,
                norm_distance_m=distance_m * reps,
                reps=reps,
                zone=zone,
            )

        response = self.client.get(f"/athlete/year/?year={day.year}&athlete={athlete.id}")
        self.assertEqual(response.status_code, 200)
        current_cell = next(
            cell
            for week in response.context["week_rows"]
            for cell in week["cells1"]
            if cell["day"] == day
        )
        self.assertEqual(current_cell["session_km"], "6.9")
        self.assertContains(response, 'class="session-km-label">T 6.9</div>')

        athlete.see_session_km = False
        athlete.save(update_fields=["see_session_km"])
        hidden_response = self.client.get(f"/athlete/year/?year={day.year}&athlete={athlete.id}")
        self.assertNotContains(hidden_response, '<div class="session-km-label">')

    def test_ayc_active_pause_appears_in_session_km_and_z1_total(self):
        coach, plan, athlete = self._user_plan_and_athlete()
        CoachSettings.objects.create(
            user=coach,
            pause_mode=CoachSettings.PAUSE_MODE_ACTIVE_UNLESS_PP,
        )
        day = date.today()
        slot = TrainingSlot.objects.create(plan=plan, athlete=athlete, date=day, slot_index=1)
        TrainingSegment.objects.create(
            slot=slot,
            order=1,
            type="CORE",
            text="3x1000m z2 p1",
            distance_m=1000,
            norm_distance_m=3000,
            reps=3,
            zone="2",
        )

        response = self.client.get(f"/athlete/year/?year={day.year}&athlete={athlete.id}")
        cell = next(
            cell
            for week in response.context["week_rows"]
            for cell in week["cells1"]
            if cell["day"] == day
        )
        week = next(week for week in response.context["week_rows"] if week["week_start"] <= day <= week["week_end"])
        self.assertEqual(cell["session_km"], "3.3")
        self.assertEqual(week["sum_z1_km"], "0.3")

        athlete.pause_mode = CoachSettings.PAUSE_MODE_ALWAYS_STATIC
        athlete.save(update_fields=["pause_mode"])
        overridden = self.client.get(f"/athlete/year/?year={day.year}&athlete={athlete.id}")
        overridden_cell = next(
            cell
            for week in overridden.context["week_rows"]
            for cell in week["cells1"]
            if cell["day"] == day
        )
        self.assertEqual(overridden_cell["session_km"], "3.0")

    def test_coach_session_km_is_shared_by_flex_and_dco(self):
        coach = get_user_model().objects.create_user(
            username="coach-session-km",
            password="secret",
            is_staff=True,
        )
        athlete = Athlete.objects.create(
            owner=coach,
            name="Coach Session KM Athlete",
            birth_year=2000,
            gender="X",
        )
        plan = TrainingPlan.objects.create(owner=coach, name="Coach session km plan")
        PlanMembership.objects.create(plan=plan, athlete=athlete)
        day = date.today()
        slot = TrainingSlot.objects.create(plan=plan, date=day, slot_index=1)
        for order, segment_type, text, distance_m in (
            (1, "WU", "1km z1", 1000),
            (2, "CORE", "3km z2", 3000),
            (3, "ALT", "5km z1", 5000),
        ):
            TrainingSegment.objects.create(
                slot=slot,
                order=order,
                type=segment_type,
                text=text,
                distance_m=distance_m,
                norm_distance_m=distance_m,
                zone="1" if segment_type != "CORE" else "2",
            )
        TrainingSegment.objects.create(
            slot=slot,
            order=4,
            type="CORE2",
            text="3x100m p1",
            distance_m=100,
            norm_distance_m=300,
            reps=3,
            zone="2",
        )
        settings = CoachSettings.objects.create(
            user=coach,
            see_session_km=True,
            pause_mode=CoachSettings.PAUSE_MODE_ACTIVE_UNLESS_PP,
        )
        self.client.force_login(coach)

        week_start = day - timedelta(days=day.weekday())
        flex = self.client.get(
            f"/flex-planner/?start={week_start.isoformat()}&weeks=1&athletes={athlete.id}"
        )
        flex_cell = next(
            cell
            for cell in flex.context["week_rows"][0]["athlete_rows"][0]["am_cells"]
            if cell["day"] == day
        )
        self.assertEqual(flex_cell["session_km"], "4.6")
        self.assertContains(flex, "flex-session-km-label")
        self.assertContains(flex, 'data-flex-pause-mode="active_unless_pp"')

        dco = self.client.get(
            f"/coach/daily-overview/?date={day.isoformat()}&selection=all&slots=am&ok=1"
        )
        self.assertEqual(dco.context["rows"][0]["session_km1"], "4.6")
        self.assertContains(dco, "daily-session-km-label")

        settings.see_session_km = False
        settings.save(update_fields=["see_session_km"])
        hidden_flex = self.client.get(
            f"/flex-planner/?start={week_start.isoformat()}&weeks=1&athletes={athlete.id}"
        )
        hidden_cell = next(
            cell
            for cell in hidden_flex.context["week_rows"][0]["athlete_rows"][0]["am_cells"]
            if cell["day"] == day
        )
        self.assertEqual(hidden_cell["session_km"], "")
        self.assertNotContains(hidden_flex, '<div class="flex-session-km-label')

        hidden_dco = self.client.get(
            f"/coach/daily-overview/?date={day.isoformat()}&selection=all&slots=am&ok=1"
        )
        self.assertEqual(hidden_dco.context["rows"][0]["session_km1"], "")
        self.assertNotContains(hidden_dco, '<div class="daily-session-km-label')

    def test_existing_trainer_plan_pm_pauses_follow_coach_mode_in_flex(self):
        coach = get_user_model().objects.create_user(
            username="coach-pm-pauses", password="secret", is_staff=True
        )
        athlete = Athlete.objects.create(
            owner=coach, name="PM Pause Athlete", birth_year=2000, gender="X"
        )
        plan = TrainingPlan.objects.create(
            owner=coach,
            name="PM pause trainer plan",
            plan_kind=TrainingPlan.PLAN_KIND_TRAINER,
        )
        day = date.today()
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
            weekday=day.weekday(),
            slot_index=2,
            mode=AthleteBasePlanningSlot.MODE_TRAINER,
            trainer_plan=plan,
        )
        slot = TrainingSlot.objects.create(plan=plan, date=day, slot_index=2)
        TrainingSegment.objects.create(
            slot=slot, order=1, type="WU", text="3800m z1",
            distance_m=3800, norm_distance_m=3800, zone="1",
        )
        TrainingSegment.objects.create(
            slot=slot, order=2, type="CORE",
            text="4*1200m z2>z3 p2 (5:30-->5:00)",
            distance_m=1200, norm_distance_m=4800, reps=1, zone="2",
        )
        settings = CoachSettings.objects.create(
            user=coach, pause_mode=CoachSettings.PAUSE_MODE_ALWAYS_STATIC
        )
        self.client.force_login(coach)
        week_start = day - timedelta(days=day.weekday())
        url = f"/flex-planner/?start={week_start.isoformat()}&weeks=1&athletes={athlete.id}"

        static = self.client.get(url)
        static_cell = next(
            cell for cell in static.context["week_rows"][0]["athlete_rows"][0]["pm_cells"]
            if cell["day"] == day
        )
        self.assertEqual(static_cell["session_km"], "8.6")

        settings.pause_mode = CoachSettings.PAUSE_MODE_ACTIVE_UNLESS_PP
        settings.save(update_fields=["pause_mode"])
        active = self.client.get(url)
        active_cell = next(
            cell for cell in active.context["week_rows"][0]["athlete_rows"][0]["pm_cells"]
            if cell["day"] == day
        )
        self.assertGreater(float(active_cell["session_km"]), float(static_cell["session_km"]))
        self.assertContains(active, '<tr data-flex-pause-mode="active_unless_pp">')
        self.assertFalse(TrainingSlot.objects.filter(athlete=athlete, date=day).exists())

        # Existing trainer-plan sessions in either half of the day must also
        # count an explicitly active `ap` when ordinary `p` is static.
        AthleteBasePlanningSlot.objects.create(
            block=block, weekday=day.weekday(), slot_index=1,
            mode=AthleteBasePlanningSlot.MODE_TRAINER, trainer_plan=plan,
        )
        am_slot = TrainingSlot.objects.create(plan=plan, date=day, slot_index=1)
        TrainingSegment.objects.create(
            slot=am_slot, order=1, type="CORE", text="3*1000m z2 ap=50m",
            distance_m=1000, norm_distance_m=3000, reps=1, zone="2",
        )
        pm_main = slot.segments.get(type="CORE")
        pm_main.text = "4*1200m z2>z3 ap2 (5:30-->5:00)"
        pm_main.save(update_fields=["text"])
        settings.pause_mode = CoachSettings.PAUSE_MODE_ALWAYS_STATIC
        settings.save(update_fields=["pause_mode"])
        explicit = self.client.get(url)
        athlete_row = explicit.context["week_rows"][0]["athlete_rows"][0]
        am_cell = next(cell for cell in athlete_row["am_cells"] if cell["day"] == day)
        pm_cell = next(cell for cell in athlete_row["pm_cells"] if cell["day"] == day)
        self.assertEqual(am_cell["session_km"], "3.1")
        self.assertGreater(float(pm_cell["session_km"]), float(static_cell["session_km"]))
        self.assertContains(explicit, '<tr data-flex-pause-mode="always_static">')

    def test_ayc_week_totals_exclude_not_done_running_and_alternative_load(self):
        user, plan, athlete = self._user_plan_and_athlete()
        day = date.today()
        not_done_slot = TrainingSlot.objects.create(
            plan=plan, athlete=athlete, date=day, slot_index=1
        )
        TrainingSegment.objects.create(
            slot=not_done_slot,
            order=1,
            type="CORE",
            text="5km z1",
            distance_m=5000,
            norm_distance_m=5000,
            zone="1",
        )
        TrainingSegment.objects.create(
            slot=not_done_slot,
            order=2,
            type="ALT",
            text="30' z1",
            duration_s=1800,
            zone="1",
        )
        completed_slot = TrainingSlot.objects.create(
            plan=plan, athlete=athlete, date=day, slot_index=2
        )
        TrainingSegment.objects.create(
            slot=completed_slot,
            order=1,
            type="CORE",
            text="2km z2",
            distance_m=2000,
            norm_distance_m=2000,
            zone="2",
        )
        TrainingSegment.objects.create(
            slot=completed_slot,
            order=2,
            type="ALT",
            text="10' z2",
            duration_s=600,
            zone="2",
        )
        AthleteDayCheck.objects.create(
            athlete=athlete,
            date=day,
            slot_index=1,
            status=AthleteDayCheck.STATUS_NOT_DONE,
            updated_by=user,
        )

        response = self.client.get(f"/athlete/year/?year={day.year}&athlete={athlete.id}")

        self.assertEqual(response.status_code, 200)
        week = next(row for row in response.context["week_rows"] if row["week_start"] <= day <= row["week_end"])
        self.assertEqual(week["sum_tot_km"], "2.0")
        self.assertEqual(week["alt_z1_min"], 0)
        self.assertEqual(week["alt_z2_min"], 10)

    def test_base_planning_autosave_allows_intermediate_overlapping_blocks(self):
        user, _, athlete = self._user_plan_and_athlete()
        block1 = AthleteBasePlanningBlock.objects.create(
            athlete=athlete,
            planning_kind=AthleteBasePlanningBlock.KIND_BASE,
            label="Block 1",
            start_month=1,
            start_day=1,
            end_month=12,
            end_day=31,
            sort_order=1,
        )
        block2 = AthleteBasePlanningBlock.objects.create(
            athlete=athlete,
            planning_kind=AthleteBasePlanningBlock.KIND_BASE,
            label="Block 2",
            start_month=1,
            start_day=1,
            end_month=12,
            end_day=31,
            sort_order=2,
        )

        response = self.client.post(
            "/planning/base/",
            {
                "athlete_id": str(athlete.id),
                "kind": AthleteBasePlanningBlock.KIND_BASE,
                "action": "save",
                "autosave": "1",
                "block_id": [str(block1.id), str(block2.id)],
                f"block_{block1.id}_label": "Winter",
                f"block_{block1.id}_start": "01-01",
                f"block_{block1.id}_end": "30-06",
                f"block_{block2.id}_label": "Summer",
                f"block_{block2.id}_start": "01-01",
                f"block_{block2.id}_end": "31-12",
            },
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        self.assertEqual(response.status_code, 200)
        future_blocks = list(AthleteBasePlanningBlock.objects.filter(
            athlete=athlete,
            effective_from=date.today() + timedelta(days=1),
        ).order_by("sort_order"))
        self.assertEqual(len(future_blocks), 2)
        self.assertEqual((future_blocks[0].start_month, future_blocks[0].start_day, future_blocks[0].end_month, future_blocks[0].end_day), (1, 1, 6, 30))
        self.assertEqual((future_blocks[1].start_month, future_blocks[1].start_day, future_blocks[1].end_month, future_blocks[1].end_day), (1, 1, 12, 31))

        response = self.client.post(
            "/planning/base/",
            {
                "athlete_id": str(athlete.id),
                "kind": AthleteBasePlanningBlock.KIND_BASE,
                "action": "save",
                "autosave": "1",
                "block_id": [str(block1.id), str(block2.id)],
                f"block_{block1.id}_label": "Winter",
                f"block_{block1.id}_start": "01-01",
                f"block_{block1.id}_end": "30-06",
                f"block_{block2.id}_label": "Summer",
                f"block_{block2.id}_start": "01-07",
                f"block_{block2.id}_end": "31-12",
            },
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        self.assertEqual(response.status_code, 200)
        future_block2 = AthleteBasePlanningBlock.objects.get(
            athlete=athlete,
            effective_from=date.today() + timedelta(days=1),
            sort_order=2,
        )
        self.assertEqual((future_block2.start_month, future_block2.start_day, future_block2.end_month, future_block2.end_day), (7, 1, 12, 31))

    def test_base_planning_form_autosave_persists_slot_and_block_fields(self):
        _, _, athlete = self._user_plan_and_athlete()
        block = AthleteBasePlanningBlock.objects.create(
            athlete=athlete,
            planning_kind=AthleteBasePlanningBlock.KIND_BASE,
            label="Original",
            start_month=1,
            start_day=1,
            end_month=12,
            end_day=31,
            sort_order=1,
        )
        slot = AthleteBasePlanningSlot.objects.create(
            block=block,
            weekday=0,
            slot_index=1,
            mode=AthleteBasePlanningSlot.MODE_REST,
        )

        response = self.client.post(
            f"/planning/base/?athlete={athlete.id}",
            {
                "athlete_id": str(athlete.id),
                "kind": AthleteBasePlanningBlock.KIND_BASE,
                "action": "save",
                "autosave": "1",
                "block_id": [str(block.id)],
                f"block_{block.id}_label": "Autosaved block",
                f"block_{block.id}_start": "01-01",
                f"block_{block.id}_end": "31-12",
                f"slot_{slot.id}_mode": AthleteBasePlanningSlot.MODE_TRAINING,
                f"slot_{slot.id}_training_text": "CORE=5 km z2",
                f"slot_{slot.id}_trainer_plan": "",
            },
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        self.assertEqual(response.status_code, 200, response.content.decode())
        self.assertEqual(response.json(), {"ok": True})
        editable_block = AthleteBasePlanningBlock.objects.get(
            athlete=athlete,
            planning_kind=AthleteBasePlanningBlock.KIND_BASE,
            effective_from=date.today() + timedelta(days=1),
        )
        self.assertEqual(editable_block.label, "Autosaved block")
        editable_slot = editable_block.slots.get(weekday=0, slot_index=1)
        self.assertEqual(editable_slot.mode, AthleteBasePlanningSlot.MODE_TRAINING)
        self.assertEqual(editable_slot.training_text, "CORE=5 km z2")

    def test_base_planning_slot_autosave_uses_full_form_save_path(self):
        _, _, athlete = self._user_plan_and_athlete()
        page = self.client.get(f"/planning/base/?athlete={athlete.id}")

        self.assertEqual(page.status_code, 200)
        self.assertContains(page, 'action="/planning/base/" id="basePlanningForm"')
        self.assertContains(page, 'const autosaveUrl = "/planning/base/";')
        self.assertContains(page, "const data = new FormData(planningForm);")
        self.assertContains(page, 'data.set("action", "save");')
        self.assertNotContains(page, 'data.set("action", "autosave_slot");')

    def test_base_planning_block_copy_keeps_slots(self):
        user, plan, athlete = self._user_plan_and_athlete()
        block = AthleteBasePlanningBlock.objects.create(
            athlete=athlete,
            planning_kind=AthleteBasePlanningBlock.KIND_BASE,
            label="Winter",
            start_month=1,
            start_day=1,
            end_month=3,
            end_day=31,
            sort_order=1,
        )
        AthleteBasePlanningSlot.objects.create(
            block=block,
            weekday=0,
            slot_index=1,
            mode=AthleteBasePlanningSlot.MODE_TRAINER,
            trainer_plan=plan,
        )
        AthleteBasePlanningSlot.objects.create(
            block=block,
            weekday=1,
            slot_index=2,
            mode=AthleteBasePlanningSlot.MODE_TRAINING,
            training_text="CORE=5 km z2",
        )

        response = self.client.post(
            "/planning/base/",
            {
                "athlete_id": str(athlete.id),
                "kind": AthleteBasePlanningBlock.KIND_BASE,
                "action": f"copy_block:{block.id}",
            },
        )

        self.assertEqual(response.status_code, 302)
        copied = AthleteBasePlanningBlock.objects.get(athlete=athlete, label="Winter copy")
        self.assertEqual((copied.start_month, copied.start_day, copied.end_month, copied.end_day), (1, 1, 3, 31))
        copied_slots = {
            (slot.weekday, slot.slot_index): slot
            for slot in copied.slots.all()
        }
        self.assertEqual(copied_slots[(0, 1)].mode, AthleteBasePlanningSlot.MODE_TRAINER)
        self.assertEqual(copied_slots[(0, 1)].trainer_plan, plan)
        self.assertEqual(copied_slots[(1, 2)].mode, AthleteBasePlanningSlot.MODE_TRAINING)
        self.assertEqual(copied_slots[(1, 2)].training_text, "CORE=5 km z2")

    def test_base_planning_autosave_does_not_delete_blocks(self):
        user, _, athlete = self._user_plan_and_athlete()
        block1 = AthleteBasePlanningBlock.objects.create(
            athlete=athlete,
            planning_kind=AthleteBasePlanningBlock.KIND_BASE,
            label="Block 1",
            start_month=1,
            start_day=1,
            end_month=6,
            end_day=30,
            sort_order=1,
        )
        block2 = AthleteBasePlanningBlock.objects.create(
            athlete=athlete,
            planning_kind=AthleteBasePlanningBlock.KIND_BASE,
            label="Block 2",
            start_month=7,
            start_day=1,
            end_month=12,
            end_day=31,
            sort_order=2,
        )

        response = self.client.post(
            "/planning/base/",
            {
                "athlete_id": str(athlete.id),
                "kind": AthleteBasePlanningBlock.KIND_BASE,
                "action": "save",
                "autosave": "1",
                "block_id": [str(block1.id), str(block2.id)],
                "delete_block": [str(block2.id)],
                f"block_{block1.id}_label": "Block 1",
                f"block_{block1.id}_start": "01-01",
                f"block_{block1.id}_end": "30-06",
                f"block_{block2.id}_label": "Block 2",
                f"block_{block2.id}_start": "01-07",
                f"block_{block2.id}_end": "31-12",
            },
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(AthleteBasePlanningBlock.objects.filter(id=block2.id).exists())

    def test_base_planning_add_block_uses_posted_previous_end_date(self):
        user, plan, athlete = self._user_plan_and_athlete()
        block = AthleteBasePlanningBlock.objects.create(
            athlete=athlete,
            planning_kind=AthleteBasePlanningBlock.KIND_BASE,
            label="Block 1",
            start_month=1,
            start_day=1,
            end_month=12,
            end_day=31,
            sort_order=1,
        )
        AthleteBasePlanningSlot.objects.create(
            block=block,
            weekday=0,
            slot_index=1,
            mode=AthleteBasePlanningSlot.MODE_TRAINER,
            trainer_plan=plan,
        )

        response = self.client.post(
            "/planning/base/",
            {
                "athlete_id": str(athlete.id),
                "kind": AthleteBasePlanningBlock.KIND_BASE,
                "action": "add_block",
                "block_id": [str(block.id)],
                f"block_{block.id}_label": "Block 1",
                f"block_{block.id}_start": "01-01",
                f"block_{block.id}_end": "30-06",
            },
        )

        self.assertEqual(response.status_code, 302)
        blocks = list(AthleteBasePlanningBlock.objects.filter(
            athlete=athlete,
            effective_from=date.today() + timedelta(days=1),
        ).order_by("sort_order"))
        self.assertEqual(len(blocks), 2)
        self.assertEqual((blocks[0].start_month, blocks[0].start_day, blocks[0].end_month, blocks[0].end_day), (1, 1, 6, 30))
        self.assertEqual((blocks[1].start_month, blocks[1].start_day, blocks[1].end_month, blocks[1].end_day), (7, 1, 12, 31))

    def test_base_planning_delete_block_button_deletes_immediately(self):
        user, _, athlete = self._user_plan_and_athlete()
        block = AthleteBasePlanningBlock.objects.create(
            athlete=athlete,
            planning_kind=AthleteBasePlanningBlock.KIND_BASE,
            label="Delete me",
            start_month=1,
            start_day=1,
            end_month=6,
            end_day=30,
            sort_order=1,
        )

        response = self.client.post(
            "/planning/base/",
            {
                "athlete_id": str(athlete.id),
                "kind": AthleteBasePlanningBlock.KIND_BASE,
                "action": f"delete_block:{block.id}",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertTrue(AthleteBasePlanningBlock.objects.filter(id=block.id).exists())
        self.assertFalse(AthleteBasePlanningBlock.objects.filter(
            athlete=athlete,
            effective_from=date.today() + timedelta(days=1),
        ).exists())

    def test_base_planning_save_does_not_copy_even_with_copy_id_present(self):
        user, _, athlete = self._user_plan_and_athlete()
        block = AthleteBasePlanningBlock.objects.create(
            athlete=athlete,
            planning_kind=AthleteBasePlanningBlock.KIND_BASE,
            label="Block 1",
            start_month=1,
            start_day=1,
            end_month=12,
            end_day=31,
            sort_order=1,
        )

        response = self.client.post(
            "/planning/base/",
            {
                "athlete_id": str(athlete.id),
                "kind": AthleteBasePlanningBlock.KIND_BASE,
                "action": "save",
                "copy_block_id": str(block.id),
                "block_id": [str(block.id)],
                f"block_{block.id}_label": "Saved label",
                f"block_{block.id}_start": "01-01",
                f"block_{block.id}_end": "31-12",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(AthleteBasePlanningBlock.objects.filter(athlete=athlete).count(), 2)
        future_block = AthleteBasePlanningBlock.objects.get(
            athlete=athlete,
            effective_from=date.today() + timedelta(days=1),
        )
        self.assertEqual(future_block.label, "Saved label")
        block.refresh_from_db()
        self.assertEqual(block.label, "Block 1")

    def test_base_planning_add_block_rejects_after_year_end(self):
        user, _, athlete = self._user_plan_and_athlete()
        AthleteBasePlanningBlock.objects.create(
            athlete=athlete,
            planning_kind=AthleteBasePlanningBlock.KIND_BASE,
            label="Block 1",
            start_month=1,
            start_day=1,
            end_month=12,
            end_day=31,
            sort_order=1,
        )

        response = self.client.post(
            "/planning/base/",
            {
                "athlete_id": str(athlete.id),
                "kind": AthleteBasePlanningBlock.KIND_BASE,
                "action": "add_block",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Cannot add a block")
        self.assertEqual(AthleteBasePlanningBlock.objects.filter(athlete=athlete).count(), 1)

    def test_base_planning_manual_save_keeps_block_dates(self):
        user, _, athlete = self._user_plan_and_athlete()
        block1 = AthleteBasePlanningBlock.objects.create(
            athlete=athlete,
            planning_kind=AthleteBasePlanningBlock.KIND_BASE,
            label="Block 1",
            start_month=1,
            start_day=1,
            end_month=6,
            end_day=30,
            sort_order=1,
        )
        block2 = AthleteBasePlanningBlock.objects.create(
            athlete=athlete,
            planning_kind=AthleteBasePlanningBlock.KIND_BASE,
            label="Block 2",
            start_month=7,
            start_day=1,
            end_month=12,
            end_day=31,
            sort_order=2,
        )

        response = self.client.post(
            "/planning/base/",
            {
                "athlete_id": str(athlete.id),
                "kind": AthleteBasePlanningBlock.KIND_BASE,
                "action": "save",
                "block_id": [str(block1.id), str(block2.id)],
                f"block_{block1.id}_label": "Early",
                f"block_{block1.id}_start": "01-01",
                f"block_{block1.id}_end": "31-05",
                f"block_{block2.id}_label": "Late",
                f"block_{block2.id}_start": "01-06",
                f"block_{block2.id}_end": "31-12",
            },
        )

        self.assertEqual(response.status_code, 200)
        future_blocks = list(AthleteBasePlanningBlock.objects.filter(
            athlete=athlete,
            effective_from=date.today() + timedelta(days=1),
        ).order_by("sort_order"))
        self.assertEqual((future_blocks[0].start_month, future_blocks[0].start_day, future_blocks[0].end_month, future_blocks[0].end_day), (1, 1, 5, 31))
        self.assertEqual((future_blocks[1].start_month, future_blocks[1].start_day, future_blocks[1].end_month, future_blocks[1].end_day), (6, 1, 12, 31))

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

    def test_flex_can_copy_training_from_athlete_base_week(self):
        user = get_user_model().objects.create_user(
            username="base-copy-coach",
            password="secret",
            is_staff=True,
        )
        athlete = Athlete.objects.create(
            owner=user,
            name="Base Copy Athlete",
            birth_year=2000,
            gender="X",
        )
        flex_plan = TrainingPlan.objects.create(owner=user, name="Flex Planner base copy")
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
            weekday=0,
            slot_index=1,
            mode=AthleteBasePlanningSlot.MODE_TRAINING,
            training_text="WU=1000m z1\nCORE=6*400m z4\nCD=1000m z1",
        )
        self.client.force_login(user)

        copy_response = self.client.post(
            f"/slot-copy/2026/01/05/1/?plan={flex_plan.id}&athlete={athlete.id}&source=flex"
        )
        self.assertEqual(copy_response.status_code, 200)
        clipboard = self.client.session.get("training_clipboard")
        self.assertEqual([item["type"] for item in clipboard["segments"]], ["WU", "CORE", "CD"])

        paste_response = self.client.post(
            f"/slot-paste/2026/01/06/2/?plan={flex_plan.id}&athlete={athlete.id}&source=flex"
        )
        self.assertEqual(paste_response.status_code, 200)
        slot = TrainingSlot.objects.get(plan=flex_plan, athlete=athlete, date="2026-01-06", slot_index=2)
        self.assertEqual(
            [segment.text for segment in slot.segments.order_by("order", "id")],
            ["1000m z1", "6*400m z4", "1000m z1"],
        )

    def test_flex_modal_prefills_base_individual_training(self):
        user = get_user_model().objects.create_user(
            username="base-modal-coach",
            password="secret",
            is_staff=True,
        )
        athlete = Athlete.objects.create(
            owner=user,
            name="Base Modal Athlete",
            birth_year=2000,
            gender="X",
        )
        flex_plan = TrainingPlan.objects.create(owner=user, name=f"Flex Planner {user.id}")
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
            weekday=3,
            slot_index=1,
            mode=AthleteBasePlanningSlot.MODE_TRAINING,
            training_text="WU=1000m z1\nCORE=6*400m z4\nCD=1000m z1",
        )
        self.client.force_login(user)

        response = self.client.get(
            f"/slot-modal/2026/09/24/1/?plan={flex_plan.id}&athlete={athlete.id}&source=flex"
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "1000m z1")
        self.assertContains(response, "6*400m z4")
        self.assertEqual(response.context["wu_text"], "1000m z1")
        self.assertEqual(response.context["core_text"], "6*400m z4")
        self.assertEqual(response.context["cd_text"], "1000m z1")

    def test_flex_modal_uses_current_effective_base_individual_training(self):
        user = get_user_model().objects.create_user(
            username="base-modal-effective-coach",
            password="secret",
            is_staff=True,
        )
        athlete = Athlete.objects.create(
            owner=user,
            name="Effective Base Modal Athlete",
            birth_year=2000,
            gender="X",
        )
        flex_plan = TrainingPlan.objects.create(owner=user, name=f"Flex Planner {user.id}")
        old_block = AthleteBasePlanningBlock.objects.create(
            athlete=athlete,
            planning_kind=AthleteBasePlanningBlock.KIND_BASE,
            start_month=1,
            start_day=1,
            end_month=12,
            end_day=31,
            effective_from=date(2025, 1, 1),
        )
        AthleteBasePlanningSlot.objects.create(
            block=old_block,
            weekday=3,
            slot_index=1,
            mode=AthleteBasePlanningSlot.MODE_TRAINING,
            training_text="CORE=Old plan 10 km z1",
        )
        current_block = AthleteBasePlanningBlock.objects.create(
            athlete=athlete,
            planning_kind=AthleteBasePlanningBlock.KIND_BASE,
            start_month=1,
            start_day=1,
            end_month=12,
            end_day=31,
            effective_from=date(2026, 1, 1),
        )
        AthleteBasePlanningSlot.objects.create(
            block=current_block,
            weekday=3,
            slot_index=1,
            mode=AthleteBasePlanningSlot.MODE_TRAINING,
            training_text="WU=1000m z1\nCORE=Current plan 8*400m z4\nCD=800m z1",
        )
        self.client.force_login(user)

        flex_response = self.client.get(
            f"/flex-planner/?start=2026-09-21&weeks=1&athletes={athlete.id}"
        )
        flex_cell = next(
            cell
            for week in flex_response.context["week_rows"]
            for cell in week["athlete_rows"][0]["am_cells"]
            if cell["day"] == date(2026, 9, 24)
        )
        self.assertEqual(flex_cell["slot"].core_text(), "Current plan 8*400m z4")

        response = self.client.get(
            f"/slot-modal/2026/09/24/1/?plan={flex_plan.id}&athlete={athlete.id}&source=flex"
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["wu_text"], "1000m z1")
        self.assertEqual(response.context["core_text"], "Current plan 8*400m z4")
        self.assertEqual(response.context["cd_text"], "800m z1")

    def test_flex_modal_prefers_individual_base_training_over_assigned_trainer_plan(self):
        user = get_user_model().objects.create_user(
            username="base-modal-vs-trainer-coach",
            password="secret",
            is_staff=True,
        )
        athlete = Athlete.objects.create(
            owner=user,
            name="Individual Base Training Athlete",
            birth_year=2000,
            gender="X",
        )
        trainer_plan = TrainingPlan.objects.create(
            owner=user,
            name="Assigned Trainer Plan",
            plan_kind=TrainingPlan.PLAN_KIND_TRAINER,
        )
        PlanMembership.objects.create(plan=trainer_plan, athlete=athlete)
        flex_plan = TrainingPlan.objects.create(owner=user, name=f"Flex Planner {user.id}")
        day = date(2026, 9, 24)
        block = AthleteBasePlanningBlock.objects.create(
            athlete=athlete,
            planning_kind=AthleteBasePlanningBlock.KIND_BASE,
            start_month=1,
            start_day=1,
            end_month=12,
            end_day=31,
            effective_from=date(2026, 1, 1),
        )
        AthleteBasePlanningSlot.objects.create(
            block=block,
            weekday=day.weekday(),
            slot_index=1,
            mode=AthleteBasePlanningSlot.MODE_TRAINING,
            training_text="WU=800m z1\nCORE=Individual 6*500m z3\nCD=600m z1",
        )
        trainer_slot = TrainingSlot.objects.create(
            plan=trainer_plan,
            date=day,
            slot_index=1,
        )
        trainer_slot.segments.create(type="CORE", text="Trainer plan 10 km z1", order=0)
        self.client.force_login(user)

        flex_page = self.client.get(
            f"/flex-planner/?start=2026-09-21&weeks=1&athletes={athlete.id}"
        )
        flex_cell = next(
            cell
            for week in flex_page.context["week_rows"]
            for cell in week["athlete_rows"][0]["am_cells"]
            if cell["day"] == day
        )
        self.assertEqual(flex_cell["slot"].core_text(), "Individual 6*500m z3")

        response = self.client.get(
            f"/slot-modal/{day.year}/{day.month}/{day.day}/1/"
            f"?plan={trainer_plan.id}&athlete={athlete.id}&source=flex"
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["wu_text"], "800m z1")
        self.assertEqual(response.context["core_text"], "Individual 6*500m z3")
        self.assertEqual(response.context["cd_text"], "600m z1")

    def test_flex_modal_prefills_training_from_source_plan_before_override(self):
        user = get_user_model().objects.create_user(
            username="source-plan-modal-coach",
            password="secret",
            is_staff=True,
        )
        athlete = Athlete.objects.create(
            owner=user,
            name="Source Plan Modal Athlete",
            birth_year=2000,
            gender="X",
        )
        source_plan = TrainingPlan.objects.create(owner=user, name="Visible source plan")
        PlanMembership.objects.create(plan=source_plan, athlete=athlete)
        TrainingPlan.objects.create(owner=user, name=f"Flex Planner {user.id}")
        slot = TrainingSlot.objects.create(
            plan=source_plan,
            date=date(2026, 9, 24),
            slot_index=1,
        )
        TrainingSegment.objects.create(
            slot=slot,
            type="CORE",
            text="8 km z2",
            zone="2",
            distance_m=8000,
            norm_distance_m=8000,
        )
        self.client.force_login(user)

        response = self.client.get(
            f"/slot-modal/2026/09/24/1/?plan={source_plan.id}&athlete={athlete.id}&source=flex"
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "8 km z2")

    def test_flex_modal_exposes_reset_for_empty_override(self):
        user = get_user_model().objects.create_user(
            username="empty-override-reset-coach",
            password="secret",
            is_staff=True,
        )
        athlete = Athlete.objects.create(
            owner=user,
            name="Empty Override Athlete",
            birth_year=2000,
            gender="X",
        )
        source_plan = TrainingPlan.objects.create(owner=user, name="Reset source plan")
        PlanMembership.objects.create(plan=source_plan, athlete=athlete)
        source_slot = TrainingSlot.objects.create(
            plan=source_plan,
            date=date(2026, 9, 24),
            slot_index=1,
        )
        TrainingSegment.objects.create(
            slot=source_slot,
            type="CORE",
            text="8 km z2",
            zone="2",
            distance_m=8000,
            norm_distance_m=8000,
        )
        flex_plan = TrainingPlan.objects.create(owner=user, name=f"Flex Planner {user.id}")
        empty_override = TrainingSlot.objects.create(
            plan=flex_plan,
            athlete=athlete,
            date=date(2026, 9, 24),
            slot_index=1,
        )
        self.client.force_login(user)

        response = self.client.get(
            f"/slot-modal/2026/09/24/1/?plan={flex_plan.id}&athlete={athlete.id}&source=flex"
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Reset to plan")

        reset_response = self.client.post(
            f"/slot-reset-override/2026/09/24/1/?plan={flex_plan.id}&athlete={athlete.id}&source=flex"
        )

        self.assertEqual(reset_response.status_code, 200)
        self.assertFalse(TrainingSlot.objects.filter(id=empty_override.id).exists())

    def test_flex_reset_resolves_personal_plan_when_modal_points_to_source_plan(self):
        user = get_user_model().objects.create_user(
            username="source-reset-coach",
            password="secret",
            is_staff=True,
        )
        athlete = Athlete.objects.create(owner=user, name="Source Reset Athlete", birth_year=2000, gender="X")
        source_plan = TrainingPlan.objects.create(owner=user, name="Source reset plan")
        PlanMembership.objects.create(plan=source_plan, athlete=athlete)
        flex_plan = TrainingPlan.objects.create(owner=user, name=f"Flex Planner {user.id}")
        empty_override = TrainingSlot.objects.create(
            plan=flex_plan, athlete=athlete, date=date(2026, 9, 24), slot_index=1
        )
        self.client.force_login(user)

        response = self.client.post(
            f"/slot-reset-override/2026/09/24/1/?plan={source_plan.id}&athlete={athlete.id}&source=flex"
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(TrainingSlot.objects.filter(id=empty_override.id).exists())

    def test_direct_flex_modal_reset_fallback_removes_override(self):
        user = get_user_model().objects.create_user(
            username="direct-reset-coach",
            password="secret",
            is_staff=True,
        )
        athlete = Athlete.objects.create(owner=user, name="Direct Reset Athlete", birth_year=2000, gender="X")
        source_plan = TrainingPlan.objects.create(owner=user, name="Direct source plan")
        PlanMembership.objects.create(plan=source_plan, athlete=athlete)
        flex_plan = TrainingPlan.objects.create(owner=user, name=f"Flex Planner {user.id}")
        empty_override = TrainingSlot.objects.create(
            plan=flex_plan, athlete=athlete, date=date(2026, 9, 24), slot_index=1
        )
        self.client.force_login(user)

        response = self.client.post(
            f"/slot-modal/2026/09/24/1/?plan={source_plan.id}&athlete={athlete.id}&source=flex",
            {"action": "reset_to_plan", "plan": str(source_plan.id), "athlete": str(athlete.id), "source": "flex"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(TrainingSlot.objects.filter(id=empty_override.id).exists())

    def test_flex_hides_empty_trainer_plan_from_base_planning(self):
        user = get_user_model().objects.create_user(
            username="empty-trainer-base-coach",
            password="secret",
            is_staff=True,
        )
        athlete = Athlete.objects.create(
            owner=user,
            name="Empty Trainer Base Athlete",
            birth_year=2000,
            gender="X",
        )
        trainer_plan = TrainingPlan.objects.create(
            owner=user,
            name="Empty trainer plan",
            plan_kind=TrainingPlan.PLAN_KIND_TRAINER,
        )
        AthleteBasePlanningBlock.objects.create(
            athlete=athlete,
            planning_kind=AthleteBasePlanningBlock.KIND_BASE,
            start_month=1,
            start_day=1,
            end_month=12,
            end_day=31,
        )
        block = AthleteBasePlanningBlock.objects.get(athlete=athlete)
        AthleteBasePlanningSlot.objects.create(
            block=block,
            weekday=3,
            slot_index=1,
            mode=AthleteBasePlanningSlot.MODE_TRAINER,
            trainer_plan=trainer_plan,
        )
        TrainingSlot.objects.create(
            plan=trainer_plan,
            date=date(2026, 9, 24),
            slot_index=1,
        )
        self.client.force_login(user)

        response = self.client.get(
            f"/flex-planner/?start=2026-09-21&weeks=1&athletes={athlete.id}"
        )

        self.assertEqual(response.status_code, 200)
        target_cell = response.context["week_rows"][0]["athlete_rows"][0]["am_cells"][3]
        self.assertIsNone(target_cell["slot"])

    def test_flex_uses_base_planning_trainer_plan_for_each_daypart(self):
        user = get_user_model().objects.create_user(
            username="mixed-trainer-base-coach",
            password="secret",
            is_staff=True,
        )
        athlete = Athlete.objects.create(
            owner=user, name="Mixed Trainer Base Athlete", birth_year=2000, gender="X"
        )
        first_plan = TrainingPlan.objects.create(
            owner=user, name="A CORE", plan_kind=TrainingPlan.PLAN_KIND_TRAINER
        )
        second_plan = TrainingPlan.objects.create(
            owner=user, name="B MILA", plan_kind=TrainingPlan.PLAN_KIND_TRAINER
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
            block=block, weekday=0, slot_index=2,
            mode=AthleteBasePlanningSlot.MODE_TRAINER, trainer_plan=first_plan,
        )
        AthleteBasePlanningSlot.objects.create(
            block=block, weekday=1, slot_index=2,
            mode=AthleteBasePlanningSlot.MODE_TRAINER, trainer_plan=second_plan,
        )
        monday_slot = TrainingSlot.objects.create(
            plan=first_plan, date=date(2026, 10, 12), slot_index=2
        )
        monday_slot.segments.create(type="CORE", text="40' z1", order=0)
        TrainingSlot.objects.create(
            plan=first_plan, date=date(2026, 10, 13), slot_index=2
        )
        tuesday_slot = TrainingSlot.objects.create(
            plan=second_plan, date=date(2026, 10, 13), slot_index=2
        )
        tuesday_slot.segments.create(type="CORE", text="5*1000m z3", order=0)
        self.client.force_login(user)

        response = self.client.get(
            f"/flex-planner/?start=2026-10-12&weeks=1&athletes={athlete.id}"
        )

        self.assertEqual(response.status_code, 200)
        pm_cells = response.context["week_rows"][0]["athlete_rows"][0]["pm_cells"]
        self.assertEqual(pm_cells[0]["slot"].core_text(), "40' z1")
        self.assertEqual(pm_cells[0]["plan_id"], first_plan.id)
        self.assertEqual(pm_cells[1]["slot"].core_text(), "5*1000m z3")
        self.assertEqual(pm_cells[1]["plan_id"], second_plan.id)

    def test_flex_keeps_trainer_plan_id_for_copying_source_training(self):
        user = get_user_model().objects.create_user(
            username="trainer-source-copy-coach",
            password="secret",
            is_staff=True,
        )
        athlete = Athlete.objects.create(
            owner=user,
            name="Trainer Source Copy Athlete",
            birth_year=2000,
            gender="X",
        )
        trainer_plan = TrainingPlan.objects.create(
            owner=user,
            name="Trainer source plan",
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
            weekday=0,
            slot_index=1,
            mode=AthleteBasePlanningSlot.MODE_TRAINER,
            trainer_plan=trainer_plan,
        )
        source_slot = TrainingSlot.objects.create(
            plan=trainer_plan,
            date=date(2026, 10, 12),
            slot_index=1,
        )
        source_slot.segments.create(type="CORE", text="1200m z2", order=0)
        self.client.force_login(user)

        response = self.client.get(
            f"/flex-planner/?start=2026-10-12&weeks=1&athletes={athlete.id}"
        )

        self.assertEqual(response.status_code, 200)
        target_cell = response.context["week_rows"][0]["athlete_rows"][0]["am_cells"][0]
        self.assertEqual(target_cell["plan_id"], trainer_plan.id)

        copy_response = self.client.post(
            f"/slot-copy/2026/10/12/1/?plan={trainer_plan.id}&athlete={athlete.id}&source=flex"
        )
        self.assertEqual(copy_response.status_code, 200)
        clipboard = self.client.session.get("training_clipboard")
        self.assertEqual(clipboard["segments"][0]["text"], "1200m z2")

    def test_flex_shows_same_base_trainer_plan_for_multiple_athletes(self):
        user = get_user_model().objects.create_user(
            username="multi-base-flex-coach",
            password="secret",
            is_staff=True,
        )
        athletes = [
            Athlete.objects.create(owner=user, name=f"Multi Base Athlete {index}", birth_year=2000, gender="X")
            for index in (1, 2)
        ]
        trainer_plan = TrainingPlan.objects.create(
            owner=user,
            name="Shared base trainer plan",
            plan_kind=TrainingPlan.PLAN_KIND_TRAINER,
            start_date=date(2026, 10, 1),
            end_date=date(2026, 10, 12),
        )
        day = date(2026, 10, 13)
        source_slot = TrainingSlot.objects.create(
            plan=trainer_plan,
            date=day,
            slot_index=2,
        )
        source_slot.segments.create(type="CORE", text="1600m z2", zone="2", order=1)
        for athlete in athletes:
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
                weekday=day.weekday(),
                slot_index=2,
                mode=AthleteBasePlanningSlot.MODE_TRAINER,
                trainer_plan=trainer_plan,
            )

        self.client.force_login(user)
        response = self.client.get(
            f"/flex-planner/?start={day.isoformat()}&weeks=1&athletes={athletes[0].id}&athletes={athletes[1].id}"
        )
        self.assertEqual(response.status_code, 200)
        rows = response.context["week_rows"][0]["athlete_rows"]
        self.assertEqual(len(rows), 2)
        for row in rows:
            cell = next(cell for cell in row["pm_cells"] if cell["day"] == day)
            self.assertIsNotNone(cell["slot"])
            self.assertEqual(cell["slot"].core_text(), "1600m z2")

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

    def test_athlete_year_wucd_distance_without_zone_defaults_to_z1(self):
        _, plan, athlete = self._user_plan_and_athlete()

        response = self.client.post(
            f"/athlete/year/?year=2026&athlete={athlete.id}",
            {
                "date": "2026-01-08",
                "slot_index": "1",
                "plan": str(plan.id),
                "wu_text": "1000m",
                "slot_text": "1000m z3",
                "core_text": "1000m z3",
                "cd_text": "800m",
            },
        )

        self.assertEqual(response.status_code, 200)
        slot = TrainingSlot.objects.get(plan=plan, athlete=athlete, date="2026-01-08", slot_index=1)
        segments = list(slot.segments.order_by("order", "id"))
        self.assertEqual([seg.type for seg in segments], ["WU", "CORE", "CD"])
        self.assertEqual(segments[0].text, "1000m")
        self.assertEqual(segments[0].zone, "1")
        self.assertEqual(segments[0].distance_m, 1000)
        self.assertEqual(segments[-1].text, "800m")
        self.assertEqual(segments[-1].zone, "1")
        self.assertEqual(segments[-1].distance_m, 800)

    def test_slot_modal_wucd_distance_without_zone_defaults_to_z1(self):
        _, plan, athlete = self._user_plan_and_athlete()

        response = self.client.post(
            f"/slot-modal/2026/01/08/1/?plan={plan.id}&athlete={athlete.id}",
            {
                "plan": str(plan.id),
                "athlete": str(athlete.id),
                "wu_text": "1000m",
                "core_text": "1000m z3",
                "cd_text": "800m",
            },
        )

        self.assertEqual(response.status_code, 200)
        slot = TrainingSlot.objects.get(plan=plan, athlete=athlete, date="2026-01-08", slot_index=1)
        segments = list(slot.segments.order_by("order", "id"))
        self.assertEqual([seg.type for seg in segments], ["WU", "CORE", "CD"])
        self.assertEqual(segments[0].zone, "1")
        self.assertEqual(segments[0].distance_m, 1000)
        self.assertEqual(segments[-1].zone, "1")
        self.assertEqual(segments[-1].distance_m, 800)

    def test_athlete_year_can_save_flex_override_outside_flex_plan_date_range(self):
        user = get_user_model().objects.create_user(
            username="ayc-flex-range-coach",
            password="secret",
            is_staff=True,
        )
        athlete = Athlete.objects.create(
            owner=user,
            name="AYC Flex Range Athlete",
            birth_year=2000,
            gender="X",
        )
        flex_plan = TrainingPlan.objects.create(
            owner=user,
            name="Flex Planner old range",
            start_date=date(2026, 1, 1),
            end_date=date(2026, 1, 7),
        )
        self.client.force_login(user)

        response = self.client.post(
            f"/athlete/year/?year=2026&athlete={athlete.id}",
            {
                "date": "2026-03-10",
                "slot_index": "1",
                "plan": str(flex_plan.id),
                "slot_text": "1000m z3",
                "core_text": "1000m z3",
            },
        )

        self.assertEqual(response.status_code, 200)
        slot = TrainingSlot.objects.get(plan=flex_plan, athlete=athlete, date="2026-03-10", slot_index=1)
        self.assertEqual(slot.core_text(), "1000m z3")

    def test_flex_delete_blocks_base_planning_training_in_athlete_year_calendar(self):
        user = get_user_model().objects.create_user(
            username="ayc-flex-delete-coach",
            password="secret",
            is_staff=True,
        )
        athlete = Athlete.objects.create(
            owner=user,
            name="Brenn Style Athlete",
            birth_year=2010,
            gender="M",
        )
        flex_plan = TrainingPlan.objects.create(owner=user, name=f"Flex Planner {user.id}")
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
            weekday=0,
            slot_index=1,
            mode=AthleteBasePlanningSlot.MODE_TRAINING,
            training_text="5 km z2",
        )
        flex_slot = TrainingSlot.objects.create(
            plan=flex_plan,
            athlete=athlete,
            date=date(2026, 9, 21),
            slot_index=1,
        )
        flex_slot.segments.create(type="CORE", text="3 km z3", zone="3", order=1)
        self.client.force_login(user)

        response = self.client.post(
            f"/slot-modal/2026/09/21/1/?plan={flex_plan.id}&athlete={athlete.id}&source=flex",
            {"action": "delete"},
        )

        self.assertEqual(response.status_code, 200)
        empty_override = TrainingSlot.objects.get(
            plan=flex_plan,
            athlete=athlete,
            date=date(2026, 9, 21),
            slot_index=1,
        )
        self.assertFalse(empty_override.segments.exists())

        page = self.client.get(f"/athlete/year/?year=2026&athlete={athlete.id}&hide=none")

        self.assertEqual(page.status_code, 200)
        target_cell = None
        for week in page.context["week_rows"]:
            for cell in week["cells1"]:
                if cell["day"] == date(2026, 9, 21):
                    target_cell = cell
                    break
            if target_cell:
                break
        self.assertIsNotNone(target_cell)
        self.assertIsNone(target_cell["slot"])

    def test_athlete_year_uses_same_active_plan_as_flex_for_standard_strength(self):
        user = get_user_model().objects.create_user(
            username="ayc-strength-plan-coach",
            password="secret",
            is_staff=True,
        )
        athlete = Athlete.objects.create(
            owner=user,
            name="AYC Strength Plan Athlete",
            birth_year=2000,
            gender="X",
        )
        active_plan = TrainingPlan.objects.create(owner=user, name="Active athlete plan")
        PlanMembership.objects.create(plan=active_plan, athlete=athlete)
        TrainingPlan.objects.create(owner=user, name=f"Flex Planner {user.id}")
        program = StandardStrengthProgram.objects.create(owner=user, name="Monday strength")
        day = date(2026, 10, 12)
        active_slot = TrainingSlot.objects.create(plan=active_plan, date=day, slot_index=1)
        active_slot.segments.create(
            type="MOB",
            text=program.name,
            standard_strength_program=program,
            order=1,
        )

        old_plan = TrainingPlan.objects.create(owner=user, name="Old unrelated plan")
        TrainingSlot.objects.create(
            plan=old_plan,
            athlete=athlete,
            date=day,
            slot_index=1,
        )
        self.client.force_login(user)

        flex_page = self.client.get(
            f"/flex-planner/?start={day.isoformat()}&weeks=1&athletes={athlete.id}"
        )
        flex_cell = next(
            cell
            for week in flex_page.context["week_rows"]
            for cell in week["athlete_rows"][0]["am_cells"]
            if cell["day"] == day
        )
        self.assertEqual(flex_cell["slot"].plan_id, active_plan.id)
        self.assertEqual(
            flex_cell["slot"].segments.all()[0].standard_strength_program,
            program,
        )

        ayc_page = self.client.get(
            f"/athlete/year/?year={day.year}&athlete={athlete.id}&hide=none"
        )
        ayc_cell = next(
            cell
            for week in ayc_page.context["week_rows"]
            for cell in week["cells1"]
            if cell["day"] == day
        )
        self.assertEqual(ayc_cell["slot"].id, active_slot.id)
        self.assertContains(ayc_page, "Monday strength")

    def test_ayc_override_is_visible_in_ayc_and_flex_when_plans_overlap(self):
        user = get_user_model().objects.create_user(
            username="ayc-visible-override-coach",
            password="secret",
            is_staff=True,
        )
        athlete = Athlete.objects.create(
            owner=user,
            name="Visible Override Athlete",
            birth_year=2000,
            gender="X",
        )
        old_plan = TrainingPlan.objects.create(owner=user, name="A old plan")
        current_plan = TrainingPlan.objects.create(owner=user, name="Z current plan")
        PlanMembership.objects.create(plan=old_plan, athlete=athlete)
        PlanMembership.objects.create(plan=current_plan, athlete=athlete)
        day = date.today()
        old_slot = TrainingSlot.objects.create(plan=old_plan, date=day, slot_index=1)
        old_slot.segments.create(type="CORE", text="800m z1", zone="1", order=1)
        current_slot = TrainingSlot.objects.create(plan=current_plan, date=day, slot_index=1)
        current_slot.segments.create(type="CORE", text="1000m z2", zone="2", order=1)

        self.client.force_login(user)
        save_response = self.client.post(
            f"/athlete/year/?year={day.year}&athlete={athlete.id}",
            {
                "date": day.isoformat(),
                "slot_index": "1",
                "plan": str(current_plan.id),
                "slot_text": "1200m z3",
                "core_text": "1200m z3",
            },
        )
        self.assertEqual(save_response.status_code, 200)

        ayc_page = self.client.get(
            f"/athlete/year/?year={day.year}&athlete={athlete.id}&hide=none"
        )
        ayc_cell = next(
            cell
            for week in ayc_page.context["week_rows"]
            for cell in week["cells1"]
            if cell["day"] == day
        )
        self.assertEqual(ayc_cell["slot"].plan_id, current_plan.id)
        self.assertEqual(ayc_cell["slot"].core_text(), "1200m z3")

        flex_page = self.client.get(
            f"/flex-planner/?start={day.isoformat()}&weeks=1&athletes={athlete.id}"
        )
        flex_cell = next(
            cell
            for week in flex_page.context["week_rows"]
            for cell in week["athlete_rows"][0]["am_cells"]
            if cell["day"] == day
        )
        self.assertEqual(flex_cell["plan"].id, current_plan.id)
        self.assertIsNotNone(flex_cell["plan_id"])
        self.assertEqual(flex_cell["slot"].plan_id, current_plan.id)
        self.assertEqual(flex_cell["slot"].core_text(), "1200m z3")

    def test_flex_keeps_targeted_override_visible_after_source_plan_end(self):
        user = get_user_model().objects.create_user(
            username="flex-override-after-plan-end-coach",
            password="secret",
            is_staff=True,
        )
        athlete = Athlete.objects.create(
            owner=user,
            name="Override After Plan End Athlete",
            birth_year=2000,
            gender="X",
        )
        day = date(2026, 10, 13)
        plan = TrainingPlan.objects.create(
            owner=user,
            name="Short source plan",
            start_date=date(2026, 10, 1),
            end_date=date(2026, 10, 12),
        )
        PlanMembership.objects.create(plan=plan, athlete=athlete)
        override = TrainingSlot.objects.create(
            plan=plan,
            athlete=athlete,
            date=day,
            slot_index=2,
        )
        override.segments.create(type="CORE", text="2000m z3", zone="3", order=1)

        self.client.force_login(user)
        ayc_page = self.client.get(
            f"/athlete/year/?year={day.year}&athlete={athlete.id}&hide=none"
        )
        ayc_cell = next(
            cell
            for week in ayc_page.context["week_rows"]
            for cell in week["cells2"]
            if cell["day"] == day
        )
        self.assertIsNotNone(ayc_cell["slot"])
        self.assertEqual(ayc_cell["slot"].core_text(), "2000m z3")

        flex_page = self.client.get(
            f"/flex-planner/?start={day.isoformat()}&weeks=1&athletes={athlete.id}"
        )
        flex_cell = next(
            cell
            for week in flex_page.context["week_rows"]
            for cell in week["athlete_rows"][0]["pm_cells"]
            if cell["day"] == day
        )
        self.assertIsNotNone(flex_cell["slot"])
        self.assertEqual(flex_cell["slot"].core_text(), "2000m z3")

    def test_flex_uses_explicit_athlete_slot_without_membership(self):
        user = get_user_model().objects.create_user(
            username="flex-explicit-slot-coach",
            password="secret",
            is_staff=True,
        )
        athlete = Athlete.objects.create(owner=user, name="Explicit Slot Athlete", birth_year=2000, gender="X")
        day = date(2026, 10, 13)
        plan = TrainingPlan.objects.create(owner=user, name="Explicit source plan")
        slot = TrainingSlot.objects.create(plan=plan, athlete=athlete, date=day, slot_index=2)
        slot.segments.create(type="CORE", text="5*1000m z2", zone="2", order=1)
        self.client.force_login(user)

        page = self.client.get(f"/flex-planner/?start={day.isoformat()}&weeks=1&athletes={athlete.id}")
        cell = next(
            cell
            for week in page.context["week_rows"]
            for cell in week["athlete_rows"][0]["pm_cells"]
            if cell["day"] == day
        )
        self.assertIsNotNone(cell["slot"])
        self.assertEqual(cell["slot"].core_text(), "5*1000m z2")

    def test_ayc_override_is_visible_for_base_assigned_trainer_plan(self):
        user = get_user_model().objects.create_user(
            username="ayc-base-override-coach",
            password="secret",
            is_staff=True,
        )
        athlete = Athlete.objects.create(
            owner=user,
            name="Base Override Athlete",
            birth_year=2000,
            gender="X",
        )
        trainer_plan = TrainingPlan.objects.create(owner=user, name="Base trainer plan")
        block = AthleteBasePlanningBlock.objects.create(
            athlete=athlete,
            planning_kind=AthleteBasePlanningBlock.KIND_BASE,
            start_month=1,
            start_day=1,
            end_month=12,
            end_day=31,
        )
        day = date.today()
        AthleteBasePlanningSlot.objects.create(
            block=block,
            weekday=day.weekday(),
            slot_index=1,
            mode=AthleteBasePlanningSlot.MODE_TRAINER,
            trainer_plan=trainer_plan,
        )
        base_slot = TrainingSlot.objects.create(plan=trainer_plan, date=day, slot_index=1)
        base_slot.segments.create(type="CORE", text="1000m z2", zone="2", order=1)

        self.client.force_login(user)
        save_response = self.client.post(
            f"/athlete/year/?year={day.year}&athlete={athlete.id}",
            {
                "date": day.isoformat(),
                "slot_index": "1",
                "plan": str(trainer_plan.id),
                "slot_text": "1200m z3",
                "core_text": "1200m z3",
            },
        )
        self.assertEqual(save_response.status_code, 200)
        self.assertTrue(
            TrainingSlot.objects.filter(
                plan=trainer_plan,
                athlete=athlete,
                date=day,
                slot_index=1,
            ).exists()
        )

        ayc_page = self.client.get(f"/athlete/year/?year={day.year}&athlete={athlete.id}&hide=none")
        ayc_cell = next(
            cell
            for week in ayc_page.context["week_rows"]
            for cell in week["cells1"]
            if cell["day"] == day
        )
        self.assertEqual(ayc_cell["slot"].plan_id, trainer_plan.id)
        self.assertEqual(ayc_cell["slot"].core_text(), "1200m z3")

        flex_page = self.client.get(
            f"/flex-planner/?start={day.isoformat()}&weeks=1&athletes={athlete.id}"
        )
        flex_cell = next(
            cell
            for week in flex_page.context["week_rows"]
            for cell in week["athlete_rows"][0]["am_cells"]
            if cell["day"] == day
        )
        self.assertEqual(flex_cell["slot"].plan_id, trainer_plan.id)
        self.assertEqual(flex_cell["slot"].core_text(), "1200m z3")

    def test_flex_hides_trainer_slot_when_base_planning_is_rest(self):
        user = get_user_model().objects.create_user(
            username="flex-rest-base-coach",
            password="secret",
            is_staff=True,
        )
        athlete = Athlete.objects.create(
            owner=user,
            name="Rest Base Athlete",
            birth_year=2000,
            gender="X",
        )
        trainer_plan = TrainingPlan.objects.create(owner=user, name="Rest override plan")
        PlanMembership.objects.create(plan=trainer_plan, athlete=athlete)
        day = date.today()
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
            weekday=day.weekday(),
            slot_index=1,
            mode=AthleteBasePlanningSlot.MODE_REST,
        )
        slot = TrainingSlot.objects.create(plan=trainer_plan, date=day, slot_index=1)
        slot.segments.create(type="CORE", text="1000m z2", zone="2", order=1)

        self.client.force_login(user)
        flex_page = self.client.get(
            f"/flex-planner/?start={day.isoformat()}&weeks=1&athletes={athlete.id}"
        )
        flex_cell = next(
            cell
            for week in flex_page.context["week_rows"]
            for cell in week["athlete_rows"][0]["am_cells"]
            if cell["day"] == day
        )
        self.assertIsNone(flex_cell["slot"])

        ayc_page = self.client.get(
            f"/athlete/year/?year={day.year}&athlete={athlete.id}&hide=none"
        )
        ayc_cell = next(
            cell
            for week in ayc_page.context["week_rows"]
            for cell in week["cells1"]
            if cell["day"] == day
        )
        self.assertIsNone(ayc_cell["slot"])

        personal_override = TrainingSlot.objects.create(
            plan=trainer_plan,
            athlete=athlete,
            date=day,
            slot_index=1,
        )
        personal_override.segments.create(
            type="CORE", text="800m z3", zone="3", order=1
        )
        ayc_with_personal_override = self.client.get(
            f"/athlete/year/?year={day.year}&athlete={athlete.id}&hide=none"
        )
        override_cell = next(
            cell
            for week in ayc_with_personal_override.context["week_rows"]
            for cell in week["cells1"]
            if cell["day"] == day
        )
        self.assertEqual(override_cell["slot"].core_text(), "800m z3")

    def test_flex_personal_copy_overrides_base_planning_rest(self):
        user = get_user_model().objects.create_user(
            username="flex-copy-over-rest-coach",
            password="secret",
            is_staff=True,
        )
        athlete = Athlete.objects.create(
            owner=user,
            name="Extra Day Copy Athlete",
            birth_year=2000,
            gender="X",
        )
        trainer_plan = TrainingPlan.objects.create(
            owner=user,
            name="Own trainer plan for rest-day copy",
            plan_kind=TrainingPlan.PLAN_KIND_TRAINER,
        )
        PlanMembership.objects.create(plan=trainer_plan, athlete=athlete)
        source_day = date(2026, 11, 19)
        target_day = date(2026, 11, 22)
        source_slot = TrainingSlot.objects.create(
            plan=trainer_plan,
            date=source_day,
            slot_index=2,
        )
        source_slot.segments.create(type="CORE", text="8*400m z4", order=0)
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
            weekday=target_day.weekday(),
            slot_index=2,
            mode=AthleteBasePlanningSlot.MODE_REST,
        )

        self.client.force_login(user)
        copy_response = self.client.post(
            f"/slot-copy/{source_day.year}/{source_day.month}/{source_day.day}/2/"
            f"?plan={trainer_plan.id}&athlete={athlete.id}&source=flex"
        )
        self.assertEqual(copy_response.status_code, 200)
        paste_response = self.client.post(
            f"/slot-paste/{target_day.year}/{target_day.month}/{target_day.day}/2/"
            f"?plan={trainer_plan.id}&athlete={athlete.id}&source=flex"
        )
        self.assertEqual(paste_response.status_code, 200)

        flex_page = self.client.get(
            f"/flex-planner/?start=2026-11-16&weeks=1&athletes={athlete.id}"
        )
        flex_cell = next(
            cell
            for week in flex_page.context["week_rows"]
            for cell in week["athlete_rows"][0]["pm_cells"]
            if cell["day"] == target_day
        )
        self.assertEqual(flex_cell["slot"].core_text(), "8*400m z4")

    def test_athlete_year_shows_pending_evaluation_reminders_for_past_week(self):
        coach = get_user_model().objects.create_user(
            username="ayc-reminder-coach",
            password="secret",
            is_staff=True,
        )
        athlete_user = get_user_model().objects.create_user(
            username="Reminder Athlete",
            password="secret",
        )
        athlete = Athlete.objects.create(
            owner=coach,
            name="Reminder Athlete",
            birth_year=2000,
            gender="X",
        )
        plan = TrainingPlan.objects.create(owner=coach, name="Reminder plan")
        PlanMembership.objects.create(plan=plan, athlete=athlete)
        yesterday = date.today() - timedelta(days=1)
        today = date.today()
        old_day = date.today() - timedelta(days=8)
        completed_day = date.today() - timedelta(days=2)

        for day, text in (
            (yesterday, "Yesterday reminder training"),
            (today, "Today should wait"),
            (old_day, "Old should be ignored"),
            (completed_day, "Completed should be ignored"),
        ):
            slot = TrainingSlot.objects.create(plan=plan, date=day, slot_index=1)
            slot.segments.create(type="CORE", text=text, zone="2", order=1)

        AthleteDayCheck.objects.create(
            athlete=athlete,
            date=completed_day,
            slot_index=1,
            status=AthleteDayCheck.STATUS_DONE_AS_PLANNED,
            rpe=5,
            comment="Done already",
            updated_by=athlete_user,
        )

        self.client.force_login(athlete_user)
        response = self.client.get(f"/athlete/year/?year={today.year}")

        reminders = response.context["pending_evaluation_reminders"]
        self.assertEqual(len(reminders), 1)
        self.assertEqual(reminders[0]["date"], yesterday)
        self.assertEqual(reminders[0]["slot_index"], 1)
        self.assertEqual(reminders[0]["plan_text"], "Yesterday reminder training")
        self.assertContains(response, "Open evaluations")
        self.assertContains(response, "Yesterday reminder training")
        self.assertContains(response, f'data-evaluation-date="{yesterday:%Y-%m-%d}"', html=False)
        self.assertNotContains(response, f'data-evaluation-date="{today:%Y-%m-%d}"', html=False)
        self.assertNotContains(response, f'data-evaluation-date="{old_day:%Y-%m-%d}"', html=False)
        self.assertNotContains(response, f'data-evaluation-date="{completed_day:%Y-%m-%d}"', html=False)

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

    def test_authenticated_user_can_change_password_with_complexity_rules(self):
        user = get_user_model().objects.create_user(
            username="password-change-user", password="OldPass1!"
        )
        self.client.force_login(user)

        page = self.client.get("/password-change/")
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, "Change password")
        self.assertContains(page, "special character")

        invalid = self.client.post(
            "/password-change/",
            {
                "old_password": "OldPass1!",
                "new_password1": "short",
                "new_password2": "short",
            },
        )
        self.assertEqual(invalid.status_code, 200)
        self.assertContains(invalid, "at least 8 characters")

        changed = self.client.post(
            "/password-change/",
            {
                "old_password": "OldPass1!",
                "new_password1": "NewPass2!",
                "new_password2": "NewPass2!",
            },
        )
        self.assertRedirects(changed, "/password-change/done/")
        user.refresh_from_db()
        self.assertTrue(user.check_password("NewPass2!"))

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

    def test_athlete_with_base_planning_rights_can_edit_and_only_use_own_trainers_groups(self):
        coach = get_user_model().objects.create_user(
            username="base-rights-coach", password="secret"
        )
        other_coach = get_user_model().objects.create_user(
            username="other-base-rights-coach", password="secret"
        )
        athlete_user = get_user_model().objects.create_user(
            username="base-rights-athlete", password="secret"
        )
        athlete = Athlete.objects.create(
            owner=coach,
            name="base-rights-athlete",
            birth_year=2000,
            gender="X",
            can_change_base_planning=True,
        )
        own_plan = TrainingPlan.objects.create(
            owner=coach,
            name="Own athlete group",
            plan_kind=TrainingPlan.PLAN_KIND_TRAINER,
        )
        foreign_plan = TrainingPlan.objects.create(
            owner=other_coach,
            name="Foreign athlete group",
            plan_kind=TrainingPlan.PLAN_KIND_TRAINER,
        )
        block = AthleteBasePlanningBlock.objects.create(
            athlete=athlete,
            planning_kind=AthleteBasePlanningBlock.KIND_BASE,
            label="Year",
            start_month=1,
            start_day=1,
            end_month=12,
            end_day=31,
        )
        slot = AthleteBasePlanningSlot.objects.create(
            block=block,
            weekday=0,
            slot_index=1,
            mode=AthleteBasePlanningSlot.MODE_REST,
        )

        self.client.force_login(athlete_user)
        page = self.client.get(
            f"/planning/base/?athlete={athlete.id}&embedded=1&kind=base"
        )
        self.assertEqual(page.status_code, 200)
        self.assertNotContains(page, "View only")
        self.assertContains(page, own_plan.name)
        self.assertNotContains(page, foreign_plan.name)

        response = self.client.post(
            f"/planning/base/?athlete={athlete.id}&embedded=1&kind=base",
            {
                "athlete_id": str(athlete.id),
                "kind": "base",
                "embedded": "1",
                "action": "autosave_slot",
                "slot_id": str(slot.id),
                "mode": AthleteBasePlanningSlot.MODE_TRAINER,
                "trainer_plan": str(own_plan.id),
            },
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(response.status_code, 200, response.content.decode())
        edited_slot = AthleteBasePlanningSlot.objects.get(id=response.json()["slot_id"])
        self.assertEqual(edited_slot.trainer_plan_id, own_plan.id)

        response = self.client.post(
            f"/planning/base/?athlete={athlete.id}&embedded=1&kind=base",
            {
                "athlete_id": str(athlete.id),
                "kind": "base",
                "embedded": "1",
                "action": "autosave_slot",
                "slot_id": str(edited_slot.id),
                "mode": AthleteBasePlanningSlot.MODE_TRAINER,
                "trainer_plan": str(foreign_plan.id),
            },
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(response.status_code, 200, response.content.decode())
        edited_slot.refresh_from_db()
        self.assertIsNone(edited_slot.trainer_plan_id)
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
        self.assertIn('document.body.appendChild(modalEl);', template_source)

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

        not_done_response = self.client.post(
            f"/athlete/year/?year={future_day.year}&athlete={athlete.id}",
            {
                "date": future_day.isoformat(),
                "slot_index": "2",
                "report_submit": "1",
                "check_status": "not_done",
                "rpe": "",
                "report_comment": "Had to rest",
            },
        )
        self.assertEqual(not_done_response.status_code, 200)
        not_done_report = AthleteDayCheck.objects.get(
            athlete=athlete, date=future_day, slot_index=2
        )
        self.assertEqual(not_done_report.rpe, 0)
        self.assertEqual(not_done_report.comment, "Had to rest")

        desktop_page = self.client.get(
            f"/athlete/year/?year={future_day.year}&athlete={athlete.id}"
        )
        desktop_vitals_script = desktop_page.content.decode().split(
            "function postDailyVital(el)", 1
        )[1].split("</script>", 1)[0]
        self.assertNotIn("window.location.reload();", desktop_vitals_script)
        self.assertIn('"X-Requested-With": "XMLHttpRequest"', desktop_vitals_script)

    def test_not_done_evaluation_defaults_rpe_to_zero_and_keeps_comment_minimum(self):
        source = get_template("core/athlete_year_calendar.html").template.source

        self.assertIn('function setNotDoneRpe(statusId, rpeId)', source)
        self.assertIn('setVal(rpeId, "0")', source)
        self.assertIn('setNotDoneRpe("reportT1Status", "reportT1Rpe")', source)
        self.assertIn('setNotDoneRpe("reportT2Status", "reportT2Rpe")', source)
        self.assertIn('comment.length >= 4', source)

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

    def test_edit_access_coach_can_edit_shared_trainer_planning_slot(self):
        owner = get_user_model().objects.create_user(
            username="slot-owner", password="secret", is_staff=True
        )
        shared_coach = get_user_model().objects.create_user(
            username="slot-edit-coach", password="secret", is_staff=True
        )
        plan = TrainingPlan.objects.create(
            owner=owner,
            name="Shared trainer plan",
            plan_kind=TrainingPlan.PLAN_KIND_TRAINER,
        )
        CoachAccess.objects.create(owner=owner, grantee=shared_coach, can_edit=True)
        self.client.force_login(shared_coach)
        self.client.post("/", {"coach_view_owner": str(owner.id)})

        day = date.today()
        response = self.client.post(
            f"/slot-modal/{day.year}/{day.month}/{day.day}/1/?plan={plan.id}",
            {
                "core_text": "1000m z2",
            },
        )

        self.assertEqual(response.status_code, 200)
        slot = TrainingSlot.objects.get(plan=plan, athlete__isnull=True, date=day, slot_index=1)
        self.assertEqual(slot.core_text(), "1000m z2")

    def test_edit_access_coach_can_open_and_save_shared_flex_slot(self):
        owner = get_user_model().objects.create_user(
            username="flex-owner", password="secret", is_staff=True
        )
        shared_coach = get_user_model().objects.create_user(
            username="flex-edit-coach", password="secret", is_staff=True
        )
        athlete = Athlete.objects.create(
            owner=owner,
            name="Shared Flex Athlete",
            birth_year=2000,
            gender="X",
            is_private=False,
        )
        plan = TrainingPlan.objects.create(owner=owner, name="Flex Planner shared")
        CoachAccess.objects.create(owner=owner, grantee=shared_coach, can_edit=True)
        self.client.force_login(shared_coach)
        self.client.post("/", {"coach_view_owner": str(owner.id)})

        day = date.today()
        open_response = self.client.get(
            f"/slot-modal/{day.year}/{day.month}/{day.day}/1/?plan={plan.id}&athlete={athlete.id}&source=flex"
        )
        self.assertEqual(open_response.status_code, 200)
        self.assertContains(open_response, "Plan training")

        save_response = self.client.post(
            f"/slot-modal/{day.year}/{day.month}/{day.day}/1/?plan={plan.id}&athlete={athlete.id}&source=flex",
            {
                "plan": str(plan.id),
                "athlete": str(athlete.id),
                "source": "flex",
                "core_text": "1000m z2",
            },
        )
        self.assertEqual(save_response.status_code, 200)
        slot = TrainingSlot.objects.get(plan=plan, athlete=athlete, date=day, slot_index=1)
        self.assertEqual(slot.core_text(), "1000m z2")

    def test_edit_access_coach_can_copy_shared_flex_slot(self):
        owner = get_user_model().objects.create_user(
            username="flex-copy-owner", password="secret", is_staff=True
        )
        shared_coach = get_user_model().objects.create_user(
            username="flex-copy-coach", password="secret", is_staff=True
        )
        source_athlete = Athlete.objects.create(
            owner=owner,
            name="Flex Copy Source",
            birth_year=2000,
            gender="X",
            is_private=False,
        )
        target_athlete = Athlete.objects.create(
            owner=owner,
            name="Flex Copy Target",
            birth_year=2000,
            gender="X",
            is_private=False,
        )
        plan = TrainingPlan.objects.create(
            owner=owner,
            name="Shared flex copy source",
            plan_kind=TrainingPlan.PLAN_KIND_TRAINER,
        )
        PlanMembership.objects.create(plan=plan, athlete=source_athlete)
        PlanMembership.objects.create(plan=plan, athlete=target_athlete)
        source_day = date.today()
        target_day = source_day + timedelta(days=1)
        source_slot = TrainingSlot.objects.create(
            plan=plan,
            date=source_day,
            slot_index=1,
        )
        source_slot.segments.create(type="CORE", text="1000m z2", order=0)
        CoachAccess.objects.create(owner=owner, grantee=shared_coach, can_edit=True)

        self.client.force_login(shared_coach)
        self.client.post("/", {"coach_view_owner": str(owner.id)})

        copy_response = self.client.post(
            f"/slot-copy/{source_day.year}/{source_day.month}/{source_day.day}/1/"
            f"?plan={plan.id}&athlete={source_athlete.id}&source=flex"
        )
        self.assertEqual(copy_response.status_code, 200)

        paste_response = self.client.post(
            f"/slot-paste/{target_day.year}/{target_day.month}/{target_day.day}/1/"
            f"?plan={plan.id}&athlete={target_athlete.id}&source=flex"
        )
        self.assertEqual(paste_response.status_code, 200)

        flex_plan = TrainingPlan.objects.get(owner=owner, name__startswith="Flex Planner")
        copied_slot = TrainingSlot.objects.get(
            plan=flex_plan,
            athlete=target_athlete,
            date=target_day,
            slot_index=1,
        )
        self.assertEqual(copied_slot.core_text(), "1000m z2")

    def test_edit_access_coach_can_copy_slot_when_flex_cell_points_to_flex_plan(self):
        owner = get_user_model().objects.create_user(
            username="flex-copy-flex-owner", password="secret", is_staff=True
        )
        shared_coach = get_user_model().objects.create_user(
            username="flex-copy-flex-coach", password="secret", is_staff=True
        )
        source_athlete = Athlete.objects.create(
            owner=owner,
            name="Flex Override Source",
            birth_year=2000,
            gender="X",
            is_private=False,
        )
        target_athlete = Athlete.objects.create(
            owner=owner,
            name="Flex Override Target",
            birth_year=2000,
            gender="X",
            is_private=False,
        )
        flex_plan = TrainingPlan.objects.create(owner=owner, name="Flex Planner shared overrides")
        source_day = date.today()
        target_day = source_day + timedelta(days=1)
        source_slot = TrainingSlot.objects.create(
            plan=flex_plan,
            athlete=source_athlete,
            date=source_day,
            slot_index=1,
        )
        source_slot.segments.create(type="CORE", text="800m z3", order=0)
        CoachAccess.objects.create(owner=owner, grantee=shared_coach, can_edit=True)

        self.client.force_login(shared_coach)
        self.client.post("/", {"coach_view_owner": str(owner.id)})

        copy_response = self.client.post(
            f"/slot-copy/{source_day.year}/{source_day.month}/{source_day.day}/1/"
            f"?plan={flex_plan.id}&athlete={source_athlete.id}&source=flex"
        )
        self.assertEqual(copy_response.status_code, 200, copy_response.content.decode())

        paste_response = self.client.post(
            f"/slot-paste/{target_day.year}/{target_day.month}/{target_day.day}/1/"
            f"?plan={flex_plan.id}&athlete={target_athlete.id}&source=flex"
        )
        self.assertEqual(paste_response.status_code, 200, paste_response.content.decode())

        copied_slot = TrainingSlot.objects.get(
            plan=flex_plan,
            athlete=target_athlete,
            date=target_day,
            slot_index=1,
        )
        self.assertEqual(copied_slot.core_text(), "800m z3")

    def test_edit_access_coach_can_copy_shared_source_for_athlete_owner(self):
        source_owner = get_user_model().objects.create_user(
            username="flex-cross-owner", password="secret", is_staff=True
        )
        athlete_owner = get_user_model().objects.create_user(
            username="flex-cross-athlete-owner", password="secret", is_staff=True
        )
        source_plan = TrainingPlan.objects.create(
            owner=source_owner,
            name="Shared trainer source",
            plan_kind=TrainingPlan.PLAN_KIND_TRAINER,
        )
        athlete = Athlete.objects.create(
            owner=athlete_owner,
            name="Cross owner athlete",
            birth_year=2000,
            gender="X",
            is_private=False,
        )
        target = Athlete.objects.create(
            owner=athlete_owner,
            name="Cross owner target",
            birth_year=2000,
            gender="X",
            is_private=False,
        )
        PlanMembership.objects.create(plan=source_plan, athlete=athlete)
        PlanMembership.objects.create(plan=source_plan, athlete=target)
        source_day = date.today()
        target_day = source_day + timedelta(days=1)
        source_slot = TrainingSlot.objects.create(
            plan=source_plan,
            date=source_day,
            slot_index=1,
        )
        source_slot.segments.create(type="CORE", text="1200m z2", order=0)
        CoachAccess.objects.create(owner=source_owner, grantee=athlete_owner, can_edit=False)

        self.client.force_login(athlete_owner)
        self.client.post(
            "/",
            {"coach_view_owner": str(source_owner.id)},
        )
        # Switch back to the athlete owner: this is the owner whose Flex
        # Planner override may be changed.
        self.client.post("/", {"coach_view_owner": str(athlete_owner.id)})

        copy_response = self.client.post(
            f"/slot-copy/{source_day.year}/{source_day.month}/{source_day.day}/1/"
            f"?plan={source_plan.id}&athlete={athlete.id}&source=flex"
        )
        self.assertEqual(copy_response.status_code, 200, copy_response.content.decode())

        paste_response = self.client.post(
            f"/slot-paste/{target_day.year}/{target_day.month}/{target_day.day}/1/"
            f"?plan={source_plan.id}&athlete={target.id}&source=flex"
        )
        self.assertEqual(paste_response.status_code, 200, paste_response.content.decode())

        flex_plan = TrainingPlan.objects.get(owner=athlete_owner, name__startswith="Flex Planner")
        copied_slot = TrainingSlot.objects.get(
            plan=flex_plan,
            athlete=target,
            date=target_day,
            slot_index=1,
        )
        self.assertEqual(copied_slot.core_text(), "1200m z2")

    def test_flex_copy_from_shared_trainer_plan_is_visible_in_active_coach_flex_view(self):
        active_coach = get_user_model().objects.create_user(
            username="flex-copy-active-coach", password="secret", is_staff=True
        )
        source_coach = get_user_model().objects.create_user(
            username="flex-copy-source-coach", password="secret", is_staff=True
        )
        athlete = Athlete.objects.create(
            owner=active_coach,
            name="Flex shared-plan copy athlete",
            birth_year=2000,
            gender="X",
        )
        source_plan = TrainingPlan.objects.create(
            owner=source_coach,
            name="Shared trainer plan for Flex copy",
            plan_kind=TrainingPlan.PLAN_KIND_TRAINER,
        )
        CoachAccess.objects.create(owner=source_coach, grantee=active_coach, can_edit=True)

        block = AthleteBasePlanningBlock.objects.create(
            athlete=athlete,
            planning_kind=AthleteBasePlanningBlock.KIND_BASE,
            start_month=1,
            start_day=1,
            end_month=12,
            end_day=31,
        )
        target_day = date(2026, 11, 22)
        AthleteBasePlanningSlot.objects.create(
            block=block,
            weekday=target_day.weekday(),
            slot_index=2,
            mode=AthleteBasePlanningSlot.MODE_TRAINER,
            trainer_plan=source_plan,
        )
        source_day = date(2026, 11, 21)
        source_slot = TrainingSlot.objects.create(
            plan=source_plan,
            date=source_day,
            slot_index=2,
        )
        source_slot.segments.create(type="CORE", text="8*400m z4", order=0)

        self.client.force_login(active_coach)
        copy_response = self.client.post(
            f"/slot-copy/{source_day.year}/{source_day.month}/{source_day.day}/2/"
            f"?plan={source_plan.id}&athlete={athlete.id}&source=flex"
        )
        self.assertEqual(copy_response.status_code, 200)
        paste_response = self.client.post(
            f"/slot-paste/{target_day.year}/{target_day.month}/{target_day.day}/2/"
            f"?plan={source_plan.id}&athlete={athlete.id}&source=flex"
        )
        self.assertEqual(paste_response.status_code, 200)

        active_flex_plan = TrainingPlan.objects.get(
            owner=active_coach, name__startswith="Flex Planner"
        )
        copied_slot = TrainingSlot.objects.get(
            plan=active_flex_plan,
            athlete=athlete,
            date=target_day,
            slot_index=2,
        )
        self.assertEqual(copied_slot.core_text(), "8*400m z4")

        response = self.client.get(
            f"/flex-planner/?start=2026-11-16&weeks=1&athletes={athlete.id}"
        )
        self.assertEqual(response.status_code, 200)
        pm_cells = response.context["week_rows"][0]["athlete_rows"][0]["pm_cells"]
        self.assertEqual(pm_cells[target_day.weekday()]["slot"].core_text(), "8*400m z4")

    def test_flex_copy_from_own_trainer_plan_to_extra_athlete_day_is_visible(self):
        coach = get_user_model().objects.create_user(
            username="flex-own-plan-copy-coach", password="secret", is_staff=True
        )
        athlete = Athlete.objects.create(
            owner=coach,
            name="Own plan extra day athlete",
            birth_year=2000,
            gender="X",
        )
        trainer_plan = TrainingPlan.objects.create(
            owner=coach,
            name="Own trainer plan for extra day copy",
            plan_kind=TrainingPlan.PLAN_KIND_TRAINER,
        )
        PlanMembership.objects.create(plan=trainer_plan, athlete=athlete)
        source_day = date(2026, 11, 19)
        target_day = date(2026, 11, 22)
        source_slot = TrainingSlot.objects.create(
            plan=trainer_plan,
            date=source_day,
            slot_index=2,
        )
        source_slot.segments.create(type="CORE", text="8*400m z4", order=0)

        self.client.force_login(coach)
        copy_response = self.client.post(
            f"/slot-copy/{source_day.year}/{source_day.month}/{source_day.day}/2/"
            f"?plan={trainer_plan.id}&athlete={athlete.id}&source=flex"
        )
        self.assertEqual(copy_response.status_code, 200)
        paste_response = self.client.post(
            f"/slot-paste/{target_day.year}/{target_day.month}/{target_day.day}/2/"
            f"?plan={trainer_plan.id}&athlete={athlete.id}&source=flex"
        )
        self.assertEqual(paste_response.status_code, 200)

        flex_plan = TrainingPlan.objects.get(owner=coach, name__startswith="Flex Planner")
        copied_slot = TrainingSlot.objects.get(
            plan=flex_plan,
            athlete=athlete,
            date=target_day,
            slot_index=2,
        )
        self.assertEqual(copied_slot.core_text(), "8*400m z4")

        response = self.client.get(
            f"/flex-planner/?start=2026-11-16&weeks=1&athletes={athlete.id}"
        )
        self.assertEqual(response.status_code, 200)
        pm_cells = response.context["week_rows"][0]["athlete_rows"][0]["pm_cells"]
        self.assertEqual(pm_cells[target_day.weekday()]["slot"].core_text(), "8*400m z4")

    def test_edit_access_coach_can_save_shared_ayc_training(self):
        owner = get_user_model().objects.create_user(
            username="ayc-shared-owner", password="secret", is_staff=True
        )
        shared_coach = get_user_model().objects.create_user(
            username="ayc-shared-edit-coach", password="secret", is_staff=True
        )
        athlete = Athlete.objects.create(
            owner=owner,
            name="Shared AYC Athlete",
            birth_year=2000,
            gender="X",
            is_private=False,
        )
        plan = TrainingPlan.objects.create(
            owner=owner,
            name="Shared AYC plan",
            plan_kind=TrainingPlan.PLAN_KIND_TRAINER,
        )
        PlanMembership.objects.create(plan=plan, athlete=athlete)
        day = date.today()
        TrainingSlot.objects.create(plan=plan, date=day, slot_index=1)
        CoachAccess.objects.create(owner=owner, grantee=shared_coach, can_edit=True)

        self.client.force_login(shared_coach)
        self.client.post("/", {"coach_view_owner": str(owner.id)})

        page = self.client.get(
            f"/athlete/year/?year={day.year}&athlete={athlete.id}"
        )
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, "Shared AYC Athlete")
        self.assertContains(page, 'var aycCoachUser = true;', html=False)

        future_day = day + timedelta(days=2)
        modal = self.client.get(
            f"/slot-modal/{future_day.year}/{future_day.month}/{future_day.day}/1/?plan={plan.id}&athlete={athlete.id}&source=athlete_year"
        )
        self.assertEqual(modal.status_code, 200)
        self.assertTrue(modal.context["athlete_year_can_edit_training"])

        response = self.client.post(
            f"/athlete/year/?year={day.year}&athlete={athlete.id}",
            {
                "date": day.isoformat(),
                "slot_index": "1",
                "plan": str(plan.id),
                "slot_text": "1000m z2",
                "core_text": "1000m z2",
            },
        )
        self.assertEqual(response.status_code, 200)
        saved = TrainingSlot.objects.get(
            plan=plan, athlete=athlete, date=day, slot_index=1
        )
        self.assertEqual(saved.core_text(), "1000m z2")

    def test_flex_modal_uses_flex_plan_when_source_plan_is_trainer_planning(self):
        owner = get_user_model().objects.create_user(
            username="flex-source-owner", password="secret", is_staff=True
        )
        shared_coach = get_user_model().objects.create_user(
            username="flex-source-edit-coach", password="secret", is_staff=True
        )
        athlete = Athlete.objects.create(
            owner=owner,
            name="Source Plan Athlete",
            birth_year=2000,
            gender="X",
            is_private=False,
        )
        source_plan = TrainingPlan.objects.create(
            owner=owner,
            name="Source trainer plan",
            plan_kind=TrainingPlan.PLAN_KIND_TRAINER,
        )
        flex_plan = TrainingPlan.objects.create(owner=owner, name="Flex Planner source owner")
        CoachAccess.objects.create(owner=owner, grantee=shared_coach, can_edit=True)
        self.client.force_login(shared_coach)
        self.client.post("/", {"coach_view_owner": str(owner.id)})

        day = date.today()
        open_response = self.client.get(
            f"/slot-modal/{day.year}/{day.month}/{day.day}/1/?plan={source_plan.id}&athlete={athlete.id}&source=flex"
        )
        self.assertEqual(open_response.status_code, 200)
        self.assertContains(open_response, f'value="{flex_plan.id}"')

        save_response = self.client.post(
            f"/slot-modal/{day.year}/{day.month}/{day.day}/1/?plan={source_plan.id}&athlete={athlete.id}&source=flex",
            {
                "plan": str(source_plan.id),
                "athlete": str(athlete.id),
                "source": "flex",
                "core_text": "1000m z3",
            },
        )
        self.assertEqual(save_response.status_code, 200)
        self.assertFalse(TrainingSlot.objects.filter(plan=source_plan, athlete=athlete).exists())
        slot = TrainingSlot.objects.get(plan=flex_plan, athlete=athlete, date=day, slot_index=1)
        self.assertEqual(slot.core_text(), "1000m z3")

    def test_edit_access_coach_can_add_wucd_to_shared_base_trainer_training_in_ayc(self):
        owner = get_user_model().objects.create_user(
            username="ayc-base-shared-owner", password="secret", is_staff=True
        )
        shared_coach = get_user_model().objects.create_user(
            username="ayc-base-shared-edit-coach", password="secret", is_staff=True
        )
        athlete = Athlete.objects.create(
            owner=owner,
            name="Shared Base AYC Athlete",
            birth_year=2000,
            gender="X",
            is_private=False,
        )
        plan = TrainingPlan.objects.create(
            owner=owner,
            name="Shared base trainer plan",
            plan_kind=TrainingPlan.PLAN_KIND_TRAINER,
        )
        day = date.today()
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
            weekday=day.weekday(),
            slot_index=1,
            mode=AthleteBasePlanningSlot.MODE_TRAINER,
            trainer_plan=plan,
        )
        source_slot = TrainingSlot.objects.create(plan=plan, date=day, slot_index=1)
        source_slot.segments.create(type="CORE", text="1000m z2", order=0)
        CoachAccess.objects.create(owner=owner, grantee=shared_coach, can_edit=True)

        self.client.force_login(shared_coach)
        self.client.post("/", {"coach_view_owner": str(owner.id)})

        response = self.client.post(
            f"/athlete/year/?year={day.year}&athlete={athlete.id}",
            {
                "date": day.isoformat(),
                "slot_index": "1",
                "plan": str(plan.id),
                "slot_text": "1000m z2",
                "wu_text": "800m",
                "core_text": "1000m z2",
                "cd_text": "600m",
            },
        )
        self.assertEqual(response.status_code, 200)
        saved = TrainingSlot.objects.get(plan=plan, athlete=athlete, date=day, slot_index=1)
        segments = list(saved.segments.order_by("order", "id"))
        self.assertEqual([segment.type for segment in segments], ["WU", "CORE", "CD"])
        self.assertEqual(segments[0].zone, "1")
        self.assertEqual(segments[-1].zone, "1")

    def test_athlete_year_modal_uses_flex_plan_when_source_plan_is_trainer_planning(self):
        owner = get_user_model().objects.create_user(
            username="ayc-source-owner", password="secret", is_staff=True
        )
        athlete = Athlete.objects.create(
            owner=owner,
            name="AYC Source Plan Athlete",
            birth_year=2000,
            gender="X",
        )
        source_plan = TrainingPlan.objects.create(
            owner=owner,
            name="AYC source trainer plan",
            plan_kind=TrainingPlan.PLAN_KIND_TRAINER,
        )
        flex_plan = TrainingPlan.objects.create(owner=owner, name="Flex Planner ayc source owner")
        self.client.force_login(owner)

        day = date.today()
        open_response = self.client.get(
            f"/slot-modal/{day.year}/{day.month}/{day.day}/2/?plan={source_plan.id}&athlete={athlete.id}&source=athlete_year"
        )
        self.assertEqual(open_response.status_code, 200)
        self.assertContains(open_response, f'value="{flex_plan.id}"')

    def test_athlete_cannot_edit_future_training_in_ayc_slot_modal(self):
        coach = get_user_model().objects.create_user(
            username="future-ayc-coach", password="secret"
        )
        athlete_user = get_user_model().objects.create_user(
            username="Future AYC Athlete", password="secret"
        )
        athlete = Athlete.objects.create(
            owner=coach, name="Future AYC Athlete", birth_year=2000, gender="X"
        )
        plan = TrainingPlan.objects.create(owner=coach, name="Future AYC plan")
        PlanMembership.objects.create(plan=plan, athlete=athlete)
        future_day = date.today() + timedelta(days=1)

        self.client.force_login(athlete_user)
        response = self.client.post(
            f"/slot-modal/{future_day:%Y/%m/%d}/1/?athlete={athlete.id}&plan={plan.id}&source=athlete_year",
            {
                "athlete": str(athlete.id),
                "plan": str(plan.id),
                "source": "athlete_year",
                "core_text": "1000m z3",
            },
        )

        self.assertEqual(response.status_code, 403)
        self.assertFalse(
            TrainingSlot.objects.filter(athlete=athlete, date=future_day, slot_index=1).exists()
        )

        past_day = date.today() - timedelta(days=1)
        empty_slot_response = self.client.post(
            f"/slot-modal/{past_day:%Y/%m/%d}/2/?athlete={athlete.id}&plan={plan.id}&source=athlete_year",
            {
                "athlete": str(athlete.id),
                "plan": str(plan.id),
                "source": "athlete_year",
                "core_text": "1000m z3",
            },
        )
        self.assertEqual(empty_slot_response.status_code, 403)
        self.assertFalse(
            TrainingSlot.objects.filter(athlete=athlete, date=past_day, slot_index=2).exists()
        )

        self.client.force_login(coach)
        coach_response = self.client.post(
            f"/slot-modal/{future_day:%Y/%m/%d}/1/?athlete={athlete.id}&plan={plan.id}&source=athlete_year",
            {
                "athlete": str(athlete.id),
                "plan": str(plan.id),
                "source": "athlete_year",
                "core_text": "1000m z3",
            },
        )
        self.assertEqual(coach_response.status_code, 200)
        self.assertTrue(
            TrainingSlot.objects.filter(athlete=athlete, date=future_day, slot_index=1).exists()
        )

    def test_athlete_with_extended_edit_rights_can_add_future_ayc_training(self):
        coach = get_user_model().objects.create_user(
            username="extended-rights-coach", password="secret"
        )
        athlete_user = get_user_model().objects.create_user(
            username="Extended Rights Athlete", password="secret"
        )
        athlete = Athlete.objects.create(
            owner=coach,
            name="Extended Rights Athlete",
            birth_year=2000,
            gender="X",
            extended_edit_rights=True,
        )
        plan = TrainingPlan.objects.create(owner=coach, name="Extended rights plan")
        future_day = date.today() + timedelta(days=1)

        self.client.force_login(athlete_user)
        response = self.client.post(
            f"/slot-modal/{future_day:%Y/%m/%d}/2/?athlete={athlete.id}&plan={plan.id}&source=athlete_year",
            {
                "athlete": str(athlete.id),
                "plan": str(plan.id),
                "source": "athlete_year",
                "core_text": "1000m z3",
            },
        )

        self.assertEqual(response.status_code, 200, response.content.decode())
        self.assertTrue(
            TrainingSlot.objects.filter(athlete=athlete, date=future_day, slot_index=2).exists()
        )

    def test_extended_rights_show_am_pm_evaluations_on_empty_future_day(self):
        coach = get_user_model().objects.create_user(
            username="empty-evaluation-coach", password="secret"
        )
        athlete_user = get_user_model().objects.create_user(
            username="Empty Evaluation Athlete", password="secret"
        )
        athlete = Athlete.objects.create(
            owner=coach,
            name="Empty Evaluation Athlete",
            birth_year=2000,
            gender="X",
            extended_edit_rights=True,
        )
        future_day = date.today() + timedelta(days=1)

        self.client.force_login(athlete_user)
        page = self.client.get(f"/athlete/year/?year={future_day.year}&athlete={athlete.id}")
        self.assertEqual(page.status_code, 200)
        report = next(
            cell
            for week in page.context["week_rows"]
            for cell in week["cells3"]
            if cell["day"] == future_day
        )
        self.assertTrue(report["has_slot1"])
        self.assertTrue(report["has_slot2"])
        self.assertContains(page, f'data-date="{future_day:%Y-%m-%d}"', html=False)
        self.assertContains(page, 'data-t1-enabled="1"', html=False)
        self.assertContains(page, 'data-t2-enabled="1"', html=False)

        response = self.client.post(
            f"/athlete/year/?year={future_day.year}&athlete={athlete.id}",
            {
                "date": future_day.isoformat(),
                "slot_index": "1",
                "report_submit": "1",
                "check_status": "done_as_planned",
                "rpe": "5",
                "report_comment": "Future watch report",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(
            AthleteDayCheck.objects.filter(
                athlete=athlete, date=future_day, slot_index=1, comment="Future watch report"
            ).exists()
        )

    def test_athlete_year_pm_training_contains_modal_prefill_values(self):
        template_path = get_template("core/athlete_year_calendar.html").origin.name
        template_source = Path(template_path).read_text(encoding="utf-8")
        self.assertIn('if (aycTrainingIsEditable(box.getAttribute("data-date")))', template_source)
        pm_desktop_block = template_source.split(
            '<tr class="slotrow {% if today >= w.week_start and today <= w.week_end %}current-week{% endif %}">',
            1,
        )[1].split("{% if show_training_reports %}", 1)[0]

        for field in ("wu", "mob", "sprint", "core", "core2", "alt", "cd"):
            self.assertIn(f'data-prefill-{field}=', pm_desktop_block)


class SegmentRepTimeDisplayTests(TestCase):
    def test_zone_hr_label_uses_manual_zone_heart_rate(self):
        athlete = Athlete.objects.create(
            name="HR Runner",
            birth_year=2000,
            gender="X",
            zone_hr_bpm={"1": 145, "2": 160, "3": 172},
        )
        segment = TrainingSegment(type="CORE", text="20' z2", zone="2", duration_s=1200)

        self.assertEqual(_segment_hr_label(athlete, segment), "HR160")

    def test_zone_hr_label_accepts_text_ranges_and_z4_z5(self):
        athlete = Athlete.objects.create(
            name="Text HR Runner",
            birth_year=2000,
            gender="X",
            zone_hr_bpm={"4": "160-170", "5": "max 170"},
        )

        self.assertEqual(
            _segment_hr_label(
                athlete,
                TrainingSegment(type="CORE", text="400m z4", zone="4"),
            ),
            "HR160-170",
        )
        self.assertEqual(
            _segment_hr_label(
                athlete,
                TrainingSegment(type="CORE", text="200m z5", zone="5"),
            ),
            "HRmax 170",
        )

    def test_zone_hr_label_lists_distinct_zones_for_compound_segment(self):
        athlete = Athlete.objects.create(
            name="Compound HR Runner",
            birth_year=2000,
            gender="X",
            zone_hr_bpm={"1": 145, "2": 160, "3": 172},
        )
        segment = TrainingSegment(
            type="CORE",
            text="4*(300m z2-100m z1)",
            zone="2",
        )

        self.assertEqual(_segment_hr_label(athlete, segment), "HR160/HR145")

    def test_progressive_zone_hr_label_uses_arrow(self):
        athlete = Athlete.objects.create(
            name="Progressive HR Runner",
            birth_year=2000,
            gender="X",
            zone_hr_bpm={"1": 145, "2": 155, "3": 165},
        )
        segment = TrainingSegment(type="CORE", text="1000m z2>z3")

        self.assertEqual(_segment_hr_label(athlete, segment), "HR155-->HR165")

    def test_progressive_zone_hr_label_includes_intermediate_configured_zones(self):
        athlete = Athlete.objects.create(
            name="Long Progressive HR Runner",
            birth_year=2000,
            gender="X",
            zone_hr_bpm={"1": 145, "2": 155, "3": 165},
        )
        segment = TrainingSegment(type="CORE", text="1000m z1>z4")

        self.assertEqual(_segment_hr_label(athlete, segment), "HR145-->HR155-->HR165")

    def test_display_text_includes_hr_next_to_indicative_time(self):
        athlete = Athlete.objects.create(
            name="Displayed HR Runner",
            birth_year=2000,
            gender="X",
            zone_speed_mps={"2": 1000 / 300},
            zone_hr_bpm={"2": 160},
        )
        segment = TrainingSegment(type="CORE", text="20' z2", zone="2", duration_s=1200)

        class Segments:
            def all(self):
                return [segment]

        class Slot:
            segments = Segments()

        _annotate_slot_segment_display_times(Slot(), athlete)

        self.assertEqual(segment.display_text, "20' z2 (5:00 min/km; HR160)")

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
            f"/race-calendar/?year=2026&view=list&period=full&race_group=plan:{trainer_plan.id}&race_athlete=athlete:{athlete_one.id}"
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
        self.assertContains(response, 'data-initial-filter="participating"', html=False)
        popup_athlete_filter = response.content.decode().split(
            'class="form-select form-select-sm race-athlete-filter"', 1
        )[1].split("</select>", 1)[0]
        self.assertIn('value="participating"', popup_athlete_filter)
        self.assertIn('value="participating" selected', popup_athlete_filter)
        self.assertNotIn("athlete:", popup_athlete_filter)
        self.assertContains(response, 'row.dataset.participating === "1"', html=False)
        self.assertContains(response, "this.form.querySelector('[name=show_all]').checked=false", html=False)
        self.assertNotRegex(response.content.decode(), r'name="show_all" value="1" checked')
        self.assertContains(response, 'class="form-check-input race-expand-toggle"', html=False)
        self.assertRegex(response.content.decode(), r'class="form-check-input race-expand-toggle"[^>]*checked')
        self.assertContains(response, '<span>Athlete</span><span>Distance</span><span>Trainer</span><span>Athlete</span><span>Target</span>', html=False)
        self.assertContains(response, 'class="race-entry-distance-list"', html=False)
        self.assertContains(response, 'row.open = toggle.checked', html=False)

        group_response = self.client.get(
            f"/race-calendar/?year=2026&view=list&period=full&race_group=plan:{trainer_plan.id}&race_athlete=all"
        )
        self.assertContains(group_response, 'data-initial-filter="participating"', html=False)
        self.assertNotRegex(
            group_response.content.decode(),
            r'name="show_all" value="1" checked',
        )

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

    def test_race_calendar_group_filter_only_lists_active_coach_plans(self):
        logged_in = get_user_model().objects.create_user(
            username="race-group-grantee", password="secret", is_staff=True
        )
        active_owner = get_user_model().objects.create_user(
            username="race-group-owner", password="secret", is_staff=True
        )
        CoachAccess.objects.create(owner=active_owner, grantee=logged_in, can_edit=True)
        own_plan = TrainingPlan.objects.create(
            owner=logged_in, name="Own hidden group", plan_kind=TrainingPlan.PLAN_KIND_TRAINER
        )
        active_plan = TrainingPlan.objects.create(
            owner=active_owner, name="Active coach group", plan_kind=TrainingPlan.PLAN_KIND_TRAINER
        )
        self.client.force_login(logged_in)
        session = self.client.session
        session["active_coach_owner_id"] = active_owner.id
        session.save()

        response = self.client.get("/race-calendar/?year=2026&view=list")

        self.assertContains(response, "Active coach group")
        self.assertNotContains(response, "Own hidden group")
        self.assertContains(response, f'value="plan:{active_plan.id}"', html=False)
        self.assertNotContains(response, f'value="plan:{own_plan.id}"', html=False)

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
        self.assertIn('id="see_session_km"', html)
        self.assertIn('id="see_session_km"\n            name="see_session_km"\n            checked', html)
        self.assertIn('class="zone-time-grid"', html)
        self.assertIn('class="pr-time-grid"', html)
        self.assertEqual(html.count('class="col-md-2 pr-time-card"'), 10)
        self.assertEqual(html.count('data-time-label="PR"'), 10)
        self.assertEqual(html.count('data-time-label="Doel"'), 10)
        for name in ("t4", "target_t4"):
            self.assertIn(f'name="{name}"', html)
            self.assertRegex(html, rf'name="{name}"[^>]+data-time-format="seconds-hundredths"')
        for name in (
            "pr_600", "target_pr_600", "pr_800", "target_pr_800",
            "pr_1000", "target_pr_1000", "pr_1500", "target_pr_1500",
        ):
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

    def test_fill_missing_pbs_accepts_blank_hundredths(self):
        source = get_template("core/coach_athlete_form.html").template.source

        self.assertIn('seconds ? seconds + "." + (hundredths || "00") : ""', source)
        self.assertIn('minutes && seconds ? minutes + ":" + seconds + "." + (hundredths || "00") : ""', source)
        self.assertIn("target._setFixedTimeSeconds(calculatedSeconds)", source)

    def test_selected_athlete_name_is_shown_to_coaches_across_tabs(self):
        source = get_template("core/coach_athlete_form.html").template.source

        self.assertIn('{% elif not self_view and athlete %}', source)
        self.assertIn('Selected athlete: <span class="fw-semibold text-body">{{ athlete.name }}</span>', source)
        self.assertIn("previous_athlete.id", source)
        self.assertIn("next_athlete.id", source)
        self.assertIn("?tab={{ active_tab }}", source)

    def test_athlete_input_navigation_is_alphabetical_and_scoped_to_active_coach(self):
        User = get_user_model()
        admin = User.objects.create_user(
            username="athlete-nav-admin", password="secret", is_staff=True, is_superuser=True
        )
        active_coach = User.objects.create_user(
            username="athlete-nav-active", password="secret", is_staff=True
        )
        unrelated_coach = User.objects.create_user(
            username="athlete-nav-unrelated", password="secret", is_staff=True
        )
        CoachAccess.objects.create(owner=active_coach, grantee=admin, can_edit=True)
        previous = Athlete.objects.create(owner=active_coach, name="Ada Runner", birth_year=2000, gender="X")
        current = Athlete.objects.create(owner=active_coach, name="Mira Runner", birth_year=2000, gender="X")
        following = Athlete.objects.create(owner=active_coach, name="Zoey Runner", birth_year=2000, gender="X")
        unrelated = Athlete.objects.create(owner=unrelated_coach, name="Aaron Outsider", birth_year=2000, gender="X")
        self.client.force_login(admin)
        session = self.client.session
        session["active_coach_owner_id"] = active_coach.id
        session.save()

        response = self.client.get(f"/coach/athletes/{current.id}/edit/?tab=base-planning")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, f'href="/coach/athletes/{previous.id}/edit/?tab=base-planning"', html=False)
        self.assertContains(response, f'href="/coach/athletes/{following.id}/edit/?tab=base-planning"', html=False)
        self.assertNotContains(response, f'/coach/athletes/{unrelated.id}/edit/', html=False)

    def test_trainer_and_athlete_can_change_see_session_km(self):
        User = get_user_model()
        coach = User.objects.create_user(username="session-km-coach", password="secret", is_staff=True)
        athlete = Athlete.objects.create(
            owner=coach,
            name="sessionkmrunner",
            birth_year=2000,
            gender="X",
        )
        athlete_user = User.objects.create_user(username="sessionkmrunner", password="secret")
        form_data = {
            "name": athlete.name,
            "birth_year": "2000",
            "gender": "X",
            "zone_method": "manual",
            "z1_pace": "6:00",
            "z2_pace": "5:30",
            "z3_pace": "5:00",
            "z4_pace": "4:30",
            "z5_pace": "4:00",
        }

        self.client.force_login(coach)
        trainer_response = self.client.post(f"/coach/athletes/{athlete.id}/edit/", form_data)
        self.assertEqual(trainer_response.status_code, 302)
        athlete.refresh_from_db()
        self.assertFalse(athlete.see_session_km)

        self.client.force_login(athlete_user)
        athlete_response = self.client.post(
            "/athlete/settings/",
            {**form_data, "see_session_km": "on"},
        )
        self.assertEqual(athlete_response.status_code, 302)
        athlete.refresh_from_db()
        self.assertTrue(athlete.see_session_km)


class TrainingSegmentLabelTests(TestCase):
    def test_main_labels_replace_core_labels(self):
        self.assertEqual(TrainingSegment(type="CORE").get_type_display(), "Main")
        self.assertEqual(TrainingSegment(type="CORE2").get_type_display(), "Main 2")

    def test_watch_slot_uses_actual_zone_time_for_segment_label_and_totals(self):
        from core.stats import athlete_week_stats

        coach = get_user_model().objects.create_user(username="watchsourcecoach", password="secret", is_staff=True)
        athlete = Athlete.objects.create(
            owner=coach,
            name="Watch Source Athlete",
            birth_year=2000,
            gender="X",
            zone_speed_mps={"1": 3.0, "2": 4.0},
        )
        plan = TrainingPlan.objects.create(owner=coach, name="Watch source plan")
        day = date(2026, 10, 22)
        slot = TrainingSlot.objects.create(
            plan=plan,
            athlete=athlete,
            date=day,
            slot_index=1,
            source="watch_a",
            watch_loads=[
                {"segment": "CORE", "zone": "1", "meters": 300, "seconds": 100},
                {"segment": "CORE", "zone": "2", "meters": 800, "seconds": 200},
            ],
        )
        segment = slot.segments.create(type="CORE", text="20' z2", zone="2", duration_s=1200)

        self.assertEqual(_segment_rep_time_label(athlete, segment), "4:10 min/km")
        loads = _ayc_slot_loads_for_totals(slot, athlete)
        self.assertEqual(sum(load["meters"] for load in loads), 1100)
        weekly = athlete_week_stats(plan, athlete, day)
        self.assertEqual(weekly["zones"]["1"]["distance_m"], 300)
        self.assertEqual(weekly["zones"]["1"]["duration_s"], 100)
        self.assertEqual(weekly["zones"]["2"]["distance_m"], 800)
        self.assertEqual(weekly["zones"]["2"]["duration_s"], 200)


class WatchProcessedMainRepTests(TestCase):
    def test_processed_main_reps_are_saved_separately_and_skip_recovery_laps(self):
        from core.watch_processing import save_processed_main_reps

        coach = get_user_model().objects.create_user(username="watch-rep-layer", password="secret", is_staff=True)
        athlete = Athlete.objects.create(owner=coach, name="Rep Layer Athlete", birth_year=2000, gender="X")
        plan = TrainingPlan.objects.create(owner=coach, name="Rep layer plan")
        raw_loads = [
            {"segment": "CORE", "zone": "4", "meters": 202, "seconds": 40.5},
            {"segment": "CORE", "zone": "1", "meters": 45, "seconds": 30},
            {"segment": "CORE", "zone": "4", "meters": 198, "seconds": 41},
            {"segment": "CORE", "zone": "5", "meters": 151, "seconds": 25.5},
            {"segment": "CORE", "zone": "1", "meters": 40, "seconds": 28},
            {"segment": "CORE", "zone": "5", "meters": 149, "seconds": 24.8},
        ]
        slot = TrainingSlot.objects.create(
            plan=plan, athlete=athlete, date=date(2026, 10, 27), slot_index=1,
            source="watch_c", watch_loads=raw_loads,
        )
        slot.segments.create(type="CORE", text="2*200m z4", order=1, reps=2, distance_m=200, norm_distance_m=400, zone="4")
        slot.segments.create(type="CORE", text="2*150m z5", order=2, reps=2, distance_m=150, norm_distance_m=300, zone="5")
        km_before = _ayc_slot_session_km(slot, athlete)

        processed = save_processed_main_reps(slot)
        slot.refresh_from_db()

        self.assertEqual([rep["distance_m"] for rep in processed], [200, 200, 150, 150])
        self.assertEqual([rep["measured_distance_m"] for rep in processed], [202, 198, 151, 149])
        self.assertEqual(processed[0]["pace_seconds_per_km"], round(40.5 * 1000 / 202, 2))
        self.assertEqual([rep["rep"] for rep in processed], [1, 2, 3, 4])
        self.assertEqual(slot.watch_loads, raw_loads)
        self.assertEqual(slot.watch_main_reps, processed)
        self.assertEqual(_ayc_slot_session_km(slot, athlete), km_before)

    def test_main_rep_distance_uses_planned_distance_despite_gps_drift(self):
        from core.watch_processing import processed_main_reps

        coach = get_user_model().objects.create_user(username="watch-rep-rounded", password="secret", is_staff=True)
        athlete = Athlete.objects.create(owner=coach, name="Rounded Rep Athlete", birth_year=2000, gender="X")
        plan = TrainingPlan.objects.create(owner=coach, name="Rounded rep plan")
        slot = TrainingSlot.objects.create(
            plan=plan, athlete=athlete, date=date(2026, 10, 27), slot_index=1,
            source="watch_c", watch_loads=[
                {"segment": "CORE", "zone": "2", "meters": 190, "seconds": 40},
                {"segment": "CORE", "zone": "1", "meters": 50, "seconds": 30},
                {"segment": "CORE", "zone": "2", "meters": 250, "seconds": 45},
                {"segment": "CORE", "zone": "5", "meters": 160, "seconds": 25},
                {"segment": "CORE", "zone": "5", "meters": 140, "seconds": 24},
            ],
        )
        slot.segments.create(type="CORE", text="2*200m z2", order=1, reps=2, distance_m=200, norm_distance_m=400, zone="2")
        slot.segments.create(type="CORE", text="2*150m z5", order=2, reps=2, distance_m=150, norm_distance_m=300, zone="5")

        processed = processed_main_reps(slot)

        self.assertEqual([rep["distance_m"] for rep in processed], [200, 200, 150, 150])
        self.assertEqual([rep["measured_distance_m"] for rep in processed], [190, 250, 160, 140])

    def test_ayc_watch_source_indicator_appears_without_session_totals(self):
        for source, label in (
            ("watch_a", "Polar A"),
            ("watch_b", "Polar B"),
            ("watch_c", "Garmin C"),
        ):
            with self.subTest(source=source):
                html = render_to_string(
                    "core/partials/ayc_slot_segments.html",
                    {
                        "cell": {
                            "slot": {"source": source, "text": "800m z1"},
                            "slot_index": 1,
                            "whereabouts": [],
                            "session_km": "",
                            "session_zones": [],
                        },
                        "show_session_km": False,
                        "show_session_zones": False,
                    },
                )
                self.assertIn(f'aria-label="View measured Main reps from {label}"', html)
                self.assertIn("watch-source-indicator", html)

        planned_html = render_to_string(
            "core/partials/ayc_slot_segments.html",
            {
                "cell": {
                    "slot": {"source": "planned", "text": "800m z1"},
                    "slot_index": 1,
                    "whereabouts": [],
                    "session_km": "",
                    "session_zones": [],
                },
                "show_session_km": False,
                "show_session_zones": False,
            },
        )
        self.assertNotIn("watch-source-indicator", planned_html)

    def test_watch_main_time_label_ignores_short_recovery_laps(self):
        segment = TrainingSegment(
            type="CORE",
            text="3x2000m z2 p1",
            distance_m=2000,
            norm_distance_m=6000,
            reps=3,
        )
        label = _watch_actual_time_label(
            [
                {"meters": 2000, "seconds": 420},
                {"meters": 200, "seconds": 8},
                {"meters": 2000, "seconds": 430},
            ],
            segment,
        )
        self.assertNotIn("0:08", label)
        self.assertIn("7:10-->7:00 (3:35-->3:30 min/km)", label)

    def test_watch_short_rep_time_labels_match_each_segments_distance(self):
        loads = [
            {"meters": 190, "seconds": 38.463, "zone": "5"},
            {"meters": 40, "seconds": 45.663, "zone": "1"},
            {"meters": 250, "seconds": 44.631, "zone": "5"},
            {"meters": 30, "seconds": 44.411, "zone": "1"},
            {"meters": 200, "seconds": 41.864, "zone": "5"},
            {"meters": 30, "seconds": 44.629, "zone": "1"},
            {"meters": 190, "seconds": 41.614, "zone": "4"},
            {"meters": 30, "seconds": 45.027, "zone": "1"},
            {"meters": 200, "seconds": 40.956, "zone": "5"},
            {"meters": 30, "seconds": 119.496, "zone": "1"},
            {"meters": 190, "seconds": 41.825, "zone": "4"},
            {"meters": 40, "seconds": 49.550, "zone": "1"},
            {"meters": 200, "seconds": 43.900, "zone": "4"},
            {"meters": 30, "seconds": 44.905, "zone": "1"},
            {"meters": 200, "seconds": 41.867, "zone": "5"},
            {"meters": 30, "seconds": 89.702, "zone": "1"},
            {"meters": 200, "seconds": 39.784, "zone": "5"},
            {"meters": 40, "seconds": 45.120, "zone": "1"},
            {"meters": 190, "seconds": 43.002, "zone": "4"},
            {"meters": 50, "seconds": 142.302, "zone": "1"},
            {"meters": 230, "seconds": 382.1, "zone": "1"},
            {"meters": 150, "seconds": 25.760, "zone": "5"},
            {"meters": 220, "seconds": 172.7, "zone": "1"},
            {"meters": 160, "seconds": 26.455, "zone": "5"},
            {"meters": 230, "seconds": 382.1, "zone": "1"},
            {"meters": 150, "seconds": 25.100, "zone": "5"},
            {"meters": 220, "seconds": 174.4, "zone": "1"},
            {"meters": 140, "seconds": 25.700, "zone": "5"},
        ]
        segment_200 = TrainingSegment(
            type="CORE", text="10x200m z4>z5 p59", distance_m=200,
            norm_distance_m=2000, reps=10,
        )
        segment_150 = TrainingSegment(
            type="CORE", text="4x150m z5 p243", distance_m=150,
            norm_distance_m=600, reps=4,
        )

        label_200 = _watch_actual_time_label(loads, segment_200)
        label_150 = _watch_actual_time_label(loads, segment_150)

        self.assertIn("3:46-->2:59 min/km", label_200)
        self.assertNotIn("27:41", label_200)
        self.assertNotIn("6:22", label_200)
        self.assertIn("3:04-->2:45 min/km", label_150)
        self.assertNotIn("3:22", label_150)


class FlexPlannerAltTotalsTests(TestCase):
    def test_watch_main_display_notation_is_normalized_before_slot_parsing(self):
        from core.parser import parse_segment_text
        from core.training_text import normalize_watch_main_text

        display_text = "2×(1150 m Z2 (4:14) + 1000 m Z2 (4:08) + 800 m Z2 (4:11))"
        planner_text = normalize_watch_main_text(display_text)

        self.assertEqual(planner_text, "2×(1150 m Z2 - 1000 m Z2 - 800 m Z2)")
        parsed = parse_segment_text(planner_text)
        self.assertTrue(parsed.ok)
        self.assertEqual(parsed.distance_m, 5900)

    def test_main_segment_splitter_accepts_plus_and_keeps_inner_compound_separators(self):
        from core.training_text import split_main_segments

        self.assertEqual(
            split_main_segments("8*(400m z2-50m z1-150m z3) + 2*1000m z3 // 5*200m z4"),
            ["8*(400m z2-50m z1-150m z3)", "2*1000m z3", "5*200m z4"],
        )
        self.assertEqual(
            split_main_segments("3x2000m z2 p107 - 2x1000m z2 p40"),
            ["3x2000m z2 p107", "2x1000m z2 p40"],
        )

    def test_flex_plus_saves_main_as_two_segments_and_both_zones_count(self):
        from core.stats import athlete_week_stats

        trainer = get_user_model().objects.create_user(username="plusmaincoach", password="secret", is_staff=True)
        athlete = Athlete.objects.create(owner=trainer, name="Plus Main Athlete", birth_year=2000, gender="X")
        week_start = date(2026, 10, 26)
        plan = TrainingPlan.objects.create(
            owner=trainer,
            name="Flex Planner Plus Main",
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
                "core_text": "2*1000m z2 + 2*1000m z3",
            },
        )

        self.assertEqual(response.status_code, 200)
        slot = TrainingSlot.objects.get(plan=plan, athlete=athlete, date=week_start, slot_index=1)
        segments = list(slot.segments.filter(type="CORE").order_by("order", "id"))
        self.assertEqual([segment.text for segment in segments], ["2*1000m z2", "2*1000m z3"])

        stats = athlete_week_stats(plan, athlete, week_start)
        self.assertEqual(stats["zones"]["2"]["distance_m"], 2000)
        self.assertEqual(stats["zones"]["3"]["distance_m"], 2000)

    def test_legacy_plus_main_counts_each_part_in_stats_and_ayc(self):
        from core.stats import athlete_week_stats, base_week_stats
        from core.views.calendar import _ayc_slot_loads_for_totals

        cache.clear()
        trainer = get_user_model().objects.create_user(username="legacypluscoach", password="secret", is_staff=True)
        athlete = Athlete.objects.create(owner=trainer, name="Legacy Plus Athlete", birth_year=2000, gender="X")
        week_start = date(2026, 10, 26)
        plan = TrainingPlan.objects.create(owner=trainer, name="Legacy plus plan")
        PlanMembership.objects.create(plan=plan, athlete=athlete)
        slot = TrainingSlot.objects.create(plan=plan, athlete=athlete, date=week_start, slot_index=1)
        slot.segments.create(
            type="CORE",
            text="2*1000m z2+2*1000m z3",
            zone="2",
            reps=2,
            distance_m=1000,
            norm_distance_m=2000,
        )
        base_slot = TrainingSlot.objects.create(plan=plan, date=week_start, slot_index=1)
        base_slot.segments.create(type="CORE", text="2*1000m z2+2*1000m z3", zone="2")

        stats = athlete_week_stats(plan, athlete, week_start)
        self.assertEqual(stats["zones"]["2"]["distance_m"], 2000)
        self.assertEqual(stats["zones"]["3"]["distance_m"], 2000)
        base_stats = base_week_stats(plan, week_start)
        self.assertEqual(base_stats["zones"]["2"]["distance_m"], 2000)
        self.assertEqual(base_stats["zones"]["3"]["distance_m"], 2000)
        display_slot = _clone_slot_for_display(slot)
        self.assertEqual(
            [segment.text for segment in display_slot.segments.all()],
            ["2*1000m z2", "2*1000m z3"],
        )
        loads = _ayc_slot_loads_for_totals(slot, athlete)
        self.assertEqual(
            {(load["zone"], load["meters"]) for load in loads},
            {("2", 2000.0), ("3", 2000.0)},
        )

    def test_flex_totals_keep_alt_z1_to_z3_separate_from_running_distance(self):
        source = get_template("core/flex_planner.html").template.source

        self.assertIn('if (segType === "ALT")', source)
        self.assertIn('["1", "2", "3"].includes(fallbackZone)', source)
        self.assertIn('? [{kind: "alt", zone: fallbackZone, seconds: altSeconds}]', source)
        self.assertIn('if (load.kind === "alt")', source)
        self.assertIn('"ALT Z" + z', source)
        self.assertIn('const altParts = text.split("//")', source)

    def test_flex_slot_modal_uses_capture_click_opener(self):
        source = get_template("core/flex_planner.html").template.source

        self.assertIn("function openFlexSlotModal(url)", source)
        self.assertIn("window.htmx.process(container)", source)
        self.assertIn('event.stopImmediatePropagation();', source)
        self.assertIn('".flex-cell[hx-get]"', source)
        self.assertIn("}, true);", source)

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

    def test_progressive_zone_range_includes_intermediate_zones(self):
        from core.stats import base_week_stats

        cache.clear()
        trainer = get_user_model().objects.create_user(username="rangezonecoach", password="secret", is_staff=True)
        plan = TrainingPlan.objects.create(owner=trainer, name="Range zone plan")
        week_start = date(2026, 9, 7)
        slot = TrainingSlot.objects.create(plan=plan, date=week_start, slot_index=1)
        TrainingSegment.objects.create(
            slot=slot,
            type="CORE",
            text="6km z2>z4",
            zone="2",
            norm_distance_m=6000,
        )

        self.assertEqual(
            [(load["zone"], round(load["meters"])) for load in _ayc_slot_loads_for_totals(slot)],
            [("2", 2000), ("3", 2000), ("4", 2000)],
        )
        stats = base_week_stats(plan, week_start)
        self.assertEqual(
            {zone: values["distance_m"] for zone, values in stats["zones"].items() if values["distance_m"]},
            {"2": 2000, "3": 2000, "4": 2000},
        )

    def test_progressive_t_range_includes_intermediate_t_types(self):
        from core.stats import base_week_stats

        cache.clear()
        trainer = get_user_model().objects.create_user(username="rangetcoach", password="secret", is_staff=True)
        plan = TrainingPlan.objects.create(owner=trainer, name="Range t plan")
        week_start = date(2026, 9, 7)
        slot = TrainingSlot.objects.create(plan=plan, date=week_start, slot_index=1)
        TrainingSegment.objects.create(
            slot=slot,
            type="CORE",
            text="3km t5>t15",
            zone="4",
            t_type="5000",
            norm_distance_m=3000,
        )

        self.assertEqual(
            [(load["zone"], load["t_key"], round(load["meters"])) for load in _ayc_slot_loads_for_totals(slot)],
            [("4", "5000", 1000), ("4", "3000", 1000), ("5", "1500", 1000)],
        )
        stats = base_week_stats(plan, week_start)
        self.assertEqual(
            {key: values["distance_m"] for key, values in stats["t_totals"].items() if values["distance_m"]},
            {"5000": 1000, "3000": 1000, "1500": 1000},
        )

    def test_progressive_t_range_includes_new_blue_t_types(self):
        from core.stats import base_week_stats

        cache.clear()
        trainer = get_user_model().objects.create_user(username="bluecoach", password="secret", is_staff=True)
        plan = TrainingPlan.objects.create(owner=trainer, name="Blue t plan")
        week_start = date(2026, 9, 7)
        slot = TrainingSlot.objects.create(plan=plan, date=week_start, slot_index=1)
        TrainingSegment.objects.create(
            slot=slot,
            type="CORE",
            text="5km t15>t4",
            zone="5",
            t_type="1500",
            norm_distance_m=5000,
        )

        self.assertEqual(
            [(load["zone"], load["t_key"], round(load["meters"])) for load in _ayc_slot_loads_for_totals(slot)],
            [
                ("5", "1500", 1000),
                ("5", "1000", 1000),
                ("5", "800", 1000),
                ("5", "600", 1000),
                ("5", "T4", 1000),
            ],
        )
        stats = base_week_stats(plan, week_start)
        self.assertEqual(
            {key: values["distance_m"] for key, values in stats["t_totals"].items() if values["distance_m"]},
            {"1500": 1000, "1000": 1000, "800": 1000, "600": 1000, "T4": 1000},
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

    def test_dco_saved_selection_save_as_keeps_existing_selection(self):
        trainer = get_user_model().objects.create_user(
            username="dco-multiple-selections", password="secret", is_staff=True
        )
        first = Athlete.objects.create(owner=trainer, name="DCO First", birth_year=2000, gender="X")
        second = Athlete.objects.create(owner=trainer, name="DCO Second", birth_year=2001, gender="X")
        self.client.force_login(trainer)

        first_response = self.client.post(
            "/coach/daily-overview/",
            {
                "action": "save_dco_selection",
                "date": date.today().isoformat(),
                "slots": "both",
                "selection_name": "First group",
                "athletes": [str(first.id)],
            },
        )
        self.assertEqual(first_response.status_code, 302)
        first_saved = CoachSettings.objects.get(user=trainer).dco_saved_selections
        self.assertEqual(len(first_saved), 1)

        second_response = self.client.post(
            "/coach/daily-overview/",
            {
                "action": "save_dco_selection",
                "date": date.today().isoformat(),
                "slots": "both",
                "saved_selection": first_saved[0]["id"],
                "selection_name": "Second group",
                "athletes": [str(second.id)],
            },
        )
        self.assertEqual(second_response.status_code, 302)
        saved = CoachSettings.objects.get(user=trainer).dco_saved_selections
        self.assertEqual({item["name"] for item in saved}, {"First group", "Second group"})
        self.assertEqual(next(item for item in saved if item["name"] == "First group")["athlete_ids"], [first.id])
        self.assertEqual(next(item for item in saved if item["name"] == "Second group")["athlete_ids"], [second.id])

    def test_dco_saved_selections_belong_to_active_coach(self):
        logged_in = get_user_model().objects.create_user(
            username="dco-selection-grantee", password="secret", is_staff=True
        )
        active_owner = get_user_model().objects.create_user(
            username="dco-selection-owner", password="secret", is_staff=True
        )
        athlete = Athlete.objects.create(owner=active_owner, name="Owner athlete", birth_year=2000, gender="X")
        CoachAccess.objects.create(owner=active_owner, grantee=logged_in, can_edit=True)
        CoachSettings.objects.create(
            user=logged_in,
            dco_saved_selections=[{"id": "wrong-owner", "name": "Logged-in selection", "athlete_ids": []}],
        )
        CoachSettings.objects.create(
            user=active_owner,
            dco_saved_selections=[{"id": "active-owner", "name": "Active selection", "athlete_ids": [athlete.id]}],
        )
        self.client.force_login(logged_in)
        session = self.client.session
        session["active_coach_owner_id"] = active_owner.id
        session.save()

        response = self.client.get("/coach/daily-overview/?selection=selection")
        self.assertContains(response, "Active selection")
        self.assertNotContains(response, "Logged-in selection")

        self.client.post(
            "/coach/daily-overview/",
            {
                "action": "save_dco_selection",
                "date": date.today().isoformat(),
                "slots": "both",
                "selection_name": "New active selection",
                "athletes": [str(athlete.id)],
            },
        )
        self.assertTrue(
            CoachSettings.objects.get(user=active_owner).dco_saved_selections
        )
        self.assertIn(
            "New active selection",
            {item["name"] for item in CoachSettings.objects.get(user=active_owner).dco_saved_selections},
        )
        self.assertEqual(
            CoachSettings.objects.get(user=logged_in).dco_saved_selections[0]["name"],
            "Logged-in selection",
        )

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


class AthleteZoneHeartRateTests(TestCase):
    def test_zone_heart_rates_are_saved_and_shown_for_zones_one_to_three(self):
        coach = get_user_model().objects.create_user(
            username="zone-hr-coach", password="secret", is_staff=True
        )
        athlete = Athlete.objects.create(
            owner=coach, name="Zone HR Athlete", birth_year=2000, gender="X"
        )
        self.client.force_login(coach)

        response = self.client.post(
            f"/coach/athletes/{athlete.id}/edit/",
            {
                "active_tab": "zones",
                "name": athlete.name,
                "birth_year": "2000",
                "gender": "X",
                "zone_method": "manual",
                "z1_pace": "5:30",
                "z2_pace": "5:00",
                "z3_pace": "4:30",
                "z4_pace": "4:00",
                "z5_pace": "3:30",
                "z1_hr": "130",
                "z2_hr": "145",
                "z3_hr": "160",
                "z4_hr": "160-170",
                "z5_hr": "max 170",
            },
        )

        self.assertRedirects(
            response,
            f"/coach/athletes/{athlete.id}/edit/?tab=zones&saved=1",
        )
        athlete.refresh_from_db()
        self.assertEqual(
            athlete.zone_hr_bpm,
            {"1": "130", "2": "145", "3": "160", "4": "160-170", "5": "max 170"},
        )

        page = self.client.get(f"/coach/athletes/{athlete.id}/edit/?tab=zones")
        self.assertContains(page, 'name="z1_hr"', html=False)
        self.assertContains(page, 'value="130"', html=False)
        self.assertContains(page, 'value="145"', html=False)
        self.assertContains(page, 'value="160"', html=False)
        self.assertContains(page, 'value="160-170"', html=False)
        self.assertContains(page, 'value="max 170"', html=False)


class SecurityAccessRegressionTests(TestCase):
    def setUp(self):
        self.coach = get_user_model().objects.create_user(
            username="security-coach", password="secret", is_staff=True
        )
        self.alice_user = get_user_model().objects.create_user(
            username="alice", password="secret"
        )
        self.bob_user = get_user_model().objects.create_user(
            username="bob", password="secret"
        )
        self.alice = Athlete.objects.create(
            owner=self.coach, name="Alice", birth_year=2000, gender="X"
        )
        self.bob = Athlete.objects.create(
            owner=self.coach, name="Bob", birth_year=2001, gender="X"
        )

    def test_athlete_cannot_switch_to_another_athlete_in_personal_views(self):
        self.client.force_login(self.alice_user)

        settings_response = self.client.get("/athlete/settings/")
        year_response = self.client.get(
            f"/athlete/year/?year=2026&athlete={self.bob.id}"
        )

        self.assertEqual(settings_response.status_code, 200)
        self.assertContains(settings_response, "Alice")
        self.assertNotContains(settings_response, "Bob")
        self.assertEqual(year_response.status_code, 200)
        self.assertContains(year_response, "Alice")
        self.assertNotContains(year_response, "Bob")


class MeetingRequestTests(TestCase):
    def setUp(self):
        self.coach = get_user_model().objects.create_user(username="meeting-coach", password="secret")
        self.athlete_user = get_user_model().objects.create_user(username="meeting-athlete", password="secret")
        self.other_user = get_user_model().objects.create_user(username="other-athlete", password="secret")
        self.athlete = Athlete.objects.create(owner=self.coach, name="Meeting Athlete", birth_year=2000, gender="X")
        self.other_athlete = Athlete.objects.create(owner=self.coach, name="Other Athlete", birth_year=2001, gender="X")

    def test_athlete_can_request_and_cancel_meeting_from_settings(self):
        self.athlete_user.username = "meetingathlete"
        self.athlete_user.save(update_fields=["username"])
        self.client.force_login(self.athlete_user)

        page = self.client.get("/athlete/settings/")
        self.assertContains(page, "Request meeting")
        response = self.client.post("/athlete/settings/", {"meeting_action": "request"})
        self.assertEqual(response.status_code, 302)
        self.athlete.refresh_from_db()
        self.assertIsNotNone(self.athlete.meeting_requested_at)
        page = self.client.get("/athlete/settings/")
        self.assertContains(page, "Meeting requested on")
        self.assertContains(page, 'value="cancel"')

        response = self.client.post("/athlete/settings/", {"meeting_action": "cancel"})
        self.assertEqual(response.status_code, 302)
        self.athlete.refresh_from_db()
        self.assertIsNone(self.athlete.meeting_requested_at)

    def test_main_coach_sees_new_request_and_age_badge_until_dismissed(self):
        self.athlete.meeting_requested_at = timezone.now() - timedelta(days=3)
        self.athlete.save(update_fields=["meeting_requested_at"])
        self.client.force_login(self.coach)

        response = self.client.get("/coach/daily-overview-other/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Meeting Athlete requested a meeting.")
        self.assertContains(response, "Meeting requested · 3d")
        self.assertContains(response, "btn-warning")

        response = self.client.post("/coach/meeting-requests/dismiss/")
        self.assertEqual(response.status_code, 302)
        response = self.client.get("/coach/daily-overview-other/")
        self.assertNotContains(response, "Meeting Athlete requested a meeting.")
        self.assertContains(response, "Meeting requested · 3d")

    def test_meeting_request_button_color_thresholds(self):
        today = timezone.localdate()
        athletes = [self.athlete, self.other_athlete]
        for name in ("Age Five", "Age Six", "Age Two"):
            athletes.append(Athlete.objects.create(owner=self.coach, name=name, birth_year=2000, gender="X"))
        for athlete, age in zip(athletes, (0, 3, 5, 6, 2)):
            athlete.meeting_requested_at = timezone.make_aware(
                datetime.combine(today - timedelta(days=age), time.min)
            )
            athlete.save(update_fields=["meeting_requested_at"])

        self.client.force_login(self.coach)
        response = self.client.get("/coach/daily-overview-other/")
        self.assertContains(response, "Meeting requested · 0d")
        self.assertContains(response, "Meeting requested · 2d")
        self.assertContains(response, "Meeting requested · 3d")
        self.assertContains(response, "Meeting requested · 5d")
        self.assertContains(response, "Meeting requested · 6d")
        self.assertContains(response, "btn-success")
        self.assertContains(response, "btn-warning")
        self.assertContains(response, "btn-danger")

    def test_athlete_cannot_clear_another_athletes_request(self):
        self.athlete.meeting_requested_at = timezone.now()
        self.athlete.save(update_fields=["meeting_requested_at"])
        self.other_user.username = "otherathlete"
        self.other_user.save(update_fields=["username"])
        self.client.force_login(self.other_user)

        self.client.post("/athlete/settings/", {"meeting_action": "cancel"})
        self.athlete.refresh_from_db()
        self.assertIsNotNone(self.athlete.meeting_requested_at)
