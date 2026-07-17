from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("core", "0051_alter_athlete_gender_and_base_planning_labels"),
    ]

    operations = [
        migrations.CreateModel(
            name="PolarConnection",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("member_id", models.CharField(max_length=120, unique=True)),
                ("polar_user_id", models.CharField(blank=True, default="", max_length=64)),
                ("access_token", models.TextField(blank=True, default="")),
                ("token_type", models.CharField(blank=True, default="", max_length=30)),
                ("expires_in", models.PositiveIntegerField(blank=True, null=True)),
                ("scope", models.CharField(blank=True, default="", max_length=255)),
                (
                    "status",
                    models.CharField(
                        choices=[("connected", "Connected"), ("error", "Error")],
                        default="connected",
                        max_length=30,
                    ),
                ),
                ("last_error", models.TextField(blank=True, default="")),
                ("raw_token_response", models.JSONField(blank=True, default=dict)),
                ("raw_user_response", models.JSONField(blank=True, default=dict)),
                ("connected_at", models.DateTimeField(blank=True, null=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "user",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="polar_connection",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
        ),
    ]
