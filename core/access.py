import os

from django.contrib.auth import get_user_model


COACH_TOOLS_ONLY_USERNAMES = {"coachtools"}
COACH_TOOLS_OWNER_FALLBACK_USERNAMES = ("Iain_somers", "Iain", "iains")


def is_coach_tools_only_user(user):
    if not getattr(user, "is_authenticated", False):
        return False
    return str(getattr(user, "username", "")).strip().lower() in COACH_TOOLS_ONLY_USERNAMES


def coach_tools_data_owner(user):
    if not is_coach_tools_only_user(user):
        return user

    User = get_user_model()
    configured_username = os.environ.get("COACH_TOOLS_OWNER_USERNAME", "").strip()
    usernames = [configured_username] if configured_username else []
    usernames.extend(COACH_TOOLS_OWNER_FALLBACK_USERNAMES)

    for username in usernames:
        if not username:
            continue
        owner = User.objects.filter(username__iexact=username).first()
        if owner:
            return owner

    owner = User.objects.filter(is_superuser=True).exclude(id=user.id).order_by("id").first()
    if owner:
        return owner

    return User.objects.filter(is_staff=True).exclude(id=user.id).order_by("id").first() or user
