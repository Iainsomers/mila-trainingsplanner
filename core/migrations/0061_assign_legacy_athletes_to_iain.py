from django.conf import settings
from django.db import migrations


def _find_iain_user(User):
    username_candidates = [
        "Iain",
        "iain",
        "iains",
        "iain_somers",
        "iain.somers",
        "iain somers",
    ]
    for username in username_candidates:
        user = User.objects.filter(username__iexact=username).order_by("-is_superuser", "id").first()
        if user:
            return user

    for user in User.objects.order_by("-is_superuser", "id"):
        first_name = (getattr(user, "first_name", "") or "").strip().lower()
        last_name = (getattr(user, "last_name", "") or "").strip().lower()
        full_name = f"{first_name} {last_name}".strip()
        email = (getattr(user, "email", "") or "").strip().lower()
        if full_name == "iain somers" or email.startswith("iain"):
            return user

    return None


def assign_legacy_athletes_to_iain(apps, schema_editor):
    app_label, model_name = settings.AUTH_USER_MODEL.split(".")
    User = apps.get_model(app_label, model_name)
    Athlete = apps.get_model("core", "Athlete")

    iain = _find_iain_user(User)
    if not iain:
        return

    Athlete.objects.filter(owner__isnull=True).update(owner=iain)


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("core", "0060_corosworkoutpush"),
    ]

    operations = [
        migrations.RunPython(assign_legacy_athletes_to_iain, migrations.RunPython.noop),
    ]
