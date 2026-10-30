import base64
import hashlib
import secrets
from datetime import date, datetime, timedelta
import json
from urllib.parse import urlencode

import requests
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import HttpResponseForbidden, JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST, require_http_methods

from core.access import evaluation_visibility_for_request
from core.models import Athlete, AthleteDailyVital, OuraConnection
from core.views.athlete_identity import _athlete_for_user, _is_ayc_coach_user
from core.views.common import _filter_owned


OURA_AUTHORIZE_URL = "https://cloud.ouraring.com/oauth/authorize"
OURA_TOKEN_URL = "https://api.ouraring.com/oauth/token"
OURA_SCOPES = "daily"
OURA_API_BASE = "https://api.ouraring.com/v2/usercollection"
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


def revoke_oura_connection(athlete):
    """Revoke the remote token when possible and always remove local credentials."""
    connection = OuraConnection.objects.filter(athlete=athlete).first()
    if not connection:
        return
    try:
        requests.get(
            "https://api.ouraring.com/oauth/revoke",
            params={"access_token": connection.access_token},
            timeout=10,
        )
    except requests.RequestException:
        pass
    connection.delete()


def _refresh_oura_token(connection):
    if not connection.refresh_token or not _oura_configured():
        raise ValueError("Reconnect your Oura account to continue syncing.")
    response = requests.post(
        OURA_TOKEN_URL,
        data={
            "grant_type": "refresh_token",
            "refresh_token": connection.refresh_token,
            "client_id": settings.OURA_CLIENT_ID,
            "client_secret": settings.OURA_CLIENT_SECRET,
        },
        timeout=20,
        headers={"User-Agent": "MiLaPlanner/1.0"},
    )
    response.raise_for_status()
    payload = response.json()
    access_token = payload.get("access_token")
    if not access_token:
        raise ValueError("Oura token refresh did not return an access token.")
    connection.access_token = access_token
    connection.refresh_token = payload.get("refresh_token") or connection.refresh_token
    expires_in = payload.get("expires_in")
    try:
        connection.token_expires_at = timezone.now() + timedelta(seconds=max(0, int(expires_in))) if expires_in is not None else None
    except (TypeError, ValueError):
        connection.token_expires_at = None
    connection.scope = payload.get("scope") or connection.scope
    connection.save(update_fields=["access_token", "refresh_token", "token_expires_at", "scope"])


def _oura_collection(connection, collection, start_date, end_date):
    if connection.token_expires_at and connection.token_expires_at <= timezone.now() + timedelta(seconds=60):
        _refresh_oura_token(connection)
    headers = {
        "Authorization": f"Bearer {connection.access_token}",
        "User-Agent": "MiLaPlanner/1.0",
        "Accept": "application/json",
    }
    results = []
    next_token = None
    for _ in range(10):
        params = {"start_date": start_date.isoformat(), "end_date": end_date.isoformat()}
        if next_token:
            params["next_token"] = next_token
        response = requests.get(
            f"{OURA_API_BASE}/{collection}", params=params, headers=headers, timeout=20
        )
        if response.status_code == 401 and connection.refresh_token:
            _refresh_oura_token(connection)
            headers["Authorization"] = f"Bearer {connection.access_token}"
            response = requests.get(
                f"{OURA_API_BASE}/{collection}", params=params, headers=headers, timeout=20
            )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
            raise ValueError("Oura returned an unexpected data response.")
        results.extend(item for item in payload["data"] if isinstance(item, dict))
        next_token = payload.get("next_token")
        if not next_token:
            break
    return results


