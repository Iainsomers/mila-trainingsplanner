import json
from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase

from core.models import Athlete, YearPlannerWhereabout
from core.views.calendar import _whereabout_dots


class YearPlannerOtherWhereaboutsTests(TestCase):
    def setUp(self):
        self.coach = get_user_model().objects.create_user(
            username="other-whereabouts-coach",
            password="secret",
            is_staff=True,
        )
        self.athlete = Athlete.objects.create(
            owner=self.coach,
            name="Other Whereabouts Athlete",
            birth_year=2000,
            gender="X",
        )
        self.client.force_login(self.coach)

    def test_other_whereabouts_can_be_saved_and_rendered(self):
        day = date(2026, 11, 12)

        response = self.client.post(
            "/planning/year/whereabout/",
            data=json.dumps({
                "scope": f"athlete-{self.athlete.id}",
                "start_date": day.isoformat(),
                "end_date": day.isoformat(),
                "whereabouts": "other",
                "note": "Other appointment",
            }),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(YearPlannerWhereabout.objects.filter(
            athlete=self.athlete,
            whereabouts_type="other",
            note="Other appointment",
        ).exists())

        page = self.client.get(
            f"/planning/year/?year=2026&period=full&athletes={self.athlete.id}"
        )
        self.assertContains(page, 'year-where-other text-white">Other</span>')
        self.assertContains(page, "Other appointment")
        self.assertContains(page, "year-where-other")

    def test_other_whereabouts_uses_its_own_diary_dot_colour(self):
        day = date(2026, 11, 12)
        YearPlannerWhereabout.objects.create(
            owner=self.coach,
            athlete=self.athlete,
            start_date=day,
            end_date=day,
            whereabouts_type="other",
            note="Other appointment",
        )

        dots = _whereabout_dots(
            self.coach,
            [self.athlete.id],
            day,
            day + timedelta(days=1),
        )

        self.assertEqual(
            dots[(self.athlete.id, day)],
            [{"type": "other", "color": "#34495e"}],
        )
