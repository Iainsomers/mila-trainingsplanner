from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0149_alter_yearplannerentry_whereabouts_type_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="athlete",
            name="alternative_hr_correction",
            field=models.PositiveIntegerField(default=10),
        ),
    ]