def build_oura_test_data(connection, *, today=None):
    """Fetch a short-lived preview of recent Oura summaries; store nothing."""
    today = today or timezone.localdate()
    start_date = today - timedelta(days=13)
    end_date = today + timedelta(days=1)
    sleep_records = _oura_collection(connection, "sleep", start_date, end_date)
    sleep_scores = _oura_collection(connection, "daily_sleep", start_date, end_date)
    readiness_scores = _oura_collection(connection, "daily_readiness", start_date, end_date)
    main_sleep_by_day = {}
    for item in sleep_records:
        try:
            day = date.fromisoformat(str(item.get("day", "")))
        except ValueError:
            continue
        if not start_date <= day <= today:
            continue
        if item.get("type") == "nap":
            continue
        duration_s = item.get("total_sleep_duration", item.get("total_sleep_time"))
        try:
            duration_s = float(duration_s)
        except (TypeError, ValueError):
            duration_s = 0
        current = main_sleep_by_day.get(day)
        if current is None or duration_s > current[0]:
            main_sleep_by_day[day] = (duration_s, item)

    def scores_by_day(records):
        result = {}
        for record in records:
            try:
                record_day = date.fromisoformat(str(record.get("day", "")))
            except ValueError:
                continue
            if start_date <= record_day <= today:
                result[record_day] = record.get("score")
        return result

    sleep_score_by_day = scores_by_day(sleep_scores)
    readiness_by_day = scores_by_day(readiness_scores)
    days = set(main_sleep_by_day) | set(sleep_score_by_day) | set(readiness_by_day)
    preview = []
    for day in sorted(days, reverse=True):
        item = main_sleep_by_day.get(day, (0, {}))[1]
        duration_s = item.get("total_sleep_duration", item.get("total_sleep_time"))
        try:
            duration_h = round(float(duration_s) / 3600, 2) if duration_s is not None else None
        except (TypeError, ValueError):
            duration_h = None
        preview.append({
            "day": day,
            "sleep_hours": duration_h,
            "sleep_score": sleep_score_by_day.get(day),
            "readiness_score": readiness_by_day.get(day),
            "lowest_heart_rate": item.get("lowest_heart_rate"),
            "average_hrv": item.get("average_hrv"),
        })
    return preview


def build_oura_vitals_suggestions(connection, athlete, *, today=None):
    """Return only readiness-backed Oura values for still-empty Daily Vitals fields."""
    today = today or timezone.localdate()
    preview = build_oura_test_data(connection, today=today)
    existing = {
        vital.date: vital
        for vital in AthleteDailyVital.objects.filter(
            athlete=athlete,
            date__gte=today - timedelta(days=13),
            date__lte=today,
        )
    }
    suggestions = []
    for item in preview:
        if item["readiness_score"] is None:
            continue
        vital = existing.get(item["day"])
        row = {"day": item["day"].isoformat()}

        sleep_hours = item["sleep_hours"]
        if (not vital or vital.sleep_hours is None) and sleep_hours is not None and 0 < sleep_hours <= 24:
            row["sleep_hours"] = sleep_hours
        else:
            row["sleep_hours"] = None

        sleep_score = item["sleep_score"]
        if (not vital or vital.sleep_quality is None) and sleep_score is not None:
            try:
                score = float(sleep_score)
                row["sleep_quality"] = round(score / 10, 1) if 1 <= score <= 100 else None
            except (TypeError, ValueError):
                row["sleep_quality"] = None
        else:
            row["sleep_quality"] = None

        average_hrv = item["average_hrv"]
        if (not vital or vital.hrv is None) and average_hrv is not None:
            try:
                hrv = round(float(average_hrv))
                row["hrv"] = hrv if 0 <= hrv <= 65535 else None
            except (TypeError, ValueError):
                row["hrv"] = None
        else:
            row["hrv"] = None

        # Oura's lowest sleep heart rate is not the same measurement as a
        # morning heart-rate reading, so it is deliberately not suggested.
        if any(row[field] is not None for field in ("sleep_hours", "sleep_quality", "hrv")):
            suggestions.append(row)
    return suggestions


def _oura_import_athlete(request):
    athlete = _athlete_user(request)
    if not athlete or not athlete.oura_connection_enabled or not athlete.daily_vitals_enabled:
        return None
    visibility = evaluation_visibility_for_request(request, athlete.owner, athlete_self=True)
    if not visibility["vitals"]:
        return None
    if not OuraConnection.objects.filter(athlete=athlete).exists():
        return None
    return athlete


