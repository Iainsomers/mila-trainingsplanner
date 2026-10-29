from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from core.models import Athlete


class AthletePolarPermissionTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.coach = User.objects.create_user(username="polar-coach", password="pw", is_staff=True)
        self.athlete_user = User.objects.create_user(
            username="polar-runner", password="pw", first_name="Polar", last_name="Runner"
        )
        self.athlete = Athlete.objects.create(
            owner=self.coach,
            name="Polar Runner",
            birth_year=2005,
            gender="M",
        )
        self.client.force_login(self.athlete_user)

    def test_polar_access_is_off_by_default_and_enforced_on_pages_and_api(self):
        dashboard = self.client.get(reverse("dashboard"))
        calendar = self.client.get(reverse("athlete_year_calendar"))
        integration = self.client.get(reverse("polar_integration"))
        api = self.client.get(
            reverse("polar_type_a_ayc"), {"athlete": self.athlete.id, "date": "2026-10-29"}
        )

        self.assertFalse(self.athlete.polar_enabled)
        self.assertNotContains(dashboard, "Polar (under development)")
        self.assertNotContains(calendar, 'id="suggestInputBtn"')
        self.assertNotContains(calendar, 'id="suggestInputBtnB"')
        self.assertRedirects(integration, reverse("dashboard"), fetch_redirect_response=False)
        self.assertEqual(api.status_code, 403)

    def test_coach_permission_exposes_polar_for_the_athlete(self):
        self.athlete.polar_enabled = True
        self.athlete.save(update_fields=["polar_enabled"])

        dashboard = self.client.get(reverse("dashboard"))
        calendar = self.client.get(reverse("athlete_year_calendar"))

        self.assertContains(dashboard, "Polar (under development)")
        self.assertContains(calendar, 'id="suggestInputBtn"')
        self.assertContains(calendar, 'id="suggestInputBtnB"')
