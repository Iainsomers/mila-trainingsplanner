"""Athlete-owned Garmin OAuth and explicit AI consent."""
import base64
import hashlib
import secrets
from datetime import timedelta
from urllib.parse import urlencode

import requests
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from core.models import Athlete, GarminConnection
from core.views.oura import _athlete_user

CONSENT_VERSION = "garmin-ai-2026-10-31"
SESSION_KEY = "garmin_oauth_pending"
TOKEN_URL = "https://diauth.garmin.com/di-oauth2-service/oauth/token"
REGISTRATION_URL = "https://apis.garmin.com/wellness-api/rest/user/registration"


def configured():
    return bool(settings.GARMIN_CLIENT_ID and settings.GARMIN_CLIENT_SECRET and settings.GARMIN_REDIRECT_URI)


def ai_allowed(athlete):
    # Query current permissions: a stale athlete instance must not restore consent.
    return bool(athlete and Athlete.objects.filter(
        pk=athlete.pk, garmin_connection_enabled=True,
        garmin_ai_consent_at__isnull=False, garmin_ai_withdrawn_at__isnull=True,
        garmin_ai_consent_version=CONSENT_VERSION,
    ).exists())


def revoke_connection(athlete):
    """Block locally first, then best-effort unregister with Garmin."""
    connection = GarminConnection.objects.filter(athlete=athlete).first()
    Athlete.objects.filter(pk=athlete.pk).update(garmin_ai_withdrawn_at=timezone.now())
    GarminConnection.objects.filter(athlete=athlete).delete()
    if not connection:
        return True
    try:
        token = connection.access_token
        if connection.token_expires_at and connection.token_expires_at <= timezone.now():
            refreshed = requests.post(TOKEN_URL, data={
                "grant_type": "refresh_token", "refresh_token": connection.refresh_token,
                "client_id": settings.GARMIN_CLIENT_ID, "client_secret": settings.GARMIN_CLIENT_SECRET,
            }, timeout=10)
            refreshed.raise_for_status()
            token = refreshed.json()["access_token"]
        response = requests.delete(REGISTRATION_URL, headers={"Authorization": f"Bearer {token}"}, timeout=10)
        return response.status_code in (200, 204, 404)
    except (requests.RequestException, ValueError, KeyError, TypeError):
        return False


def _dashboard(status):
    return redirect(f"{reverse('dashboard')}?garmin={status}")


@login_required
@require_POST
def garmin_connect_view(request):
    athlete = _athlete_user(request)
    if not athlete or not athlete.garmin_connection_enabled:
        return HttpResponseForbidden()
    if request.POST.get("consent_garmin_data") != "on":
        return _dashboard("consent_required")
    if not configured():
        return _dashboard("not_configured")
    verifier = secrets.token_urlsafe(64)
    state = secrets.token_urlsafe(32)
    request.session[SESSION_KEY] = {
        "athlete_id": athlete.pk, "user_id": request.user.pk,
        "state": state, "verifier": verifier, "created": timezone.now().timestamp(),
        "withdrawn": athlete.garmin_ai_withdrawn_at.isoformat() if athlete.garmin_ai_withdrawn_at else None,
        "ai": request.POST.get("consent_garmin_ai") == "on",
    }
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    return redirect("https://connect.garmin.com/oauth2Confirm?" + urlencode({
        "response_type": "code", "client_id": settings.GARMIN_CLIENT_ID,
        "redirect_uri": settings.GARMIN_REDIRECT_URI, "state": state,
        "code_challenge": challenge, "code_challenge_method": "S256",
    }))


