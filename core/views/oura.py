import base64
import hashlib
import secrets
from datetime import datetime, timedelta
from urllib.parse import urlencode

import requests
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden
from django.shortcuts import redirect
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from core.models import OuraConnection
from core.views.athlete_identity import _athlete_for_user, _is_ayc_coach_user


OURA_AUTHORIZE_URL = "https://cloud.ouraring.com/oauth/authorize"
OURA_TOKEN_URL = "https://api.ouraring.com/oauth/token"
OURA_SCOPES = "daily heartrate"
OAUTH_SESSION_KEY = "oura_oauth_pending"


def _oura_configured():
    return bool(
        settings.OURA_CLIENT_ID
        and settings.OURA_CLIENT_SECRET
        and settings.OURA_REDIRECT_URI
    )


def _athlete_user(request):
    if not request.user.is_authenticated or request.user.is_staff or request.user.is_superuser:
        return None
    if _is_ayc_coach_user(request.user):
        return None
    return _athlete_for_user(request.user)


@login_required
@require_POST
def oura_connect_view(request):
    athlete = _athlete_user(request)
    if athlete is None:
        return HttpResponseForbidden("Oura can only be connected from the athlete's own account.")
    if not _oura_configured():
        return redirect(f"{reverse('dashboard')}?oura=not_configured")
    if request.POST.get("consent_oura_data") != "on":
        return redirect(f"{reverse('dashboard')}?oura=consent_required")
    if request.POST.get("confirm_adult_or_guardian") != "on":
        return redirect(f"{reverse('dashboard')}?oura=guardian_required")

    state = secrets.token_urlsafe(32)
    code_verifier = secrets.token_urlsafe(64)
    code_challenge = base64.urlsafe_b64encode(
        hashlib.sha256(code_verifier.encode("ascii")).digest()
    ).decode("ascii").rstrip("=")
    request.session[OAUTH_SESSION_KEY] = {
        "state": state,
        "code_verifier": code_verifier,
        "athlete_id": athlete.id,
        "user_id": request.user.id,
        "health_data_consent_at": timezone.now().isoformat(),
    }
    params = {
        "response_type": "code",
        "client_id": settings.OURA_CLIENT_ID,
        "redirect_uri": settings.OURA_REDIRECT_URI,
        "scope": OURA_SCOPES,
        "state": state,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
    }
    return redirect(f"{OURA_AUTHORIZE_URL}?{urlencode(params)}")


@login_required
@require_GET
def oura_callback_view(request):
    pending = request.session.pop(OAUTH_SESSION_KEY, None)
    athlete = _athlete_user(request)
    if not pending or athlete is None:
        return redirect(f"{reverse('dashboard')}?oura=authorization_expired")

    returned_state = request.GET.get("state", "")
    if (
        not secrets.compare_digest(str(pending.get("state", "")), returned_state)
        or pending.get("user_id") != request.user.id
        or pending.get("athlete_id") != athlete.id
    ):
        return redirect(f"{reverse('dashboard')}?oura=authorization_failed")
    if request.GET.get("error") or not request.GET.get("code") or not _oura_configured():
        return redirect(f"{reverse('dashboard')}?oura=authorization_cancelled")

    try:
        response = requests.post(
            OURA_TOKEN_URL,
            data={
                "grant_type": "authorization_code",
                "code": request.GET["code"],
                "redirect_uri": settings.OURA_REDIRECT_URI,
                "client_id": settings.OURA_CLIENT_ID,
                "client_secret": settings.OURA_CLIENT_SECRET,
                "code_verifier": pending["code_verifier"],
            },
            timeout=20,
        )
        response.raise_for_status()
        token_payload = response.json()
    except (requests.RequestException, ValueError, KeyError):
        return redirect(f"{reverse('dashboard')}?oura=authorization_failed")

    access_token = token_payload.get("access_token")
    if not access_token:
        return redirect(f"{reverse('dashboard')}?oura=authorization_failed")

    expires_in = token_payload.get("expires_in")
    try:
        expires_at = timezone.now() + timedelta(seconds=max(0, int(expires_in))) if expires_in is not None else None
    except (TypeError, ValueError):
        expires_at = None

    OuraConnection.objects.update_or_create(
        athlete=athlete,
        defaults={
            "access_token": access_token,
            "refresh_token": token_payload.get("refresh_token", ""),
            "token_expires_at": expires_at,
            "scope": token_payload.get("scope", OURA_SCOPES),
            "health_data_consent_at": datetime.fromisoformat(pending["health_data_consent_at"]),
            "consented_by": request.user,
            "adult_or_guardian_permission_confirmed": True,
        },
    )
    return redirect(f"{reverse('dashboard')}?oura=connected")


@login_required
@require_POST
def oura_disconnect_view(request):
    athlete = _athlete_user(request)
    if athlete is None:
        return HttpResponseForbidden("Oura can only be disconnected from the athlete's own account.")
    connection = OuraConnection.objects.filter(athlete=athlete).first()
    if connection:
        try:
            requests.get(
                "https://api.ouraring.com/oauth/revoke",
                params={"access_token": connection.access_token},
                timeout=10,
            )
        except requests.RequestException:
            pass
        connection.delete()
    return redirect(f"{reverse('dashboard')}?oura=disconnected")
