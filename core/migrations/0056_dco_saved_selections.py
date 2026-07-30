from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0055_athletebaseplanningblock_planning_kind"),
    ]

    operations = [
        migrations.AddField(
            model_name="coachsettings",
            name="dco_saved_selections",
            field=models.JSONField(blank=True, default=list),
        ),
        migrations.AddField(
            model_name="coachsettings",
            name="dco_standard_selection_id",
            field=models.CharField(blank=True, default="", max_length=40),
        ),
    ]
