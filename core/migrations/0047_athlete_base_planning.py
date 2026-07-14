from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0046_trainingplan_plan_kind"),
    ]

    operations = [
        migrations.CreateModel(
            name="AthleteBasePlanningBlock",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("label", models.CharField(blank=True, default="", max_length=120)),
                ("start_month", models.PositiveSmallIntegerField()),
                ("start_day", models.PositiveSmallIntegerField()),
                ("end_month", models.PositiveSmallIntegerField()),
                ("end_day", models.PositiveSmallIntegerField()),
                ("sort_order", models.PositiveIntegerField(default=1)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "athlete",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="base_planning_blocks",
                        to="core.athlete",
                    ),
                ),
            ],
            options={
                "ordering": ["athlete__name", "sort_order", "start_month", "start_day", "id"],
            },
        ),
        migrations.CreateModel(
            name="AthleteBasePlanningSlot",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "weekday",
                    models.PositiveSmallIntegerField(
                        choices=[
                            (0, "Monday"),
                            (1, "Tuesday"),
                            (2, "Wednesday"),
                            (3, "Thursday"),
                            (4, "Friday"),
                            (5, "Saturday"),
                            (6, "Sunday"),
                        ]
                    ),
                ),
                ("slot_index", models.PositiveSmallIntegerField(choices=[(1, "AM"), (2, "PM")])),
                (
                    "mode",
                    models.CharField(
                        choices=[
                            ("rest", "Rust"),
                            ("training", "Training"),
                            ("trainer", "Trainer planning"),
                        ],
                        default="rest",
                        max_length=20,
                    ),
                ),
                ("training_text", models.TextField(blank=True, default="")),
                (
                    "block",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="slots",
                        to="core.athletebaseplanningblock",
                    ),
                ),
                (
                    "trainer_plan",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="base_planning_slots",
                        to="core.trainingplan",
                    ),
                ),
            ],
            options={
                "ordering": ["block__sort_order", "weekday", "slot_index"],
                "constraints": [
                    models.UniqueConstraint(
                        fields=("block", "weekday", "slot_index"),
                        name="unique_base_planning_slot_per_block_weekday_slot",
                    )
                ],
            },
        ),
    ]
