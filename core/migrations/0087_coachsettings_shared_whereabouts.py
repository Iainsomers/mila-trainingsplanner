from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0086_athlete_shared_year_planner_whereabouts"),
    ]

    operations = [
        migrations.AddField(
            model_name="coachsettings",
            name="year_planner_shared_whereabouts_enabled",
            field=models.BooleanField(default=False),
        ),
    ]
