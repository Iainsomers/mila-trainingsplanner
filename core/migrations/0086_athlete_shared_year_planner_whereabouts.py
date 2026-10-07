from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0085_athlete_can_change_base_planning"),
    ]

    operations = [
        migrations.AddField(
            model_name="athlete",
            name="year_planner_shared_whereabouts_enabled",
            field=models.BooleanField(default=False),
        ),
    ]
