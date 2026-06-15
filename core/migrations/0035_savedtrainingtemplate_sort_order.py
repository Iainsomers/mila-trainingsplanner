from django.db import migrations, models


def fill_saved_training_sort_order(apps, schema_editor):
    SavedTrainingTemplate = apps.get_model("core", "SavedTrainingTemplate")
    owner_ids = (
        SavedTrainingTemplate.objects
        .order_by("owner_id")
        .values_list("owner_id", flat=True)
        .distinct()
    )

    for owner_id in owner_ids:
        templates = list(
            SavedTrainingTemplate.objects
            .filter(owner_id=owner_id)
            .order_by("name", "id")
        )
        for index, template in enumerate(templates, start=1):
            template.sort_order = index
            template.save(update_fields=["sort_order"])


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0034_copy_day_comments_to_am_report"),
    ]

    operations = [
        migrations.AddField(
            model_name="savedtrainingtemplate",
            name="sort_order",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.RunPython(fill_saved_training_sort_order, migrations.RunPython.noop),
        migrations.AlterModelOptions(
            name="savedtrainingtemplate",
            options={"ordering": ["sort_order", "name", "id"]},
        ),
    ]
