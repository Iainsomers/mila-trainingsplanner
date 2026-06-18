# Generated manually for MiLa Race Select phase 3c

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0037_race_entry_phase3a"),
    ]

    operations = [
        migrations.AddField(
            model_name="raceentry",
            name="athlete_selected",
            field=models.BooleanField(default=False),
        ),
    ]
