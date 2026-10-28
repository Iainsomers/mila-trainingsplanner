"""Resolve athlete logins separately from coach-owned plans."""

import re

from core.models import Athlete, CoachAccess

from .common import _is_coach_user


def _normalize_athlete_login_value(value):
    return re.sub(r"[^a-z0-9]", "", (value or "").strip().lower())


def _athlete_for_user(user):
    candidates = []

    username = (getattr(user, "username", "") or "").strip()
    if username:
        candidates.append(username)
        candidates.append(username.replace("_", " "))
        candidates.append(username.replace(".", " "))
        if "@" in username:
            candidates.append(username.split("@", 1)[0])

    first_name = (getattr(user, "first_name", "") or "").strip()
    last_name = (getattr(user, "last_name", "") or "").strip()
    full_name = f"{first_name} {last_name}".strip()
    if full_name:
        candidates.append(full_name)

    email = (getattr(user, "email", "") or "").strip()
    if email:
        candidates.append(email)
        candidates.append(email.split("@", 1)[0])

    for candidate in candidates:
        athlete = Athlete.objects.filter(name__iexact=candidate.strip()).first()
        if athlete:
            return athlete

    normalized_candidates = {
        _normalize_athlete_login_value(candidate)
        for candidate in candidates
        if _normalize_athlete_login_value(candidate)
    }
    if not normalized_candidates:
        return None

    for athlete in Athlete.objects.order_by("name"):
        if _normalize_athlete_login_value(athlete.name) in normalized_candidates:
            return athlete
    return None


def _is_ayc_coach_user(user):
    """A personal training plan must not turn an athlete's AYC into a coach view."""
    if not _is_coach_user(user):
        return False
    if user.is_staff or user.is_superuser:
        return True
    if (
        _athlete_for_user(user)
        and not Athlete.objects.filter(owner=user).exists()
        and not CoachAccess.objects.filter(grantee=user).exists()
    ):
        return False
    return True
