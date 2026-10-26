from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0113_athlete_see_desired_improvement_points_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="athlete",
            name="show_plan_to_athlete",
            field=models.BooleanField(default=False),
        ),
    ]
