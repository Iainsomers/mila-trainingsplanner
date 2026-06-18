# Generated manually for Race Calendar phase 1

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("core", "0035_savedtrainingtemplate_sort_order"),
    ]

    operations = [
        migrations.CreateModel(
            name="RaceEvent",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=160)),
                ("date", models.DateField()),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("owner", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="race_events", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "ordering": ["date", "name", "id"],
            },
        ),
        migrations.CreateModel(
            name="RaceEventDistance",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("distance", models.CharField(choices=[("300", "300m"), ("400", "400m"), ("600", "600m"), ("800", "800m"), ("1000", "1000m"), ("1500", "1500m"), ("1609", "1609m"), ("3000", "3000m"), ("5000", "5000m"), ("10000", "10000m"), ("custom", "x meter")], max_length=20)),
                ("custom_distance_m", models.PositiveIntegerField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("race", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="distances", to="core.raceevent")),
            ],
            options={
                "ordering": ["race__date", "id"],
            },
        ),
        migrations.AddConstraint(
            model_name="raceeventdistance",
            constraint=models.UniqueConstraint(fields=("race", "distance", "custom_distance_m"), name="unique_race_event_distance"),
        ),
    ]
