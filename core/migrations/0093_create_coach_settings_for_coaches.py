from django.db import migrations


def create_settings_for_coaches(apps, schema_editor):
    Team = apps.get_model("core", "Team")
    User = apps.get_model("auth", "User")
    Athlete = apps.get_model("core", "Athlete")
    TrainingPlan = apps.get_model("core", "TrainingPlan")
    CoachAccess = apps.get_model("core", "CoachAccess")
    CoachSettings = apps.get_model("core", "CoachSettings")

    for name in ("Atverni", "LLG", "Pace"):
        Team.objects.get_or_create(name=name)

    coach_ids = set(User.objects.filter(is_staff=True).values_list("id", flat=True))
    coach_ids.update(Athlete.objects.exclude(owner_id=None).values_list("owner_id", flat=True))
    coach_ids.update(TrainingPlan.objects.exclude(owner_id=None).values_list("owner_id", flat=True))
    coach_ids.update(CoachAccess.objects.values_list("owner_id", flat=True))
    coach_ids.update(CoachAccess.objects.values_list("grantee_id", flat=True))

    for user_id in filter(None, coach_ids):
        CoachSettings.objects.get_or_create(user_id=user_id)


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0092_team_athlete_team_coachsettings_team"),
    ]

    operations = [
        migrations.RunPython(create_settings_for_coaches, migrations.RunPython.noop),
    ]
