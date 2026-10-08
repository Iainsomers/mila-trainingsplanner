from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0087_coachsettings_shared_whereabouts"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="athlete",
            name="year_planner_shared_whereabouts_enabled",
        ),
    ]
