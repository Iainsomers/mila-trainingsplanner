from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("core", "0036_race_calendar_phase1"),
    ]

    operations = [
        migrations.CreateModel(
            name="RaceEntry",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("coach_selected", models.BooleanField(default=False)),
                ("target_selected", models.BooleanField(default=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("athlete", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="race_entries", to="core.athlete")),
                ("race_distance", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="entries", to="core.raceeventdistance")),
            ],
            options={
                "ordering": ["race_distance__race__date", "race_distance__id", "athlete__name"],
            },
        ),
        migrations.AddConstraint(
            model_name="raceentry",
            constraint=models.UniqueConstraint(fields=("race_distance", "athlete"), name="unique_race_entry_per_distance_athlete"),
        ),
    ]
