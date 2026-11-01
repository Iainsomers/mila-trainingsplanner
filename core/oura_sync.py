"""Oura polling in the athlete's last known device zone; no browser required."""
from datetime import timedelta, timezone as utc_timezone
import logging
import threading
from zoneinfo import ZoneInfo

from django.db import close_old_connections, transaction
from django.db.models import Q
from django.utils import timezone

from core.models import Athlete, OuraConnection

logger = logging.getLogger(__name__)
_thread = None


def next_check(now, time_zone):
    """Scan real UTC minutes so both DST transitions keep correct local slots."""
    zone = ZoneInfo(time_zone)
    candidate = now.astimezone(utc_timezone.utc).replace(second=0, microsecond=0) + timedelta(minutes=1)
    for _ in range(1500):
        local = candidate.astimezone(zone)
        minute = local.hour * 60 + local.minute
        morning = 390 <= minute <= 480
        if (morning and local.minute % 10 == 0) or (not morning and local.minute == 0):
            return candidate
        candidate += timedelta(minutes=1)
    raise ValueError("No scheduling slot")


def sync_due(*, now=None):
    from core.views.oura import build_oura_vitals_suggestions, apply_oura_vitals_suggestions
    now = now or timezone.now()
    athletes = Athlete.objects.filter(oura_auto_import_enabled=True, oura_connection_enabled=True,
        daily_vitals_enabled=True, oura_connection__isnull=False).exclude(device_time_zone="").filter(
            Q(oura_next_check_at__isnull=True) | Q(oura_next_check_at__lte=now))
    processed = 0
    for athlete in athletes.iterator():
        try:
            zone = ZoneInfo(athlete.device_time_zone)
            due = athlete.oura_next_check_at or next_check(now - timedelta(minutes=1), athlete.device_time_zone)
            if due > now:
                Athlete.objects.filter(pk=athlete.pk, oura_next_check_at__isnull=True).update(oura_next_check_at=due)
                continue
            # The database claim also protects overlapping web workers/deploys.
            claimed_until = now + timedelta(minutes=15)
            claimed = Athlete.objects.filter(pk=athlete.pk, oura_auto_import_enabled=True,
                oura_connection_enabled=True, device_time_zone=athlete.device_time_zone).filter(
                    Q(oura_next_check_at__isnull=True) | Q(oura_next_check_at__lte=now)).update(oura_next_check_at=claimed_until)
            if not claimed:
                continue
            connection = OuraConnection.objects.filter(athlete=athlete).first()
            if not connection:
                continue
            try:
                with timezone.override(zone):
                    suggestions = build_oura_vitals_suggestions(connection, athlete, today=now.astimezone(zone).date())
                with transaction.atomic():
                    current = Athlete.objects.select_for_update().get(pk=athlete.pk)
                    if (current.oura_auto_import_enabled and current.oura_connection_enabled
                            and current.daily_vitals_enabled and current.device_time_zone == athlete.device_time_zone
                            and OuraConnection.objects.filter(pk=connection.pk, athlete=current).exists()):
                        saved = apply_oura_vitals_suggestions(current, suggestions, actor=connection.consented_by)
                        if saved:
                            logger.info("Oura automatic import saved %s day(s)", len(saved))
                processed += 1
            finally:
                Athlete.objects.filter(pk=athlete.pk, oura_next_check_at=claimed_until).update(
                    oura_next_check_at=next_check(now, athlete.device_time_zone), oura_last_check_at=now)
        except Exception as error:
            # No tokens, user identifiers, API response bodies or health values.
            logger.warning("Oura automatic check failed: %s", type(error).__name__)
    return processed


def start_worker():
    """One lightweight daemon per web process; DB claims prevent duplicate pulls."""
    global _thread
    if _thread is not None and _thread.is_alive():
        return

    def run():
        while True:
            try:
                close_old_connections()
                sync_due()
            except Exception as error:
                logger.warning("Oura scheduler failed: %s", type(error).__name__)
            finally:
                close_old_connections()
            threading.Event().wait(30)

    _thread = threading.Thread(target=run, name="oura-auto-import", daemon=True)
    _thread.start()
    logger.info("Oura automatic import worker started")
