"""Poll connected COROS athletes independently of browser visits."""
import logging
import re
import secrets
import threading
from datetime import timedelta
from time import monotonic
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django.db import close_old_connections
from django.db.models import Q
from django.utils import timezone
from core.models import CorosMCPConnection

logger = logging.getLogger(__name__)
_thread = None


def sync_due(*, now=None):
    from core.views.coros_mcp import _start_session, _tool, _text, _activity_rows, import_activity
    now = now or timezone.now()
    due = Q(next_sync_at__isnull=True) | Q(next_sync_at__lte=now)
    processed = 0
    for connection in CorosMCPConnection.objects.filter(due, athlete__coros_connection_enabled=True).iterator():
        claim = secrets.token_hex(16)
        if not CorosMCPConnection.objects.filter(due, pk=connection.pk,
                athlete__coros_connection_enabled=True).update(next_sync_at=now + timedelta(minutes=20), sync_claim=claim):
            continue
        error = ""
        deadline = monotonic() + 600
        try:
            session = _start_session(connection)
            today = timezone.localdate(now)
            try:
                if connection.athlete.device_time_zone:
                    today = now.astimezone(ZoneInfo(connection.athlete.device_time_zone)).date()
            except ZoneInfoNotFoundError:
                pass
            rows = []
            # Explicit range with a high limit, splitting by day if saturated.
            content = _tool(connection, session, "querySportRecords", {"startDate":(today-timedelta(days=6)).strftime("%Y%m%d"),
                "endDate":today.strftime("%Y%m%d"), "limit":200})
            text = _text(content)
            rows = _activity_rows(text, None, connection)
            if text.strip() and not rows and not re.search(r"\b0\s+records?\b|no (?:matching )?(?:activities|records)", text, re.I):
                raise ValueError("Unsupported activity list")
            if len(rows) >= 200:
                rows = []
                for offset in range(7):
                    day = (today - timedelta(days=offset)).strftime("%Y%m%d")
                    batch = _activity_rows(_text(_tool(connection, session, "querySportRecords",
                        {"startDate":day, "endDate":day, "limit":200})), None, connection)
                    if len(batch) >= 200:
                        raise ValueError("Activity list saturated")
                    rows.extend(batch)
            pending = [row for row in rows if not row["imported"]]
            for row in pending[:10]:
                if monotonic() >= deadline:
                    error = "More activities are queued for the next automatic check."
                    break
                try:
                    import_activity(connection, session, row["label"], row["sport_code"])
                except Exception:
                    error = "Some FIT files could not be imported; they will be retried automatically."
            if len(pending) > 10 and not error:
                error = "More activities are queued for the next automatic check."
            processed += 1
            if not error:
                CorosMCPConnection.objects.filter(pk=connection.pk, sync_claim=claim).update(last_success_at=now)
        except Exception as exc:
            error = "COROS automatic check failed. It will retry in 15 minutes. Reconnect if the problem persists."
            logger.warning("COROS automatic check failed: %s", type(exc).__name__)
        finally:
            CorosMCPConnection.objects.filter(pk=connection.pk, sync_claim=claim).update(
                next_sync_at=timezone.now()+timedelta(minutes=15), sync_claim="", last_sync_at=now, sync_error=error)
    return processed


def start_worker():
    global _thread
    if _thread is not None and _thread.is_alive():
        return
    def run():
        while True:
            try:
                close_old_connections()
                sync_due()
            except Exception as exc:
                logger.warning("COROS scheduler failed: %s", type(exc).__name__)
            finally:
                close_old_connections()
            threading.Event().wait(30)
    _thread = threading.Thread(target=run, name="coros-auto-import", daemon=True)
    _thread.start()
