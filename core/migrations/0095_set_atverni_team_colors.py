from django.db import migrations


def set_atverni_team_colors(apps, schema_editor):
    Team = apps.get_model("core", "Team")
    Team.objects.filter(name__iexact="Atverni").update(
        color_1="#3973DE",
        color_2="#3973DE",
    )


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0094_team_color_1_team_color_2"),
    ]

    operations = [
        migrations.RunPython(set_atverni_team_colors, migrations.RunPython.noop),
    ]
