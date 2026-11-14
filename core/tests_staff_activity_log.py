from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from core.models import (
    Athlete,
    AthleteActivityEvent,
    AthleteDailyVital,
    AthleteDayCheck,
    CoachAccess,
    CoachSettings,
)


class StaffActivityLogTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.coach = User.objects.create_user(
            username="log-coach", password="secret", is_staff=True
        )
        self.athlete = Athlete.objects.create(
            owner=self.coach,
            name="Log Athlete",
            birth_year=2000,
            gender="X",
            training_reports_enabled=True,
            daily_vitals_enabled=True,
        )

    def test_saving_athlete_updates_creates_append_only_events(self):
        AthleteDayCheck.objects.create(
            athlete=self.athlete,
            date=date.today(),
            slot_index=1,
            checked=True,
            rpe=4,
            comment="Felt good",
            updated_by=self.coach,
        )
        AthleteDailyVital.objects.create(
            athlete=self.athlete,
            date=date.today(),
            sleep_hours=8,
            sleep_quality=7.5,
            updated_by=self.coach,
        )

        self.assertEqual(self.athlete.activity_events.count(), 2)
        evaluation = self.athlete.activity_events.get(
            category=AthleteActivityEvent.CATEGORY_EVALUATION
        )
        self.assertIn("RPE 4", evaluation.detail)
        self.assertEqual(evaluation.metadata["slot"], "AM")
        vitals = self.athlete.activity_events.get(
            category=AthleteActivityEvent.CATEGORY_VITALS
        )
        self.assertIn("Sleep quality: 7.5", vitals.detail)

    def test_log_shows_only_accessible_events_from_last_24_hours(self):
        other_coach = get_user_model().objects.create_user(
            username="other-log-coach", password="secret", is_staff=True
        )
        other_athlete = Athlete.objects.create(
            owner=other_coach,
            name="Hidden Log Athlete",
            birth_year=2001,
            gender="X",
        )
        AthleteActivityEvent.objects.create(
            athlete=self.athlete,
            category=AthleteActivityEvent.CATEGORY_WATCH,
            title="Visible recent event",
        )
        old_event = AthleteActivityEvent.objects.create(
            athlete=self.athlete,
            category=AthleteActivityEvent.CATEGORY_WATCH,
            title="Visible but old event",
        )
        AthleteActivityEvent.objects.filter(pk=old_event.pk).update(
            occurred_at=timezone.now() - timedelta(hours=25)
        )
        AthleteActivityEvent.objects.create(
            athlete=other_athlete,
            category=AthleteActivityEvent.CATEGORY_WATCH,
            title="Inaccessible recent event",
        )
        self.client.force_login(self.coach)

        response = self.client.get("/coach/daily-overview-other/", {"view": "log"})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Last 24 hours")
        self.assertContains(response, "Visible recent event")
        self.assertNotContains(response, "Visible but old event")
        self.assertNotContains(response, "Inaccessible recent event")

    def test_log_includes_events_for_athletes_shared_with_coach(self):
        owner = get_user_model().objects.create_user(
            username="shared-log-owner", password="secret", is_staff=True
        )
        shared_athlete = Athlete.objects.create(
            owner=owner,
            name="Shared Log Athlete",
            birth_year=2002,
            gender="X",
        )
        CoachAccess.objects.create(owner=owner, grantee=self.coach, can_edit=False)
        AthleteActivityEvent.objects.create(
            athlete=shared_athlete,
            category=AthleteActivityEvent.CATEGORY_WATCH,
            title="Shared recent event",
        )
        self.client.force_login(self.coach)
        session = self.client.session
        session["active_coach_owner_id"] = owner.id
        session.save()

        response = self.client.get("/coach/daily-overview-other/", {"view": "log"})

        self.assertContains(response, "Shared Log Athlete")
        self.assertContains(response, "Shared recent event")

    def test_log_is_not_available_to_athlete_user(self):
        athlete_user = get_user_model().objects.create_user(
            username="Log Athlete", password="secret"
        )
        self.client.force_login(athlete_user)

        response = self.client.get("/coach/daily-overview-other/", {"view": "log"})

        self.assertEqual(response.status_code, 403)

    def test_log_respects_shared_evaluation_privacy(self):
        owner = get_user_model().objects.create_user(
            username="private-log-owner", password="secret", is_staff=True
        )
        shared_athlete = Athlete.objects.create(
            owner=owner,
            name="Privacy Log Athlete",
            birth_year=2003,
            gender="X",
            training_reports_enabled=True,
            week_report_enabled=True,
            daily_vitals_enabled=True,
        )
        CoachAccess.objects.create(owner=owner, grantee=self.coach, can_edit=False)
        CoachSettings.objects.create(user=owner, evaluation_sharing_enabled=True)
        for category, title in (
            (AthleteActivityEvent.CATEGORY_EVALUATION, "Private evaluation event"),
            (AthleteActivityEvent.CATEGORY_WEEK_REPORT, "Private week event"),
            (AthleteActivityEvent.CATEGORY_VITALS, "Private vitals event"),
            (AthleteActivityEvent.CATEGORY_WATCH, "Visible watch event"),
        ):
            AthleteActivityEvent.objects.create(
                athlete=shared_athlete,
                category=category,
                title=title,
            )
        self.client.force_login(self.coach)
        session = self.client.session
        session["active_coach_owner_id"] = owner.id
        session.save()

        response = self.client.get("/coach/daily-overview-other/", {"view": "log"})

        self.assertContains(response, "Visible watch event")
        self.assertNotContains(response, "Private evaluation event")
        self.assertNotContains(response, "Private week event")
        self.assertNotContains(response, "Private vitals event")
