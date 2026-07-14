from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0047_athlete_base_planning"),
    ]

    operations = [
        migrations.AddField(
            model_name="trainingplan",
            name="auto_wucd_enabled",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="trainingplan",
            name="auto_wu_m",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="trainingplan",
            name="auto_cd_m",
            field=models.PositiveIntegerField(default=0),
        ),
    ]
