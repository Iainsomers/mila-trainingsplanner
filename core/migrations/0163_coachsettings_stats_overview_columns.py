from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0162_mysasy_coach_diagnostics"),
    ]

    operations = [
        migrations.AddField(
            model_name="coachsettings",
            name="stats_overview_columns",
            field=models.JSONField(blank=True, default=list),
        ),
    ]
