from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0050_coachsettings_dco_train_athlete_ids"),
    ]

    operations = [
        migrations.AlterField(
            model_name="athlete",
            name="gender",
            field=models.CharField(
                choices=[("M", "Male"), ("V", "Female"), ("X", "Other")],
                max_length=1,
            ),
        ),
        migrations.AlterField(
            model_name="athletebaseplanningslot",
            name="mode",
            field=models.CharField(
                choices=[("rest", "Rest"), ("training", "Training"), ("trainer", "Group")],
                default="rest",
                max_length=20,
            ),
        ),
    ]
