"""Athlete-owned Garmin OAuth and explicit AI consent."""
import base64
import hashlib
import secrets
import json
import math
import hmac
from datetime import datetime, timedelta, timezone as datetime_timezone
from urllib.parse import urlencode

import requests
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.db import transaction, IntegrityError
from django.http import HttpResponseForbidden, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST
from django.views.decorators.csrf import csrf_exempt

from core.models import Athlete, GarminConnection, GarminActivitySummary
from core.views.oura import _athlete_user

CONSENT_VERSION = "garmin-ai-2026-10-31"
SESSION_KEY = "garmin_oauth_pending"
TOKEN_URL = "https://diauth.garmin.com/di-oauth2-service/oauth/token"
REGISTRATION_URL = "https://apis.garmin.com/wellness-api/rest/user/registration"


def configured():
    return bool(settings.GARMIN_CLIENT_ID and settings.GARMIN_CLIENT_SECRET and settings.GARMIN_REDIRECT_URI)


def receiver_key():
    """Separate, unguessable receiver credential, derived from existing secrets."""
    if not configured():
        return ""
    return hmac.new(settings.GARMIN_CLIENT_SECRET.encode(),
                    ("mila-garmin-push-v1:" + settings.SECRET_KEY).encode(), hashlib.sha256).hexdigest()


def ensure_user_id(connection):
    """Resolve legacy connections through Garmin itself, never from claimed names."""
    if connection.garmin_user_id:
        return connection.garmin_user_id
    token = connection.access_token
    if connection.token_expires_at and connection.token_expires_at <= timezone.now() + timedelta(seconds=60):
        response = requests.post(TOKEN_URL, data={
            "grant_type": "refresh_token", "refresh_token": connection.refresh_token,
            "client_id": settings.GARMIN_CLIENT_ID, "client_secret": settings.GARMIN_CLIENT_SECRET,
        }, timeout=8)
        response.raise_for_status()
        payload = response.json()
        token = payload["access_token"]
        if not isinstance(token, str) or not token:
            raise ValueError("Missing access token")
        updated = GarminConnection.objects.filter(pk=connection.pk, access_token=connection.access_token,
                                                  athlete__garmin_connection_enabled=True).update(
            access_token=token, refresh_token=payload.get("refresh_token") or connection.refresh_token,
            token_expires_at=timezone.now() + timedelta(seconds=int(payload["expires_in"])),
        )
        if not updated:
            raise ValueError("Connection changed")
    response = requests.get("https://apis.garmin.com/wellness-api/rest/user/id",
                            headers={"Authorization": f"Bearer {token}"}, timeout=8, allow_redirects=False)
    response.raise_for_status()
    payload = response.json()
    user_id = payload.get("userId") if isinstance(payload, dict) else None
    if not isinstance(user_id, str) or not user_id or len(user_id) > 128:
        raise ValueError("Missing Garmin user identity")
    updated = GarminConnection.objects.filter(pk=connection.pk, access_token=token, athlete__garmin_connection_enabled=True).update(garmin_user_id=user_id)
    if not updated:
        raise ValueError("Connection no longer active")
    return user_id


def _push_activity(item):
    """Validate and minimise data before any record is written."""
    if not isinstance(item, dict):
        raise ValueError()
    user_id = item.get("userId")
    activity_id = item.get("activityId") or item.get("summaryId")
    if not isinstance(user_id, str) or not user_id or len(user_id) > 128:
        raise ValueError()
    if isinstance(activity_id, bool) or not isinstance(activity_id, (str, int)) or not str(activity_id) or len(str(activity_id)) > 128:
        raise ValueError()
    start_value = item["startTimeInSeconds"]
    offset_value = item.get("startTimeOffsetInSeconds", 0)
    if isinstance(start_value, bool) or isinstance(offset_value, bool):
        raise ValueError()
    start = datetime.fromtimestamp(float(start_value), tz=datetime_timezone.utc)
    offset = int(offset_value)
    if abs(offset) > 86400:
        raise ValueError()
    distance = item.get("distanceInMeters")
    if distance is not None:
        if isinstance(distance, bool):
            raise ValueError()
        distance = float(distance)
        if not math.isfinite(distance) or distance < 0:
            raise ValueError()
    return user_id, str(activity_id), {"activity_start": start,
        "activity_date": (start + timedelta(seconds=offset)).date(), "distance_m": distance}


