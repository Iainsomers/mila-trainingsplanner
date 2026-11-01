from datetime import datetime, timedelta, timezone as utc_timezone
from unittest.mock import patch
from zoneinfo import ZoneInfo

from django.contrib.auth import get_user_model
from django.test import TestCase, SimpleTestCase
from django.urls import reverse

from core.models import Athlete, AthleteDailyVital, OuraConnection
from core.oura_sync import next_check, sync_due
from core.views.oura import build_oura_vitals_suggestions


class OuraScheduleTests(SimpleTestCase):
    def test_window_boundaries_and_hourly_checks(self):
        zone = ZoneInfo("Europe/Amsterdam")
        for hour, minute, expected in ((6, 0, "06:30"), (6, 30, "06:40"),
                (7, 50, "08:00"), (8, 0, "09:00"), (8, 17, "09:00"), (23, 0, "00:00")):
            now = datetime(2026, 11, 1, hour, minute, tzinfo=zone)
            self.assertEqual(next_check(now, zone.key).astimezone(zone).strftime("%H:%M"), expected)

    def test_dst_and_fractional_hour_time_zones(self):
        for value, zone_name in (("2026-03-29T00:59:00+00:00", "Europe/Amsterdam"),
                                 ("2026-10-25T00:59:00+00:00", "Europe/Amsterdam"),
                                 ("2026-11-01T00:50:00+00:00", "Asia/Kolkata")):
            now = datetime.fromisoformat(value)
            due = next_check(now, zone_name)
            self.assertGreater(due, now)
            local = due.astimezone(ZoneInfo(zone_name))
            self.assertTrue(local.minute == 0 or (local.hour == 6 and local.minute == 30))


