from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0053_standard_strength"),
    ]

    operations = [
        migrations.AddField(
            model_name="athletedaycheck",
            name="watch_activity_id",
            field=models.CharField(blank=True, default="", max_length=120),
        ),
        migrations.AddField(
            model_name="athletedaycheck",
            name="watch_activity_summary",
            field=models.TextField(blank=True, default=""),
        ),
        migrations.AddField(
            model_name="athletedaycheck",
            name="watch_activity_payload",
            field=models.JSONField(blank=True, default=dict),
        ),
    ]
