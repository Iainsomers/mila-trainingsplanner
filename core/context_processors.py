from django.contrib.staticfiles.storage import staticfiles_storage
from django.utils.text import slugify

from core.models import Athlete, CoachAccess, CoachSettings


def _identity_value(value):
    return "".join(character.lower() for character in (value or "") if character.isalnum())


def _athlete_for_user(user):
    if not user or not user.is_authenticated:
        return None

    candidates = [
        getattr(user, "username", ""),
        getattr(user, "email", ""),
        getattr(user, "first_name", ""),
        getattr(user, "last_name", ""),
        f"{getattr(user, 'first_name', '')} {getattr(user, 'last_name', '')}",
    ]
    normalized = {_identity_value(value) for value in candidates if value}
    for athlete in Athlete.objects.select_related("owner", "team").all():
        if _identity_value(athlete.name) in normalized:
            return athlete
    return None


def _active_coach_id(request):
    user = request.user
    if not (user.is_staff or user.is_superuser):
        return user.id

    allowed_ids = {user.id}
    allowed_ids.update(CoachAccess.objects.filter(grantee=user).values_list("owner_id", flat=True))
    raw_id = request.session.get("active_coach_owner_id")
    try:
        raw_id = int(raw_id)
    except (TypeError, ValueError):
        raw_id = user.id
    return raw_id if raw_id in allowed_ids else user.id


def team_branding(request):
    if not getattr(request.user, "is_authenticated", False):
        return {}

    athlete = _athlete_for_user(request.user)
    team = athlete.team if athlete else None
    if team is None:
        settings = (
            CoachSettings.objects
            .filter(user_id=athlete.owner_id if athlete else _active_coach_id(request))
            .select_related("team")
            .first()
        )
        team = settings.team if settings else None

    if team is None:
        return {"team_branding": None}

    logo_path = f"core/brand/team-{slugify(team.name)}.jpg"
    return {
        "team_branding": {
            "name": team.name,
            "logo_url": staticfiles_storage.url(logo_path) if staticfiles_storage.exists(logo_path) else "",
        }
    }
