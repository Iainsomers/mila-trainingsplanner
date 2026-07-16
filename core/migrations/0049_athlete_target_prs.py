from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0048_trainingplan_auto_wucd_settings"),
    ]

    operations = [
        migrations.AddField(
            model_name="athlete",
            name="target_pr_800_s",
            field=models.FloatField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="athlete",
            name="target_pr_1500_s",
            field=models.FloatField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="athlete",
            name="target_pr_3000_s",
            field=models.FloatField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="athlete",
            name="target_pr_5000_s",
            field=models.FloatField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="athlete",
            name="target_pr_10000_s",
            field=models.FloatField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="athlete",
            name="target_pr_tm_s",
            field=models.FloatField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="athlete",
            name="target_pr_thm_s",
            field=models.FloatField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="athlete",
            name="target_pr_400_s",
            field=models.FloatField(blank=True, null=True),
        ),
    ]
