from django.db import migrations, models


def copy_shared_notes(apps, schema_editor):
    FocusPointComment = apps.get_model("core", "FocusPointComment")
    AthleteFocusPoint = apps.get_model("core", "AthleteFocusPoint")
    alias = schema_editor.connection.alias

    legacy_rows = FocusPointComment.objects.using(alias).filter(
        point_key__endswith="__plan"
    ) | FocusPointComment.objects.using(alias).filter(point_key__endswith="__progress")
    grouped = {}
    for row in legacy_rows.order_by("athlete_id", "point_key", "coach_id", "id"):
        column = "plan_text" if row.point_key.endswith("__plan") else "progress_text"
        base_key = row.point_key.rsplit("__", 1)[0]
        if row.comment.strip():
            grouped.setdefault((row.athlete_id, base_key, column), []).append(row.comment.strip())

    for (athlete_id, point_key, column), notes in grouped.items():
        setting, _ = AthleteFocusPoint.objects.using(alias).get_or_create(
            athlete_id=athlete_id,
            point_key=point_key,
        )
        existing = getattr(setting, column, "").strip()
        combined = list(dict.fromkeys(([existing] if existing else []) + notes))
        setattr(setting, column, "\n".join(combined))
        setting.save(update_fields=[column], using=alias)


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0114_athlete_show_plan_to_athlete"),
    ]

    operations = [
        migrations.AddField(
            model_name="athletefocuspoint",
            name="plan_text",
            field=models.TextField(blank=True, default=""),
        ),
        migrations.AddField(
            model_name="athletefocuspoint",
            name="progress_text",
            field=models.TextField(blank=True, default=""),
        ),
        migrations.RunPython(copy_shared_notes, migrations.RunPython.noop),
    ]