class OuraAutoImportTests(TestCase):
    def setUp(self):
        self.coach = get_user_model().objects.create_user(username="oura-auto-coach", is_staff=True)
        self.user = get_user_model().objects.create_user(username="Morning_Runner")
        self.athlete = Athlete.objects.create(owner=self.coach, name="Morning Runner", birth_year=2000,
            gender="X", oura_connection_enabled=True, oura_auto_import_enabled=True,
            device_time_zone="Europe/Amsterdam", daily_vitals_enabled=True)
        self.connection = OuraConnection.objects.create(athlete=self.athlete, access_token="private-token",
            health_data_consent_at=datetime(2026, 10, 1, tzinfo=utc_timezone.utc), consented_by=self.user)
        self.now = datetime(2026, 11, 1, 6, 30, tzinfo=ZoneInfo("Europe/Amsterdam"))
        self.suggestions = [{"day": "2026-11-01", "sleep_hours": 8, "sleep_quality": 8.2, "morning_hr": 47, "hrv": 70}]

    @patch("core.views.oura.build_oura_vitals_suggestions")
    def test_background_sync_fills_blanks_preserves_manual_values_and_runs_once(self, fetch):
        fetch.return_value = self.suggestions
        AthleteDailyVital.objects.create(athlete=self.athlete, date=self.now.date(), sleep_hours=6)
        self.assertEqual(sync_due(now=self.now), 1)
        vital = AthleteDailyVital.objects.get()
        self.assertEqual(vital.sleep_hours, 6)
        self.assertEqual(vital.hrv, 70)
        self.assertEqual(vital.updated_by, self.user)
        self.assertEqual(sync_due(now=self.now + timedelta(seconds=30)), 0)
        fetch.assert_called_once()
        self.athlete.refresh_from_db()
        self.assertEqual(self.athlete.oura_next_check_at.astimezone(ZoneInfo("Europe/Amsterdam")).strftime("%H:%M"), "06:40")

    @patch("core.views.oura.build_oura_vitals_suggestions")
    def test_disallowed_disconnected_disabled_or_unknown_zone_never_fetch(self, fetch):
        for field, value in (("oura_auto_import_enabled", False), ("oura_connection_enabled", False),
                              ("daily_vitals_enabled", False), ("device_time_zone", "")):
            original = getattr(self.athlete, field)
            setattr(self.athlete, field, value)
            self.athlete.save()
            self.assertEqual(sync_due(now=self.now), 0)
            setattr(self.athlete, field, original)
            self.athlete.save()
        self.connection.delete()
        self.assertEqual(sync_due(now=self.now), 0)
        fetch.assert_not_called()

    @patch("core.views.oura.build_oura_vitals_suggestions")
    def test_nothing_is_written_when_disabled_during_fetch(self, fetch):
        def disable(*args, **kwargs):
            Athlete.objects.filter(pk=self.athlete.pk).update(oura_auto_import_enabled=False)
            return self.suggestions
        fetch.side_effect = disable
        sync_due(now=self.now)
        self.assertFalse(AthleteDailyVital.objects.exists())

    @patch("core.views.oura.build_oura_vitals_suggestions")
    def test_failure_is_private_and_retries_at_next_slot(self, fetch):
        fetch.side_effect = ValueError("private failure details")
        with self.assertLogs("core.oura_sync", level="WARNING") as logged:
            sync_due(now=self.now)
        self.assertNotIn("private failure details", " ".join(logged.output))
        self.athlete.refresh_from_db()
        self.assertGreater(self.athlete.oura_next_check_at, self.now)
        self.assertFalse(AthleteDailyVital.objects.exists())

    @patch("core.views.oura.build_oura_test_data")
    def test_readiness_must_be_available_and_valid(self, preview):
        for readiness in (None, "-", float("nan"), True, 101):
            preview.return_value = [{"day": self.now.date(), "readiness_score": readiness}]
            self.assertEqual(build_oura_vitals_suggestions(self.connection, self.athlete, today=self.now.date()), [])

    def test_device_zone_is_validated_owned_and_not_counted_as_interactive_activity(self):
        self.client.force_login(self.user)
        url = reverse("oura_device_timezone")
        self.assertEqual(self.client.post(url, {"time_zone": "Not/AZone"}).status_code, 400)
        self.assertEqual(self.client.post(url, {"time_zone": "Asia/Tokyo", "athlete": 999}).status_code, 200)
        self.athlete.refresh_from_db()
        self.assertEqual(self.athlete.device_time_zone, "Asia/Tokyo")
        self.assertIsNone(self.athlete.last_active_at)
        self.client.force_login(self.coach)
        self.assertEqual(self.client.post(url, {"time_zone": "Europe/London"}).status_code, 403)

    @patch("core.views.oura.build_oura_vitals_suggestions")
    def test_outside_window_waits_until_local_hour(self, fetch):
        self.assertEqual(sync_due(now=self.now.replace(hour=8, minute=17)), 0)
        fetch.assert_not_called()
        self.athlete.refresh_from_db()
        self.assertEqual(self.athlete.oura_next_check_at.astimezone(ZoneInfo("Europe/Amsterdam")).hour, 9)

    @patch("core.views.oura.build_oura_vitals_suggestions")
    def test_lease_prevents_overlapping_worker_fetch(self, fetch):
        self.athlete.oura_next_check_at = self.now + timedelta(minutes=15)
        self.athlete.save()
        self.assertEqual(sync_due(now=self.now), 0)
        fetch.assert_not_called()

    @patch("core.views.oura.build_oura_vitals_suggestions")
    def test_uses_athlete_local_day_when_utc_is_previous_day(self, fetch):
        self.athlete.device_time_zone = "Asia/Tokyo"
        self.athlete.save()
        fetch.return_value = []
        now = datetime(2026, 11, 1, 21, 30, tzinfo=utc_timezone.utc)  # Nov 2, 06:30 on device.
        sync_due(now=now)
        self.assertEqual(str(fetch.call_args.kwargs["today"]), "2026-11-02")

    def test_athlete_can_save_auto_import_preference(self):
        self.client.force_login(self.user)
        page = self.client.get("/athlete/settings/")
        self.assertContains(page, 'name="oura_auto_import_enabled"')
        self.assertContains(page, "Europe/Amsterdam")
        data = {"name": self.athlete.name, "birth_year": "2000", "gender": "X",
                "zone_method": "manual", "oura_auto_import_enabled": "on"}
        data.update({f"z{index}_pace": pace for index, pace in enumerate(("6:00", "5:30", "5:00", "4:30", "4:00"), 1)})
        response = self.client.post("/athlete/settings/", data)
        self.assertEqual(response.status_code, 302, response.context["errors"] if response.context else "no context")
        self.athlete.refresh_from_db()
        self.assertTrue(self.athlete.oura_auto_import_enabled)
        data.pop("oura_auto_import_enabled")
        self.client.post("/athlete/settings/", data)
        self.athlete.refresh_from_db()
        self.assertFalse(self.athlete.oura_auto_import_enabled)

    @patch("core.views.oura.build_oura_vitals_suggestions")
    def test_manual_entry_arriving_during_fetch_is_preserved(self, fetch):
        def manual_entry(*args, **kwargs):
            AthleteDailyVital.objects.create(athlete=self.athlete, date=self.now.date(), hrv=55)
            return self.suggestions
        fetch.side_effect = manual_entry
        sync_due(now=self.now)
        vital = AthleteDailyVital.objects.get()
        self.assertEqual(vital.hrv, 55)
        self.assertEqual(vital.morning_hr, 47)
