from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0163_coachsettings_stats_overview_columns"),
    ]

    operations = [
        migrations.AddField(
            model_name="coachsettings",
            name="stats_overview_sort",
            field=models.CharField(blank=True, default="name", max_length=40),
        ),
    ]
