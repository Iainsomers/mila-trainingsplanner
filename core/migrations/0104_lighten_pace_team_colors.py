from django.db import migrations


def lighten_pace_team_colors(apps, schema_editor):
    Team = apps.get_model("core", "Team")
    Team.objects.filter(name__iexact="Pace").update(
        color_1="#2E7D5B",
        color_2="#8A4F7D",
    )


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0103_set_pace_team_colors"),
    ]

    operations = [
        migrations.RunPython(lighten_pace_team_colors, migrations.RunPython.noop),
    ]
