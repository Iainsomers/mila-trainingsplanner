from datetime import timedelta
from unittest.mock import patch
from django.test import TestCase
from django.utils import timezone
from core.models import Athlete, CorosMCPConnection, GarminActivity, TrainingSlot
from core.coros_sync import sync_due


class CorosSyncTests(TestCase):
    def setUp(self):
        self.athlete = Athlete.objects.create(name="Auto COROS", birth_year=2000, gender="X",
            coros_connection_enabled=True, device_time_zone="Europe/Amsterdam")
        self.connection = CorosMCPConnection.objects.create(athlete=self.athlete, client_id="mila",
            access_token="secret", consented_at=timezone.now())
        self.text = "Sport Records (2 records)\n1. Outdoor Run — 2026-11-16\n LabelId: 123 | SportType: 100\n2. Strength — 2026-11-15\n LabelId: 456 | SportType: 402"

    @patch("core.views.coros_mcp._start_session", return_value="session")
    @patch("core.views.coros_mcp._tool")
    @patch("core.views.coros_mcp._download_fit", return_value=b"original")
    @patch("core.views.coros_mcp.parse_fit")
    def test_new_files_import_once_and_sync_runs_without_browser(self, parse, download, tool, start):
        parse.return_value = {"human":{"activity_start":timezone.now()}}
        self.text = "Sport Records (1 records)\n1. Outdoor Run — 2026-11-16\n LabelId: 123 | SportType: 100"
        def result(connection, session, name, arguments):
            return {"content":[{"type":"text", "text":self.text if name == "querySportRecords" else "https://files.coros.com/file.fit"}]}
        tool.side_effect = result
        now = timezone.now()
        self.assertEqual(sync_due(now=now), 1)
        self.assertEqual(GarminActivity.objects.count(), 1)
        self.connection.refresh_from_db()
        self.assertIsNotNone(self.connection.last_import_at)
        self.assertEqual(self.connection.last_success_at, now)
        self.assertEqual(sync_due(now=now+timedelta(seconds=30)), 0)
        self.connection.next_sync_at = now
        self.connection.save()
        self.assertEqual(sync_due(now=now+timedelta(minutes=16)), 1)
        download.assert_called_once()
        self.assertFalse(TrainingSlot.objects.exists())

    @patch("core.views.coros_mcp._start_session", return_value="session")
    @patch("core.views.coros_mcp._tool")
    @patch("core.views.coros_mcp.import_activity")
    def test_failure_does_not_block_other_files_and_is_retried(self, save, tool, start):
        tool.return_value = {"content":[{"type":"text", "text":self.text}]}
        save.side_effect = [ValueError("private-url-token"), (None, True)]
        self.assertEqual(sync_due(), 1)
        self.assertEqual(save.call_count, 2)
        self.connection.refresh_from_db()
        self.assertIn("retried", self.connection.sync_error)
        self.assertNotIn("private", self.connection.sync_error)
        self.assertIsNone(self.connection.last_success_at)
        self.connection.next_sync_at = timezone.now()
        self.connection.save()
        save.side_effect = None
        sync_due()
        self.assertEqual(save.call_count, 4)

    @patch("core.views.coros_mcp._start_session")
    def test_disabled_and_claimed_connections_do_not_fetch(self, start):
        self.connection.next_sync_at = timezone.now()+timedelta(minutes=20)
        self.connection.save()
        self.assertEqual(sync_due(), 0)
        self.connection.next_sync_at = None
        self.connection.save()
        self.athlete.coros_connection_enabled = False
        self.athlete.save()
        self.assertEqual(sync_due(), 0)
        start.assert_not_called()

    @patch("core.views.coros_mcp._start_session", return_value="session")
    @patch("core.views.coros_mcp._tool")
    def test_overlapping_check_is_claimed_and_empty_result_succeeds(self, tool, start):
        def result(*args):
            self.assertEqual(sync_due(), 0)
            return {"content":[{"type":"text", "text":"Sport Records (0 records)"}]}
        tool.side_effect = result
        self.assertEqual(sync_due(), 1)
        self.connection.refresh_from_db()
        self.assertEqual(self.connection.sync_error, "")

    @patch("core.views.coros_mcp._start_session", return_value="session")
    @patch("core.views.coros_mcp._tool")
    def test_changed_response_format_reports_error_instead_of_silent_success(self, tool, start):
        tool.return_value = {"content":[{"type":"text", "text":"Unexpected response"}]}
        with self.assertLogs("core.coros_sync", level="WARNING"):
            sync_due()
        self.connection.refresh_from_db()
        self.assertTrue(self.connection.sync_error)
        self.assertIsNone(self.connection.last_success_at)
