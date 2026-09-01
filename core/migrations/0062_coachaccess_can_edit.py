from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0061_assign_legacy_athletes_to_iain"),
    ]

    operations = [
        migrations.AddField(
            model_name="coachaccess",
            name="can_edit",
            field=models.BooleanField(default=False),
        ),
    ]
