from django.test import TestCase
from django.urls import reverse


class PrivacyPolicyPageTests(TestCase):
    def test_privacy_policy_is_public_and_contains_company_contact(self):
        response = self.client.get(reverse("privacy_policy"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Oaxley Trading BV")
        self.assertContains(response, "iainsomers@yahoo.com")
        self.assertContains(response, "Hardware settings panel")

    def test_terms_of_service_is_public_and_links_to_privacy_policy(self):
        response = self.client.get(reverse("terms_of_service"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "MiLa Planner Terms of Service")
        self.assertContains(response, "Oaxley Trading BV")
        self.assertContains(response, reverse("privacy_policy"))
