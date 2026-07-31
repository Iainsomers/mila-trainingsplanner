from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0056_dco_saved_selections"),
    ]

    operations = [
        migrations.AddField(
            model_name="polarconnection",
            name="v4_access_token",
            field=models.TextField(blank=True, default=""),
        ),
        migrations.AddField(
            model_name="polarconnection",
            name="v4_refresh_token",
            field=models.TextField(blank=True, default=""),
        ),
        migrations.AddField(
            model_name="polarconnection",
            name="v4_token_type",
            field=models.CharField(blank=True, default="", max_length=30),
        ),
        migrations.AddField(
            model_name="polarconnection",
            name="v4_expires_in",
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="polarconnection",
            name="v4_scope",
            field=models.CharField(blank=True, default="", max_length=255),
        ),
        migrations.AddField(
            model_name="polarconnection",
            name="raw_v4_token_response",
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AddField(
            model_name="polarconnection",
            name="v4_connected_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
