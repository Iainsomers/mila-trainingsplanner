from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0045_group_auto_wucd_settings"),
    ]

    operations = [
        migrations.AddField(
            model_name="trainingplan",
            name="plan_kind",
            field=models.CharField(
                choices=[
                    ("legacy", "Legacy plan"),
                    ("trainer", "Trainer planning"),
                ],
                db_index=True,
                default="legacy",
                max_length=20,
            ),
        ),
    ]