@login_required
@require_GET
def garmin_callback_view(request):
    athlete = _athlete_user(request)
    pending = request.session.pop(SESSION_KEY, None)
    if not athlete or not athlete.garmin_connection_enabled:
        return HttpResponseForbidden()
    if (not pending or pending.get("athlete_id") != athlete.pk
            or pending.get("user_id") != request.user.pk
            or not secrets.compare_digest(str(pending.get("state", "")), request.GET.get("state", ""))
            or timezone.now().timestamp() - pending.get("created", 0) > 600):
        return _dashboard("authorization_failed")
    if request.GET.get("error") or not request.GET.get("code") or not configured():
        return _dashboard("authorization_failed")
    # A withdrawal or coach disable during OAuth invalidates this attempt.
    withdrawn = athlete.garmin_ai_withdrawn_at.isoformat() if athlete.garmin_ai_withdrawn_at else None
    if pending.get("withdrawn") != withdrawn:
        return _dashboard("authorization_failed")
    try:
        response = requests.post(TOKEN_URL, data={
            "grant_type": "authorization_code", "client_id": settings.GARMIN_CLIENT_ID,
            "client_secret": settings.GARMIN_CLIENT_SECRET, "code": request.GET["code"],
            "code_verifier": pending["verifier"], "redirect_uri": settings.GARMIN_REDIRECT_URI,
        }, timeout=20)
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict) or not isinstance(payload.get("access_token"), str) or not payload["access_token"]:
            raise ValueError("Missing access token")
        expires = timezone.now() + timedelta(seconds=max(0, int(payload.get("expires_in", 0))))
    except (requests.RequestException, ValueError, KeyError, TypeError, OverflowError):
        return _dashboard("authorization_failed")
    with transaction.atomic():
        current = Athlete.objects.select_for_update().get(pk=athlete.pk)
        withdrawn = current.garmin_ai_withdrawn_at.isoformat() if current.garmin_ai_withdrawn_at else None
        if not current.garmin_connection_enabled or withdrawn != pending.get("withdrawn"):
            return _dashboard("authorization_failed")
        now = timezone.now()
        GarminConnection.objects.update_or_create(athlete=current, defaults={
            "access_token": payload["access_token"], "refresh_token": payload.get("refresh_token") or "",
            "token_expires_at": expires, "data_consent_at": now,
        })
        current.garmin_ai_consent_at = now if pending["ai"] else None
        current.garmin_ai_consent_version = CONSENT_VERSION if pending["ai"] else ""
        current.garmin_ai_withdrawn_at = None if pending["ai"] else now
        current.save(update_fields=["garmin_ai_consent_at", "garmin_ai_consent_version", "garmin_ai_withdrawn_at"])
    return _dashboard("connected")


@login_required
@require_POST
def garmin_withdraw_view(request):
    athlete = _athlete_user(request)
    if not athlete or not athlete.garmin_connection_enabled:
        return HttpResponseForbidden()
    request.session.pop(SESSION_KEY, None)
    remote_ok = revoke_connection(athlete)
    return _dashboard("disconnected" if remote_ok else "disconnected_remote_pending")


@login_required
@require_GET
def garmin_connections_view(request):
    from core.access import is_coach_tools_only_user
    from core.views.common import _is_coach_user, _filter_owned
    if _athlete_user(request) or not _is_coach_user(request.user) or is_coach_tools_only_user(request.user):
        return HttpResponseForbidden()
    athletes = _filter_owned(Athlete.objects.filter(
        garmin_connection_enabled=True, garmin_connection__isnull=False,
    ), request).only("id", "name").order_by("name", "id")
    return render(request, "core/garmin_connections.html", {"connected_athletes": athletes})


@login_required
@require_GET
def garmin_athlete_activities_view(request, athlete_id):
    from core.access import is_coach_tools_only_user
    from core.models import GarminActivity
    from core.views.common import _is_coach_user, _filter_owned
    if _athlete_user(request) or not _is_coach_user(request.user) or is_coach_tools_only_user(request.user):
        return HttpResponseForbidden()
    athlete = get_object_or_404(_filter_owned(Athlete.objects.filter(
        garmin_connection_enabled=True, garmin_connection__isnull=False,
    ), request), pk=athlete_id)
    activities = GarminActivity.objects.filter(athlete=athlete).defer("raw_file")
    return render(request, "core/garmin_athlete_activities.html", {
        "athlete": athlete, "activities": activities,
    })
