# Generated for MiLa Trainingsplanner

from django.db import migrations


def copy_day_comments_to_am_report(apps, schema_editor):
    AthleteDayComment = apps.get_model("core", "AthleteDayComment")
    AthleteDayCheck = apps.get_model("core", "AthleteDayCheck")

    for day_comment in AthleteDayComment.objects.exclude(text__isnull=True).exclude(text__exact=""):
        check, created = AthleteDayCheck.objects.get_or_create(
            athlete=day_comment.athlete,
            day=day_comment.day,
            slot_index=1,
        )

        if not (check.comment or "").strip():
            check.comment = day_comment.text
            check.save(update_fields=["comment"])


def reverse_copy_day_comments_to_am_report(apps, schema_editor):
    # Intentionally left empty: do not delete athlete report comments on rollback.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0033_athlete_day_check_report_fields"),
    ]

    operations = [
        migrations.RunPython(
            copy_day_comments_to_am_report,
            reverse_copy_day_comments_to_am_report,
        ),
    ]
