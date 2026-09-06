from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


def migrate_daily_whereabouts_to_ranges(apps, schema_editor):
    YearPlannerEntry = apps.get_model("core", "YearPlannerEntry")
    YearPlannerWhereabout = apps.get_model("core", "YearPlannerWhereabout")

    entries = (
        YearPlannerEntry.objects
        .exclude(whereabouts_type="")
        .order_by("owner_id", "athlete_id", "whereabouts_type", "note", "date")
    )
    current = None
    ranges = []
    touched_ids = []
    for entry in entries:
        key = (entry.owner_id, entry.athlete_id, entry.whereabouts_type, entry.note or "")
        touched_ids.append(entry.id)
        if current and current["key"] == key and (entry.date - current["end_date"]).days == 1:
            current["end_date"] = entry.date
            continue
        if current:
            ranges.append(current)
        current = {
            "key": key,
            "owner_id": entry.owner_id,
            "athlete_id": entry.athlete_id,
            "start_date": entry.date,
            "end_date": entry.date,
            "whereabouts_type": entry.whereabouts_type,
            "note": entry.note or "",
        }
    if current:
        ranges.append(current)

    for item in ranges:
        YearPlannerWhereabout.objects.create(
            owner_id=item["owner_id"],
            athlete_id=item["athlete_id"],
            start_date=item["start_date"],
            end_date=item["end_date"],
            whereabouts_type=item["whereabouts_type"],
            note=item["note"],
        )

    if touched_ids:
        YearPlannerEntry.objects.filter(id__in=touched_ids).update(whereabouts_type="", note="")
        YearPlannerEntry.objects.filter(
            id__in=touched_ids,
            training_type="",
            whereabouts_type="",
            note="",
        ).delete()


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("core", "0063_yearplannerentry"),
    ]

    operations = [
        migrations.CreateModel(
            name="YearPlannerWhereabout",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("start_date", models.DateField()),
                ("end_date", models.DateField()),
                ("whereabouts_type", models.CharField(choices=[("", "—"), ("camp", "Camp"), ("travel", "Travel"), ("test", "Test"), ("race", "Race"), ("medical", "Medical"), ("brinec", "Brinec")], max_length=20)),
                ("note", models.CharField(blank=True, default="", max_length=120)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("athlete", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="year_planner_whereabouts", to="core.athlete")),
                ("owner", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="year_planner_whereabouts", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "ordering": ["owner_id", "athlete__name", "start_date", "end_date"],
                "indexes": [
                    models.Index(fields=["owner", "athlete", "start_date", "end_date"], name="core_yearpl_owner_i_fca5c0_idx"),
                    models.Index(fields=["owner", "start_date", "end_date"], name="core_yearpl_owner_i_586df5_idx"),
                ],
            },
        ),
        migrations.RunPython(migrate_daily_whereabouts_to_ranges, migrations.RunPython.noop),
    ]
