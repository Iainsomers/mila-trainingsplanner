import json
from datetime import datetime, timezone as dt_timezone
from unittest.mock import Mock, patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings, Client
from django.urls import reverse
from django.utils import timezone

from core.models import Athlete, GarminConnection, GarminActivitySummary
from core.views.garmin import receiver_key, revoke_connection


@override_settings(GARMIN_CLIENT_ID="test-client", GARMIN_CLIENT_SECRET="test-secret",
                   GARMIN_REDIRECT_URI="https://example.org/callback/")
class GarminPushTests(TestCase):
    def setUp(self):
        self.coach = get_user_model().objects.create_user(username="push-coach", is_staff=True)
        self.athlete = Athlete.objects.create(owner=self.coach, name="Push Runner", birth_year=2000,
            gender="X", garmin_connection_enabled=True)
        self.connection = GarminConnection.objects.create(athlete=self.athlete, garmin_user_id="garmin-user-1",
            access_token="private-access", data_consent_at=timezone.now())
        self.url = reverse("garmin_activity_push", args=[receiver_key()])
        self.item = {"userId": "garmin-user-1", "activityId": 1234, "summaryId": "summary-1234",
            "startTimeInSeconds": int(datetime(2026, 10, 30, 23, 30, tzinfo=dt_timezone.utc).timestamp()),
            "startTimeOffsetInSeconds": 7200, "distanceInMeters": 12345.6,
            "userAccessToken": "must-not-be-stored", "startingLatitudeInDegree": 52.0}

    def push(self, items=None, url=None):
        return self.client.post(url or self.url, json.dumps({"activities": items if items is not None else [self.item]}), content_type="application/json")

    def test_authenticated_push_is_immediately_visible_on_correct_athlete_page(self):
        self.assertEqual(self.push().status_code, 200)
        saved = GarminActivitySummary.objects.get()
        self.assertEqual(saved.athlete, self.athlete)
        self.assertEqual(str(saved.activity_date), "2026-10-31")  # Garmin device offset, not server date.
        self.assertEqual(saved.distance_m, 12345.6)
        self.assertEqual(saved.activity_id, "1234")
        self.client.force_login(self.coach)
        page = self.client.get(reverse("garmin_athlete_activities", args=[self.athlete.pk]))
        self.assertContains(page, "31-10-2026")
        self.assertContains(page, "12.35 km")
        self.assertNotContains(page, "must-not-be-stored")
        self.assertNotContains(page, "private-access")

    def test_retries_do_not_duplicate_and_changed_distance_updates_record(self):
        self.push()
        self.push()
        self.item["distanceInMeters"] = 15000
        self.push()
        self.assertEqual(GarminActivitySummary.objects.count(), 1)
        self.assertEqual(GarminActivitySummary.objects.get().distance_m, 15000)

    def test_receiver_requires_private_key_and_does_not_require_browser_csrf(self):
        wrong = reverse("garmin_activity_push", args=["wrong-key"])
        self.assertEqual(self.push(url=wrong).status_code, 403)
        self.assertFalse(GarminActivitySummary.objects.exists())
        secure_client = Client(enforce_csrf_checks=True)
        response = secure_client.post(self.url, json.dumps({"activities": [self.item]}), content_type="application/json")
        self.assertEqual(response.status_code, 200)
        with override_settings(GARMIN_CLIENT_SECRET=""):
            self.assertEqual(self.push().status_code, 403)

    def test_unknown_disabled_and_disconnected_athletes_receive_no_data(self):
        self.assertEqual(self.push([{**self.item, "userId": "unknown"}]).status_code, 200)
        self.athlete.garmin_connection_enabled = False
        self.athlete.save()
        self.assertEqual(self.push().status_code, 200)
        self.athlete.garmin_connection_enabled = True
        self.athlete.save()
        with patch("core.views.garmin.requests.delete", return_value=Mock(status_code=204)):
            revoke_connection(self.athlete)
        self.assertEqual(self.push().status_code, 200)
        self.assertFalse(GarminActivitySummary.objects.exists())

    def test_malformed_batch_is_rejected_without_partial_writes_or_callbacks(self):
        variants = [None, {}, {**self.item, "distanceInMeters": -1},
            {**self.item, "distanceInMeters": float("nan")},
            {**self.item, "startTimeInSeconds": "not-a-date"},
            {"userId": "garmin-user-1", "callbackURL": "http://localhost/private"}]
        with patch("core.views.garmin.requests.get") as get:
            for invalid in variants:
                self.assertEqual(self.push([self.item, invalid]).status_code, 400)
            get.assert_not_called()
        self.assertFalse(GarminActivitySummary.objects.exists())

    def test_payload_limits_and_get_do_not_process_data(self):
        self.assertEqual(self.client.get(self.url).status_code, 405)
        self.assertEqual(self.client.post(self.url, "not-json", content_type="application/json").status_code, 400)
        self.assertEqual(self.push([self.item] * 501).status_code, 400)
        self.assertEqual(self.client.post(self.url, " " * 1_000_001, content_type="application/json").status_code, 413)

    @patch("core.views.garmin.requests.get")
    def test_existing_oauth_connection_is_resolved_using_garmin_identity(self, get):
        self.connection.garmin_user_id = None
        self.connection.save()
        get.return_value = Mock(json=lambda: {"userId": "garmin-user-1"})
        self.assertEqual(self.push().status_code, 200)
        self.connection.refresh_from_db()
        self.assertEqual(self.connection.garmin_user_id, "garmin-user-1")
        self.assertEqual(get.call_args.kwargs["headers"]["Authorization"], "Bearer private-access")
        self.assertEqual(GarminActivitySummary.objects.count(), 1)

    @patch("core.views.garmin.requests.get")
    def test_identity_errors_are_retried_instead_of_assigning_by_name(self, get):
        self.connection.garmin_user_id = None
        self.connection.save()
        get.return_value = Mock(json=lambda: {})
        self.assertEqual(self.push().status_code, 503)
        self.assertFalse(GarminActivitySummary.objects.exists())

    def test_receiving_setup_credential_is_only_visible_to_administrator(self):
        self.client.force_login(self.coach)
        self.assertNotContains(self.client.get(reverse("garmin_connections")), receiver_key())
        administrator = get_user_model().objects.create_user(username="push-admin", is_superuser=True, is_staff=True)
        self.client.force_login(administrator)
        page = self.client.get(reverse("garmin_connections"))
        self.assertContains(page, self.url)
        self.assertEqual(page["Cache-Control"], "private, no-store")

    @patch("core.views.garmin.requests.get")
    def test_admin_can_copy_resolved_user_id_but_coach_cannot_see_it(self, get):
        self.connection.garmin_user_id = None
        self.connection.save()
        get.return_value = Mock(json=lambda: {"userId": "resolved-garmin-id"})
        self.client.force_login(self.coach)
        url = reverse("garmin_athlete_activities", args=[self.athlete.pk])
        page = self.client.get(url)
        self.assertNotContains(page, 'id="garmin-user-id"')
        get.assert_not_called()
        self.coach.is_superuser = True
        self.coach.save()
        page = self.client.get(url)
        self.assertContains(page, 'value="resolved-garmin-id"')
        self.assertContains(page, "Summary Resender")
        self.assertNotContains(page, "private-access")
        self.assertEqual(page["Cache-Control"], "private, no-store")
        self.connection.refresh_from_db()
        self.assertEqual(self.connection.garmin_user_id, "resolved-garmin-id")

    @patch("core.views.garmin.requests.get")
    def test_identity_failure_keeps_connection_and_activity_page_available(self, get):
        self.connection.garmin_user_id = None
        self.connection.save()
        get.return_value = Mock(json=lambda: {})
        self.coach.is_superuser = True
        self.coach.save()
        self.client.force_login(self.coach)
        page = self.client.get(reverse("garmin_athlete_activities", args=[self.athlete.pk]))
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, "could not be retrieved")
        self.assertTrue(GarminConnection.objects.filter(pk=self.connection.pk).exists())

    def test_push_never_crosses_athletes_even_with_misleading_athlete_id(self):
        other = Athlete.objects.create(owner=self.coach, name="Other Push Runner", birth_year=2000,
            gender="X", garmin_connection_enabled=True)
        GarminConnection.objects.create(athlete=other, garmin_user_id="garmin-user-2",
            access_token="other-private-token", data_consent_at=timezone.now())
        self.assertEqual(self.push([{**self.item, "athlete_id": other.pk},
            {**self.item, "userId": "garmin-user-2", "distanceInMeters": 5000}]).status_code, 200)
        self.assertEqual(GarminActivitySummary.objects.get(athlete=self.athlete).distance_m, 12345.6)
        self.assertEqual(GarminActivitySummary.objects.get(athlete=other).distance_m, 5000)

    @patch("core.views.garmin.requests.post")
    @patch("core.views.garmin.requests.get")
    def test_identity_resolution_refreshes_expired_oauth_and_rotates_tokens(self, get, post):
        self.connection.garmin_user_id = None
        self.connection.token_expires_at = timezone.now() - timezone.timedelta(seconds=1)
        self.connection.refresh_token = "old-refresh"
        self.connection.save()
        post.return_value = Mock(json=lambda: {"access_token": "new-access", "refresh_token": "new-refresh", "expires_in": 3600})
        get.return_value = Mock(json=lambda: {"userId": "garmin-user-1"})
        self.assertEqual(self.push().status_code, 200)
        self.connection.refresh_from_db()
        self.assertEqual(self.connection.refresh_token, "new-refresh")
        self.assertEqual(get.call_args.kwargs["headers"]["Authorization"], "Bearer new-access")

    @patch("core.views.garmin.requests.get")
    def test_disconnect_during_identity_resolution_does_not_restore_connection(self, get):
        self.connection.garmin_user_id = None
        self.connection.save()
        def disconnect(*args, **kwargs):
            self.connection.delete()
            return Mock(json=lambda: {"userId": "garmin-user-1"})
        get.side_effect = disconnect
        self.assertEqual(self.push().status_code, 503)
        self.assertFalse(GarminConnection.objects.exists())
        self.assertFalse(GarminActivitySummary.objects.exists())