@csrf_exempt
@require_POST
def garmin_activity_push_view(request, key):
    """Accept only authenticated Activity Summary PUSH, not arbitrary callback URLs."""
    from django.core.exceptions import RequestDataTooBig
    expected = receiver_key()
    if not expected or not secrets.compare_digest(key.encode(), expected.encode()):
        return HttpResponseForbidden()
    try:
        body = request.body
        if len(body) > 1_000_000:
            return JsonResponse({"error": "Payload too large"}, status=413)
        payload = json.loads(body)
        if not isinstance(payload, dict) or set(payload) != {"activities"}:
            raise ValueError()
        if not isinstance(payload["activities"], list) or len(payload["activities"]) > 500:
            raise ValueError()
        items = [_push_activity(item) for item in payload["activities"]]
    except RequestDataTooBig:
        return JsonResponse({"error": "Payload too large"}, status=413)
    except (ValueError, TypeError, KeyError, OverflowError, OSError):
        return JsonResponse({"error": "Invalid activity push"}, status=400)

    known_ids = set(GarminConnection.objects.filter(athlete__garmin_connection_enabled=True)
                    .exclude(garmin_user_id=None).values_list("garmin_user_id", flat=True))
    if any(user_id not in known_ids for user_id, _, _ in items):
        # Upgrade one pre-existing OAuth connection per request; Garmin retries
        # a temporary 503 until all relevant identities are mapped. No guessed matches.
        pending = GarminConnection.objects.filter(garmin_user_id=None,
                    athlete__garmin_connection_enabled=True).order_by("pk").first()
        if pending:
            try:
                ensure_user_id(pending)
            except (requests.RequestException, ValueError, TypeError, KeyError, OverflowError, IntegrityError):
                return JsonResponse({"error": "Identity temporarily unavailable"}, status=503)
            if GarminConnection.objects.filter(garmin_user_id=None, athlete__garmin_connection_enabled=True).exists():
                return JsonResponse({"error": "Preparing existing connections"}, status=503)

    with transaction.atomic():
        for user_id, activity_id, fields in items:
            # Serialize with disconnect/coach saves on the athlete row.
            athlete = Athlete.objects.select_for_update().filter(
                garmin_connection_enabled=True, garmin_connection__garmin_user_id=user_id,
            ).first()
            if athlete is None:
                continue  # Revoked/unknown users must not acquire new data.
            GarminActivitySummary.objects.update_or_create(athlete=athlete,
                activity_id=activity_id, defaults=fields)
    return JsonResponse({"ok": True})


def ai_allowed(athlete):
    # Query current permissions: a stale athlete instance must not restore consent.
    return bool(athlete and Athlete.objects.filter(
        pk=athlete.pk, garmin_connection_enabled=True,
        garmin_ai_consent_at__isnull=False, garmin_ai_withdrawn_at__isnull=True,
        garmin_ai_consent_version=CONSENT_VERSION,
    ).exists())


def revoke_connection(athlete):
    """Block locally first, then best-effort unregister with Garmin."""
    with transaction.atomic():
        Athlete.objects.select_for_update().get(pk=athlete.pk)
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
            "garmin_user_id": None,
            "access_token": payload["access_token"], "refresh_token": payload.get("refresh_token") or "",
            "token_expires_at": expires, "data_consent_at": now,
        })
        current.garmin_ai_consent_at = now if pending["ai"] else None
        current.garmin_ai_consent_version = CONSENT_VERSION if pending["ai"] else ""
        current.garmin_ai_withdrawn_at = None if pending["ai"] else now
        current.save(update_fields=["garmin_ai_consent_at", "garmin_ai_consent_version", "garmin_ai_withdrawn_at"])
    try:
        ensure_user_id(GarminConnection.objects.get(athlete=athlete))
    except (requests.RequestException, ValueError, KeyError, TypeError, OverflowError, GarminConnection.DoesNotExist, IntegrityError):
        pass  # Connection survives; receiver retries identity resolution.
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
    from core.views.coach import _is_product_admin
    receiver_url = None
    if (request.user.is_superuser or _is_product_admin(request.user)) and configured():
        receiver_url = request.build_absolute_uri(reverse("garmin_activity_push", args=[receiver_key()]))
    response = render(request, "core/garmin_connections.html", {"connected_athletes": athletes, "receiver_url": receiver_url})
    response["Cache-Control"] = "private, no-store"
    return response


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
    activities = []
    for activity in GarminActivity.objects.filter(athlete=athlete).only("activity_start", "parsed_data"):
        activities.append({"activity_start": activity.activity_start,
                           "date": timezone.localtime(activity.activity_start).date() if activity.activity_start else None,
                           "distance": (activity.parsed_data.get("human") or {}).get("distance") or "—"})
    for activity in GarminActivitySummary.objects.filter(athlete=athlete):
        activities.append({"activity_start": activity.activity_start, "date": activity.activity_date,
                           "distance": f"{activity.distance_m / 1000:.2f} km" if activity.distance_m is not None else "—"})
    activities.sort(key=lambda row: row["activity_start"].timestamp() if row["activity_start"] else float("-inf"), reverse=True)
    return render(request, "core/garmin_athlete_activities.html", {
        "athlete": athlete, "activities": activities,
    })
