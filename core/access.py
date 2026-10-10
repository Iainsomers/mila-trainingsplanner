import os

from django.contrib.auth import get_user_model

from core.models import CoachAccess, CoachEvaluationSharing, CoachSettings


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


def evaluation_visibility_for_request(request, owner, athlete_self=False):
    """Return which athlete evaluation types the current request may view."""
    hidden = {"training": False, "week": False, "vitals": False}
    if not getattr(request, "user", None) or not request.user.is_authenticated or not owner:
        return hidden
    if athlete_self or request.user.is_superuser or request.user.id == owner.id:
        return {key: True for key in hidden}
    if not CoachSettings.objects.filter(user=owner, evaluation_sharing_enabled=True).exists():
        return hidden
    if not CoachAccess.objects.filter(owner=owner, grantee=request.user).exists():
        return hidden
    share = CoachEvaluationSharing.objects.filter(owner=owner, grantee=request.user).first()
    if not share:
        return hidden
    return {
        "training": bool(share.training),
        "week": bool(share.week),
        "vitals": bool(share.vitals),
    }
