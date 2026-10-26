from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0109_athlete_pause_mode"),
    ]

    operations = [
        migrations.AddField(
            model_name="athlete",
            name="garmin_fit_upload_enabled",
            field=models.BooleanField(default=False),
        ),
    ]
