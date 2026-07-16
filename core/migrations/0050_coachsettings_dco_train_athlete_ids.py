from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0049_athlete_target_prs"),
    ]

    operations = [
        migrations.AddField(
            model_name="coachsettings",
            name="dco_train_athlete_ids",
            field=models.JSONField(blank=True, default=list),
        ),
    ]
