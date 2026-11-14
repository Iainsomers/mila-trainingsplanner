"""Create durable staff-log events from athlete-related changes."""

from django.db.models.signals import post_save
from django.dispatch import receiver

from core.models import (
    AthleteActivityEvent,
    AthleteDailyVital,
    AthleteDayCheck,
    AthleteDayComment,
    AthleteWeekReport,
    GarminActivity,
    GarminActivitySummary,
    RaceAttendance,
    RaceEntry,
    YearPlannerWhereabout,
)


def _actor_source(actor, fallback="MiLa"):
    if not actor:
        return fallback
    return "Coach" if actor.is_staff or actor.is_superuser else "Athlete"


def _record(*, athlete, category, title, detail="", actor=None, source="MiLa", metadata=None):
    if not athlete:
        return
    AthleteActivityEvent.objects.create(
        athlete=athlete,
        category=category,
        title=title,
        detail=detail,
        actor=actor,
        source=source,
        metadata=metadata or {},
    )


@receiver(post_save, sender=AthleteDayCheck, dispatch_uid="activity_event_day_check")
def record_day_check(sender, instance, created, **kwargs):
    if kwargs.get("raw"):
        return
    parts = []
    if instance.effective_status:
        parts.append(dict(instance.STATUS_CHOICES).get(instance.effective_status, instance.effective_status))
    if instance.rpe is not None:
        parts.append(f"RPE {instance.rpe}")
    if instance.pain:
        parts.append(dict(instance.PAIN_CHOICES).get(instance.pain, instance.pain))
    if (instance.comment or "").strip():
        parts.append(instance.comment.strip())
    slot_label = "AM" if instance.slot_index == 1 else "PM"
    _record(
        athlete=instance.athlete,
        category=AthleteActivityEvent.CATEGORY_EVALUATION,
        title=f"Training evaluation {'created' if created else 'updated'}",
        detail=" · ".join(parts) or "Evaluation saved without additional details.",
        actor=instance.updated_by,
        source=_actor_source(instance.updated_by),
        metadata={"date": instance.date.isoformat(), "slot": slot_label},
    )


@receiver(post_save, sender=AthleteDailyVital, dispatch_uid="activity_event_daily_vital")
def record_daily_vital(sender, instance, created, **kwargs):
    if kwargs.get("raw"):
        return
    values = []
    for label, field, suffix in (
        ("Sleep", "sleep_hours", " h"),
        ("Sleep quality", "sleep_quality", ""),
        ("Morning HR", "morning_hr", " bpm"),
        ("HRV", "hrv", " ms"),
    ):
        value = getattr(instance, field)
        if value is not None:
            values.append(f"{label}: {value}{suffix}")
    _record(
        athlete=instance.athlete,
        category=AthleteActivityEvent.CATEGORY_VITALS,
        title=f"Daily vitals {'created' if created else 'updated'}",
        detail=" · ".join(values) or "Daily vitals saved without values.",
        actor=instance.updated_by,
        source=_actor_source(instance.updated_by, "Import"),
        metadata={"date": instance.date.isoformat()},
    )


@receiver(post_save, sender=AthleteWeekReport, dispatch_uid="activity_event_week_report")
def record_week_report(sender, instance, created, **kwargs):
    if kwargs.get("raw"):
        return
    filled = [
        label for label, field in (
            ("Athlete comment", "comm_athlete"),
            ("Coach comment", "comm_trainer"),
            ("Match report", "match_report"),
            ("Injuries", "injuries"),
        ) if (getattr(instance, field) or "").strip()
    ]
    _record(
        athlete=instance.athlete,
        category=AthleteActivityEvent.CATEGORY_WEEK_REPORT,
        title=f"Week report {'created' if created else 'updated'}",
        detail=", ".join(filled) or "Week report saved without text.",
        actor=instance.updated_by,
        source=_actor_source(instance.updated_by),
        metadata={"week_start": instance.week_start.isoformat()},
    )


@receiver(post_save, sender=AthleteDayComment, dispatch_uid="activity_event_day_comment")
def record_day_comment(sender, instance, created, **kwargs):
    if kwargs.get("raw"):
        return
    _record(
        athlete=instance.athlete,
        category=AthleteActivityEvent.CATEGORY_COMMENT,
        title=f"Day comment {'created' if created else 'updated'}",
        detail=(instance.text or "").strip(),
        actor=instance.created_by,
        source=_actor_source(instance.created_by),
        metadata={"date": instance.date.isoformat()},
    )


@receiver(post_save, sender=GarminActivity, dispatch_uid="activity_event_garmin_upload")
def record_garmin_upload(sender, instance, created, **kwargs):
    if kwargs.get("raw") or not created:
        return
    _record(
        athlete=instance.athlete,
        category=AthleteActivityEvent.CATEGORY_WATCH,
        title="Garmin activity uploaded",
        detail=instance.original_filename,
        source="Garmin",
        metadata={"activity_start": instance.activity_start.isoformat() if instance.activity_start else ""},
    )


@receiver(post_save, sender=GarminActivitySummary, dispatch_uid="activity_event_garmin_summary")
def record_garmin_summary(sender, instance, created, **kwargs):
    if kwargs.get("raw"):
        return
    details = []
    if instance.distance_m is not None:
        details.append(f"{instance.distance_m / 1000:.1f} km")
    if instance.duration_s is not None:
        details.append(f"{round(instance.duration_s / 60)} min")
    _record(
        athlete=instance.athlete,
        category=AthleteActivityEvent.CATEGORY_WATCH,
        title=f"Garmin activity {'received' if created else 'updated'}",
        detail=" · ".join(details),
        source="Garmin",
        metadata={"activity_date": sender._meta.get_field("activity_date").to_python(instance.activity_date).isoformat(),
                  "activity_id": instance.activity_id},
    )


@receiver(post_save, sender=RaceEntry, dispatch_uid="activity_event_race_entry")
def record_race_entry(sender, instance, created, **kwargs):
    if kwargs.get("raw"):
        return
    _record(
        athlete=instance.athlete,
        category=AthleteActivityEvent.CATEGORY_RACE,
        title=f"Race selection {'created' if created else 'updated'}",
        detail=str(instance.race_distance),
        source="Race Calendar",
    )


@receiver(post_save, sender=RaceAttendance, dispatch_uid="activity_event_race_attendance")
def record_race_attendance(sender, instance, created, **kwargs):
    if not kwargs.get("raw") and created:
        _record(
            athlete=instance.athlete,
            category=AthleteActivityEvent.CATEGORY_RACE,
            title="Race attendance added",
            detail=str(instance.race),
            source="Race Calendar",
        )


@receiver(post_save, sender=YearPlannerWhereabout, dispatch_uid="activity_event_whereabout")
def record_whereabout(sender, instance, created, **kwargs):
    if kwargs.get("raw") or not instance.athlete_id:
        return
    _record(
        athlete=instance.athlete,
        category=AthleteActivityEvent.CATEGORY_WHEREABOUTS,
        title=f"Whereabouts {'created' if created else 'updated'}",
        detail=f"{instance.get_whereabouts_type_display()}: {instance.start_date:%d-%m-%Y} – {instance.end_date:%d-%m-%Y}"
               + (f" · {instance.note}" if instance.note else ""),
        source="Year Planner",
    )
