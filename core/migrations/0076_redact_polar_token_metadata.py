from django.db import migrations


SECRET_KEYS = {"access_token", "refresh_token", "client_secret", "id_token"}


def redact_token_payloads(apps, schema_editor):
    PolarConnection = apps.get_model("core", "PolarConnection")
    for connection in PolarConnection.objects.all().iterator():
        changed = False
        for field_name in ("raw_token_response", "raw_v4_token_response"):
            value = getattr(connection, field_name, None)
            if not isinstance(value, dict):
                continue
            safe_value = {
                str(key): item
                for key, item in value.items()
                if str(key).lower() not in SECRET_KEYS
            }
            if safe_value != value:
                setattr(connection, field_name, safe_value)
                changed = True
        if changed:
            connection.save(update_fields=["raw_token_response", "raw_v4_token_response"])


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0075_athlete_zone_hr_bpm"),
    ]

    operations = [
        migrations.RunPython(redact_token_payloads, migrations.RunPython.noop),
    ]
