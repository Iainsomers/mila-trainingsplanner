from django.db import migrations, models


def copy_session_km_visibility(apps, schema_editor):
    Athlete = apps.get_model("core", "Athlete")
    Athlete.objects.update(see_session_zones=models.F("see_session_km"))


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0111_garminactivity"),
    ]

    operations = [
        migrations.AddField(
            model_name="athlete",
            name="see_session_zones",
            field=models.BooleanField(default=True),
        ),
        migrations.RunPython(copy_session_km_visibility, migrations.RunPython.noop),
    ]
