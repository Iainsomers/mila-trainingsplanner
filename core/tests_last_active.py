from datetime import datetime, timezone as utc_timezone, timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.http import HttpResponse, JsonResponse
from django.test import TestCase, RequestFactory, override_settings
from django.utils import timezone

from core.middleware import AthleteLastActiveMiddleware
from core.models import Athlete


class AthleteLastActiveTests(TestCase):
    def setUp(self):
        self.coach = get_user_model().objects.create_user(username="active-coach", is_staff=True)
        self.user = get_user_model().objects.create_user(username="Activity_Runner")
        self.athlete = Athlete.objects.create(owner=self.coach, name="Activity Runner", birth_year=2000, gender="X")
        self.factory = RequestFactory()

    def visit(self, *, method="get", path="/athlete/year/", user=None, response=None, **headers):
        request = getattr(self.factory, method)(path, **headers)
        request.user = user or self.user
        return AthleteLastActiveMiddleware(lambda request: response if response is not None else HttpResponse("Page"))(request)

    def last_active(self):
        self.athlete.refresh_from_db()
        return self.athlete.last_active_at

    @patch("django.utils.timezone.now")
    def test_page_navigation_and_user_save_record_activity(self, now):
        first = datetime(2026, 10, 31, 10, tzinfo=utc_timezone.utc)
        now.return_value = first
        self.visit(HTTP_SEC_FETCH_MODE="navigate")
        self.assertEqual(self.last_active(), first)
        now.return_value = first + timedelta(minutes=5)
        self.visit(method="post", response=JsonResponse({"ok": True}), HTTP_SEC_FETCH_MODE="cors")
        self.assertEqual(self.last_active(), first + timedelta(minutes=5))

    def test_coach_background_import_and_failed_requests_do_not_record_activity(self):
        self.visit(user=self.coach)
        self.visit(HTTP_SEC_FETCH_MODE="cors")
        self.visit(HTTP_X_REQUESTED_WITH="XMLHttpRequest")
        self.visit(HTTP_SEC_FETCH_MODE="navigate", HTTP_SEC_PURPOSE="prefetch;prerender")
        self.visit(response=JsonResponse({"ok": True}))
        self.visit(method="post", path="/integrations/garmin/activities/test-key/")
        self.visit(method="post", path="/integrations/coros/workouts/")
        self.visit(response=HttpResponse(status=403))
        self.visit(response=HttpResponse(status=500))
        self.assertIsNone(self.last_active())

    def test_login_followed_by_still_authenticated_page_records_real_use(self):
        self.client.force_login(self.user)
        self.assertIsNone(self.last_active())  # Auth last_login is not interactive activity history.
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIsNotNone(self.last_active())

    @override_settings(TIME_ZONE="Europe/Amsterdam")
    @patch("core.views.coach.timezone.now")
    def test_information_quality_colors_dates_and_na_use_local_calendar_days(self, now):
        # UTC is still 30 October, but Amsterdam is already 31 October.
        now.return_value = datetime(2026, 10, 30, 23, 30, tzinfo=utc_timezone.utc)
        entries = [
            ("Today Active", datetime(2026, 10, 30, 23, 5, tzinfo=utc_timezone.utc), "green"),
            ("Yesterday Active", datetime(2026, 10, 30, 12, 0, tzinfo=utc_timezone.utc), "orange"),
            ("Older Active", datetime(2026, 10, 29, 12, 0, tzinfo=utc_timezone.utc), "red"),
        ]
        for name, last, color in entries:
            Athlete.objects.create(owner=self.coach, name=name, birth_year=2000, gender="X", last_active_at=last)
        foreign_coach = get_user_model().objects.create_user(username="foreign-active-coach", is_staff=True)
        Athlete.objects.create(owner=foreign_coach, name="Private Foreign Activity", birth_year=2000, gender="X", last_active_at=now.return_value)
        self.client.force_login(self.coach)
        response = self.client.get("/coach/daily-overview-other/", {"view": "information_quality"})
        self.assertEqual(response.status_code, 200)
        rows = {row["athlete"].name: row for row in response.context["athlete_rows"]}
        for name, last, color in entries:
            self.assertEqual(rows[name]["last_active_at"], last)
            self.assertEqual(rows[name]["last_active_color"], color)
        self.assertIsNone(rows[self.athlete.name]["last_active_at"])
        self.assertContains(response, "Last active in MiLa")
        self.assertContains(response, "31-10-2026 00:05")
        self.assertContains(response, "NA")
        self.assertNotContains(response, "Private Foreign Activity")
        self.assertIsNone(self.last_active())  # Coach visiting does not refresh athlete activity.