@login_required
@require_POST
def oura_vitals_import_view(request):
    """Preview or explicitly apply readiness-backed values to the athlete's own vitals."""
    athlete = _oura_import_athlete(request)
    if athlete is None:
        return JsonResponse({"error": "Oura import is not available for this account."}, status=403)
    connection = OuraConnection.objects.filter(athlete=athlete).first()
    action = request.POST.get("action")
    if action not in {"preview", "apply"}:
        return JsonResponse({"error": "Unknown Oura import action."}, status=400)

    selected_days = None
    if action == "apply":
        try:
            raw_selected = json.loads(request.POST.get("selected_days", "[]"))
            if not isinstance(raw_selected, list) or any(not isinstance(value, str) for value in raw_selected):
                raise ValueError
            selected_days = {date.fromisoformat(value) for value in raw_selected}
        except (TypeError, ValueError):
            return JsonResponse({"error": "The selected dates were not valid."}, status=400)

    try:
        suggestions = build_oura_vitals_suggestions(connection, athlete)
    except (requests.RequestException, ValueError, KeyError):
        return JsonResponse({"error": "Oura data could not be fetched. Please try again or reconnect Oura."}, status=502)

    if action == "preview":
        return JsonResponse({"items": suggestions})

    saved = []
    with transaction.atomic():
        for item in suggestions:
            day = date.fromisoformat(item["day"])
            if day not in selected_days:
                continue
            vital = AthleteDailyVital.objects.select_for_update().filter(athlete=athlete, date=day).first()
            if vital is None:
                vital = AthleteDailyVital(athlete=athlete, date=day)
            changed_fields = []
            for field in ("sleep_hours", "sleep_quality", "hrv"):
                value = item.get(field)
                if value is not None and getattr(vital, field) is None:
                    setattr(vital, field, value)
                    changed_fields.append(field)
            if changed_fields:
                vital.updated_by = request.user
                vital.save()
                saved.append({
                    "day": day.isoformat(),
                    "sleep_hours": vital.sleep_hours,
                    "sleep_quality": vital.sleep_quality,
                    "morning_hr": vital.morning_hr,
                    "hrv": vital.hrv,
                })
    return JsonResponse({"items": saved, "saved_count": len(saved)})


@login_required
@require_POST
def oura_connect_view(request):
    athlete = _athlete_user(request)
    if athlete is None:
        return HttpResponseForbidden("Oura can only be connected from the athlete's own account.")
    if not athlete.oura_connection_enabled:
        return redirect(f"{reverse('dashboard')}?oura=not_enabled")
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
    if not pending or athlete is None or not athlete.oura_connection_enabled:
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
    revoke_oura_connection(athlete)
    return redirect(f"{reverse('dashboard')}?oura=disconnected")


@login_required
@require_http_methods(["GET", "POST"])
def oura_test_view(request):
    is_coach = _is_ayc_coach_user(request.user)
    if is_coach:
        athletes = _filter_owned(
            Athlete.objects.filter(oura_connection_enabled=True).order_by("name"), request
        ).filter(oura_connection__isnull=False)
        raw_athlete_id = request.POST.get("athlete_id") or request.GET.get("athlete_id") or ""
        athlete = athletes.filter(id=raw_athlete_id).first() if raw_athlete_id.isdigit() else None
        if athlete is None and athletes.count() == 1:
            athlete = athletes.first()
    else:
        athlete = _athlete_user(request)
        athletes = [athlete] if athlete and athlete.oura_connection_enabled and OuraConnection.objects.filter(athlete=athlete).exists() else []
        if not athletes:
            athlete = None

    connection = OuraConnection.objects.filter(athlete=athlete).first() if athlete else None
    data = []
    error = ""
    fetched = False
    if request.method == "POST":
        if not athlete or not connection:
            error = "Choose an athlete with an active Oura connection."
        else:
            try:
                data = build_oura_test_data(connection)
                fetched = True
            except (requests.RequestException, ValueError, KeyError):
                error = "Oura data could not be fetched. Please try again or reconnect the Oura account."

    return render(request, "core/oura_test.html", {
        "athletes": athletes,
        "selected_athlete": athlete,
        "oura_connected": bool(connection),
        "data": data,
        "error": error,
        "fetched": fetched,
    })
