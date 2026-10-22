from django.db import migrations


def set_pace_team_colors(apps, schema_editor):
    Team = apps.get_model("core", "Team")
    Team.objects.filter(name__iexact="Pace").update(
        color_1="#0B3D2E",
        color_2="#4B2142",
    )


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0102_coachsettings_see_session_km"),
    ]

    operations = [
        migrations.RunPython(set_pace_team_colors, migrations.RunPython.noop),
    ]
