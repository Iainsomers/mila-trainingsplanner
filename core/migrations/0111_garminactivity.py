from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0110_athlete_garmin_fit_upload_enabled"),
    ]

    operations = [
        migrations.CreateModel(
            name="GarminActivity",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("activity_start", models.DateTimeField(blank=True, db_index=True, null=True)),
                ("original_filename", models.CharField(max_length=255)),
                ("file_hash", models.CharField(db_index=True, max_length=64)),
                ("raw_file", models.BinaryField()),
                ("parsed_data", models.JSONField(blank=True, default=dict)),
                ("uploaded_at", models.DateTimeField(auto_now_add=True)),
                ("athlete", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="garmin_activities", to="core.athlete")),
            ],
            options={"ordering": ["-activity_start", "-uploaded_at", "-id"]},
        ),
        migrations.AddConstraint(
            model_name="garminactivity",
            constraint=models.UniqueConstraint(fields=("athlete", "file_hash"), name="unique_garmin_activity_file_per_athlete"),
        ),
    ]
