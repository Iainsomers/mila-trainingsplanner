# Generated for MiLa Trainingsplanner

from django.db import migrations


def copy_day_comments_to_am_report(apps, schema_editor):
    AthleteDayComment = apps.get_model("core", "AthleteDayComment")
    AthleteDayCheck = apps.get_model("core", "AthleteDayCheck")

    for day_comment in AthleteDayComment.objects.exclude(text__isnull=True).exclude(text__exact=""):
        check, created = AthleteDayCheck.objects.get_or_create(
            athlete=day_comment.athlete,
            date=day_comment.date,
            slot_index=1,
            defaults={
                "updated_by": day_comment.created_by,
            },
        )

        if not (check.comment or "").strip():
            check.comment = day_comment.text
            if not check.updated_by_id:
                check.updated_by = day_comment.created_by
            check.save(update_fields=["comment", "updated_by"])


def reverse_copy_day_comments_to_am_report(apps, schema_editor):
    # Intentionally left empty: do not delete athlete report comments on rollback.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0033_athletedaycheck_comment_athletedaycheck_rpe"),
    ]

    operations = [
        migrations.RunPython(
            copy_day_comments_to_am_report,
            reverse_copy_day_comments_to_am_report,
        ),
    ]
