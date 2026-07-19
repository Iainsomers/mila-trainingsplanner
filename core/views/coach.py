from datetime import date, timedelta
import calendar as py_calendar
import base64
import json
import os
import secrets
from urllib.parse import urlencode
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from django.http import HttpResponse, JsonResponse
from django.shortcuts import render, get_object_or_404, redirect
from django.urls import reverse
from django.views.decorators.http import require_GET, require_http_methods
from django.views.decorators.clickjacking import xframe_options_sameorigin
from django.contrib.auth.decorators import login_required
from django.contrib.auth import get_user_model
from django.db.models.functions import Lower
from django.core.cache import cache
from django.db import IntegrityError, transaction
from django.db.models import Prefetch
from django.utils import timezone

from core.models import TrainingPlan, Athlete, Group, PlanMembership, CoachSettings, TrainingSlot, PlanWeekPhase, SavedTrainingTemplate, StandardStrengthProgram, StandardStrengthExercise, RaceEvent, RaceEventDistance, RaceEntry, AthleteBasePlanningBlock, AthleteBasePlanningSlot, PolarConnection
from core.parser import parse_segment_text
from core.stats import STATS_VERSION_KEY
from core.wucd import auto_wucd_texts_for_target, create_parsed_wucd_segment
from .common import (
    _parse_iso_date,
    _parse_int,
    _parse_float,
    _clean_int_list,
    _plans_targeting_athlete,
    _ranges_overlap,
    _filter_owned,
)

from core.zones import (
    DEFAULT_ZONE_SPEED_MPS,
    zone_unit_label,
    parse_manual_zones_required,
    zones_form_from_speeds,
)


def _parse_pr_time_to_seconds(value: str):
    s = (value or "").strip().replace(";", ":")
    if not s:
        raise ValueError("empty")

    if ":" in s:
        parts = s.split(":")

        if len(parts) == 2:
            mm, ss = parts
            if not mm.isdigit():
                raise ValueError("bad format")
            try:
                minutes = int(mm)
                seconds = float(ss)
            except ValueError:
                raise ValueError("bad format")
            if seconds < 0 or seconds >= 60:
                raise ValueError("bad range")
            total_s = minutes * 60 + seconds
            if total_s <= 0:
                raise ValueError("bad range")
            return total_s

        if len(parts) == 3:
            hh, mm, ss = parts
            if not (hh.isdigit() and mm.isdigit()):
                raise ValueError("bad format")
            try:
                hours = int(hh)
                minutes = int(mm)
                seconds = float(ss)
            except ValueError:
                raise ValueError("bad format")
            if minutes < 0 or minutes >= 60 or seconds < 0 or seconds >= 60:
                raise ValueError("bad range")
            total_s = hours * 3600 + minutes * 60 + seconds
            if total_s <= 0:
                raise ValueError("bad range")
            return total_s

        raise ValueError("bad format")

    dot_parts = s.split(".")

    if len(dot_parts) == 3:
        mm, ss, ms = dot_parts
        if not (mm.isdigit() and ss.isdigit() and ms.isdigit()):
            raise ValueError("bad format")
        minutes = int(mm)
        seconds = int(ss)
        millis = int(ms)
        if seconds < 0 or seconds >= 60:
            raise ValueError("bad range")
        total_s = minutes * 60 + seconds + (millis / (10 ** len(ms)))
        if total_s <= 0:
            raise ValueError("bad range")
        return total_s

    if len(dot_parts) == 2:
        ss, ms = dot_parts
        if not (ss.isdigit() and ms.isdigit()):
            raise ValueError("bad format")
        seconds = int(ss) + (int(ms) / (10 ** len(ms)))
        if seconds <= 0:
            raise ValueError("bad range")
        return seconds

    raise ValueError("bad format")



def _format_pr_seconds(value):
    if value is None:
        return ""
    try:
        total_s = float(value)
    except (TypeError, ValueError):
        return ""
    if total_s <= 0:
        return ""

    hours = int(total_s // 3600)
    minutes = int((total_s % 3600) // 60)
    seconds = total_s - (hours * 3600 + minutes * 60)

    if abs(seconds - round(seconds)) < 1e-9:
        sec_str = f"{int(round(seconds)):02d}"
    else:
        sec_str = f"{seconds:05.2f}".rstrip("0").rstrip(".")
        if seconds < 10:
            sec_str = f"0{sec_str}"

    if hours > 0:
        return f"{hours}:{minutes:02d}:{sec_str}"
    return f"{minutes}:{sec_str}"


def _parse_optional_target_prs(post):
    values = {}
    errors = []
    fields = (
        ("target_pr_800", "target_pr_800_s", "Goal T800"),
        ("target_pr_1500", "target_pr_1500_s", "Goal T1500"),
        ("target_pr_3000", "target_pr_3000_s", "Goal T3000"),
        ("target_pr_5000", "target_pr_5000_s", "Goal T5000"),
        ("target_pr_10000", "target_pr_10000_s", "Goal T10000"),
        ("target_tm", "target_pr_tm_s", "Goal TM"),
        ("target_thm", "target_pr_thm_s", "Goal THM"),
        ("target_t4", "target_pr_400_s", "Goal T4"),
    )

    for form_key, model_field, label in fields:
        raw = (post.get(form_key) or "").strip()
        if not raw:
            values[model_field] = None
            continue
        try:
            values[model_field] = _parse_pr_time_to_seconds(raw)
        except ValueError:
            values[model_field] = None
            errors.append(f"{label} invalid format.")

    return values, errors



def _plan_week_count(start_date, end_date):
    if not start_date or not end_date:
        return 0
    start_week = start_date - timedelta(days=start_date.weekday())
    end_week = end_date - timedelta(days=end_date.weekday())
    return ((end_week - start_week).days // 7) + 1


def _copy_plan_contents(source_plan, target_plan):
    source_weeks = _plan_week_count(source_plan.start_date, source_plan.end_date)
    target_weeks = _plan_week_count(target_plan.start_date, target_plan.end_date)
    weeks_to_copy = min(source_weeks, target_weeks)

    if weeks_to_copy <= 0:
        return

    source_week0 = source_plan.start_date - timedelta(days=source_plan.start_date.weekday())
    target_week0 = target_plan.start_date - timedelta(days=target_plan.start_date.weekday())

    source_slots = (
        TrainingSlot.objects
        .filter(plan=source_plan, athlete__isnull=True)
        .prefetch_related("segments")
        .order_by("date", "slot_index", "id")
    )

    for source_slot in source_slots:
        week_index = ((source_slot.date - source_week0).days // 7)
        if week_index < 0 or week_index >= weeks_to_copy:
            continue

        target_date = target_week0 + timedelta(days=week_index * 7 + source_slot.date.weekday())
        target_slot, _ = TrainingSlot.objects.get_or_create(
            plan=target_plan,
            athlete=None,
            date=target_date,
            slot_index=source_slot.slot_index,
        )
        target_slot.segments.all().delete()

        for source_seg in source_slot.segments.order_by("order", "id"):
            seg = target_slot.segments.create(
                type=source_seg.type,
                text=source_seg.text or "",
                order=int(source_seg.order or 0),
            )
            seg.zone = source_seg.zone or ""
            seg.reps = int(source_seg.reps or 1)
            seg.distance_m = source_seg.distance_m if source_seg.distance_m is not None else None
            seg.duration_s = source_seg.duration_s if source_seg.duration_s is not None else None
            seg.norm_distance_m = source_seg.norm_distance_m if source_seg.norm_distance_m is not None else None
            seg.parse_ok = bool(source_seg.parse_ok)
            seg.parse_message = source_seg.parse_message or ""
            seg.special = getattr(source_seg, "special", "") or ""
            if hasattr(seg, "t_type"):
                seg.t_type = getattr(source_seg, "t_type", "") or ""
            if getattr(source_seg, "parsed_at", None):
                seg.parsed_at = source_seg.parsed_at
            seg.save()


    source_phase_map = {
        phase.week_start: (phase.phase or "")
        for phase in PlanWeekPhase.objects.filter(plan=source_plan)
    }

    for week_index in range(weeks_to_copy):
        source_week_start = source_week0 + timedelta(days=week_index * 7)
        target_week_start = target_week0 + timedelta(days=week_index * 7)
        source_phase_value = source_phase_map.get(source_week_start, None)

        if source_phase_value is None:
            continue

        PlanWeekPhase.objects.update_or_create(
            plan=target_plan,
            week_start=target_week_start,
            defaults={"phase": source_phase_value},
        )


def _identity_value(value):
    return "".join(ch.lower() for ch in (value or "") if ch.isalnum())


def _athlete_for_user(user):
    if not user or not user.is_authenticated:
        return None

    athlete_fields = {field.name for field in Athlete._meta.get_fields()}
    if "user" in athlete_fields:
        athlete = Athlete.objects.filter(user=user).first()
        if athlete:
            return athlete

    candidates = []
    for value in (
        getattr(user, "username", ""),
        getattr(user, "email", ""),
        getattr(user, "first_name", ""),
        getattr(user, "last_name", ""),
        f"{getattr(user, 'first_name', '')} {getattr(user, 'last_name', '')}",
    ):
        normalized = _identity_value(value)
        if normalized:
            candidates.append(normalized)

    if not candidates:
        return None

    for athlete in Athlete.objects.select_related("owner").order_by("owner_id", "name", "id"):
        athlete_name = _identity_value(getattr(athlete, "name", ""))
        if athlete_name and athlete_name in candidates:
            return athlete

    return None


def _user_for_athlete(athlete):
    if not athlete:
        return None

    athlete_fields = {field.name for field in Athlete._meta.get_fields()}
    if "user" in athlete_fields and getattr(athlete, "user_id", None):
        return athlete.user

    athlete_name = _identity_value(getattr(athlete, "name", ""))
    if not athlete_name:
        return None

    UserModel = get_user_model()
    for user in UserModel.objects.order_by("id"):
        candidates = []
        for value in (
            getattr(user, "username", ""),
            getattr(user, "email", ""),
            getattr(user, "first_name", ""),
            getattr(user, "last_name", ""),
            f"{getattr(user, 'first_name', '')} {getattr(user, 'last_name', '')}",
        ):
            normalized = _identity_value(value)
            if normalized:
                candidates.append(normalized)
        if athlete_name in candidates:
            return user
    return None


def _polar_targets_for_user(user):
    if user.is_staff or user.is_superuser:
        athletes = list(_filter_owned(Athlete.objects.order_by("name"), user))
        targets = []
        seen_user_ids = set()
        for athlete in athletes:
            athlete_user = _user_for_athlete(athlete)
            connection = PolarConnection.objects.filter(user=athlete_user).first() if athlete_user else None
            if athlete_user:
                seen_user_ids.add(athlete_user.id)
            targets.append({
                "key": f"athlete:{athlete.id}",
                "label": athlete.name,
                "athlete": athlete,
                "user": athlete_user,
                "connection": connection,
                "connected": bool(connection and connection.access_token),
            })
        for connection in PolarConnection.objects.select_related("user").exclude(user_id__in=seen_user_ids).order_by("user__username", "id"):
            if not connection.access_token:
                continue
            label = connection.user.get_full_name() or connection.user.username
            targets.append({
                "key": f"user:{connection.user_id}",
                "label": f"{label} (Polar user)",
                "athlete": None,
                "user": connection.user,
                "connection": connection,
                "connected": True,
            })
        return targets

    athlete = _athlete_for_user(user)
    label = athlete.name if athlete else (user.get_full_name() or user.username)
    return [{
        "key": "self",
        "label": label,
        "athlete": athlete,
        "user": user,
        "connection": PolarConnection.objects.filter(user=user).first(),
        "connected": bool(PolarConnection.objects.filter(user=user, access_token__gt="").exists()),
    }]


def _selected_polar_target(request):
    targets = _polar_targets_for_user(request.user)
    requested_key = (request.GET.get("polar_target") or request.POST.get("polar_target") or request.session.get("polar_target") or "").strip()
    keys = {target["key"] for target in targets}
    if requested_key not in keys:
        requested_key = "self" if "self" in keys else (targets[0]["key"] if targets else "")
    if requested_key:
        request.session["polar_target"] = requested_key
        request.session.modified = True
    for target in targets:
        if target["key"] == requested_key:
            return target, targets
    return None, targets


@login_required
@require_GET
def dashboard_view(request):
    athlete = _athlete_for_user(request.user)
    is_athlete_user = bool(athlete and not request.user.is_staff and not request.user.is_superuser)

    return render(request, "core/dashboard.html", {
        "is_athlete_user": is_athlete_user,
        "current_athlete": athlete,
    })


POLAR_AUTHORIZATION_URL = "https://flow.polar.com/oauth2/authorization"
POLAR_TOKEN_URL = "https://polarremote.com/v2/oauth2/token"
POLAR_REGISTER_USER_URL = "https://www.polaraccesslink.com/v3/users"
POLAR_EXERCISES_URL = "https://www.polaraccesslink.com/v3/exercises"
POLAR_PHYSICAL_INFO_URL = "https://www.polaraccesslink.com/v3/users/physical-info"
POLAR_ACTIVITIES_URL = "https://www.polaraccesslink.com/v3/users/activities"


def _polar_config():
    return {
        "client_id": (os.environ.get("POLAR_CLIENT_ID") or "").strip(),
        "client_secret": (os.environ.get("POLAR_CLIENT_SECRET") or "").strip(),
        "redirect_uri": (os.environ.get("POLAR_REDIRECT_URI") or "").strip(),
    }


def _polar_missing_config(config):
    env_names = {
        "client_id": "POLAR_CLIENT_ID",
        "client_secret": "POLAR_CLIENT_SECRET",
        "redirect_uri": "POLAR_REDIRECT_URI",
    }
    return [env_names[key] for key, value in config.items() if not value]


def _polar_basic_auth_header(client_id, client_secret):
    raw = f"{client_id}:{client_secret}".encode("utf-8")
    return "Basic " + base64.b64encode(raw).decode("ascii")


def _polar_json_request(url, *, method="GET", data=None, headers=None):
    body = None
    request_headers = dict(headers or {})
    if data is not None:
        body = data if isinstance(data, bytes) else json.dumps(data).encode("utf-8")
    request = Request(url, data=body, headers=request_headers, method=method)
    try:
        with urlopen(request, timeout=20) as response:
            raw = response.read().decode("utf-8")
            if not raw:
                return response.status, {}
            return response.status, json.loads(raw)
    except HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            payload = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            payload = {"error": raw}
        return exc.code, payload
    except URLError as exc:
        raise RuntimeError(str(exc.reason)) from exc


@login_required
@require_GET
def polar_integration_view(request):
    config = _polar_config()
    selected_target, polar_targets = _selected_polar_target(request)
    is_coach_polar_view = bool(request.user.is_staff or request.user.is_superuser)
    connection = selected_target["connection"] if selected_target else PolarConnection.objects.filter(user=request.user).first()
    sync_result = request.session.pop("polar_sync_result", None)
    steps_result = request.session.pop("polar_steps_result", None)
    return render(request, "core/polar_integration.html", {
        "connection": connection,
        "selected_target": selected_target,
        "polar_targets": polar_targets,
        "is_coach_polar_view": is_coach_polar_view,
        "missing_config": _polar_missing_config(config),
        "polar_error": request.GET.get("error", ""),
        "polar_connected": request.GET.get("connected") == "1",
        "sync_result": sync_result,
        "steps_result": steps_result,
    })


@login_required
@require_GET
def polar_connect_view(request):
    config = _polar_config()
    missing = _polar_missing_config(config)
    if missing:
        return redirect(f"{reverse('polar_integration')}?{urlencode({'error': 'Missing Polar configuration: ' + ', '.join(missing)})}")

    state = secrets.token_urlsafe(32)
    request.session["polar_oauth_state"] = state
    params = {
        "response_type": "code",
        "client_id": config["client_id"],
        "redirect_uri": config["redirect_uri"],
        "scope": "accesslink.read_all",
        "state": state,
    }
    return redirect(f"{POLAR_AUTHORIZATION_URL}?{urlencode(params)}")


@login_required
@require_GET
def polar_callback_view(request):
    expected_state = request.session.pop("polar_oauth_state", "")
    received_state = request.GET.get("state", "")
    if not expected_state or received_state != expected_state:
        return redirect(f"{reverse('polar_integration')}?{urlencode({'error': 'Polar authorization state did not match.'})}")

    code = request.GET.get("code", "")
    if not code:
        return redirect(f"{reverse('polar_integration')}?{urlencode({'error': request.GET.get('error') or 'Polar did not return an authorization code.'})}")

    config = _polar_config()
    missing = _polar_missing_config(config)
    if missing:
        return redirect(f"{reverse('polar_integration')}?{urlencode({'error': 'Missing Polar configuration: ' + ', '.join(missing)})}")

    token_body = urlencode({
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": config["redirect_uri"],
    }).encode("utf-8")
    token_headers = {
        "Accept": "application/json",
        "Content-Type": "application/x-www-form-urlencoded",
        "Authorization": _polar_basic_auth_header(config["client_id"], config["client_secret"]),
    }

    try:
        token_status, token_payload = _polar_json_request(
            POLAR_TOKEN_URL,
            method="POST",
            data=token_body,
            headers=token_headers,
        )
    except RuntimeError as exc:
        return redirect(f"{reverse('polar_integration')}?{urlencode({'error': 'Polar token request failed: ' + str(exc)})}")

    if token_status >= 400:
        polar_message = ""
        if isinstance(token_payload, dict):
            polar_message = token_payload.get("error_description") or token_payload.get("error") or ""
        error_message = f"Polar token request failed with status {token_status}."
        if polar_message:
            error_message = f"{error_message} {polar_message}"
        return redirect(f"{reverse('polar_integration')}?{urlencode({'error': error_message})}")

    access_token = token_payload.get("access_token", "")
    polar_user_id = str(token_payload.get("x_user_id") or "")
    if not access_token or not polar_user_id:
        return redirect(f"{reverse('polar_integration')}?{urlencode({'error': 'Polar token response was incomplete.'})}")

    member_id = f"mila-user-{request.user.id}"
    register_headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Authorization": f"Bearer {access_token}",
    }
    register_status, register_payload = _polar_json_request(
        POLAR_REGISTER_USER_URL,
        method="POST",
        data={"member-id": member_id},
        headers=register_headers,
    )

    last_error = ""
    if register_status not in {200, 409}:
        last_error = f"Polar user registration failed with status {register_status}."

    PolarConnection.objects.update_or_create(
        user=request.user,
        defaults={
            "member_id": member_id,
            "polar_user_id": polar_user_id,
            "access_token": access_token,
            "token_type": token_payload.get("token_type", ""),
            "expires_in": token_payload.get("expires_in"),
            "scope": token_payload.get("scope", ""),
            "status": PolarConnection.STATUS_ERROR if last_error else PolarConnection.STATUS_CONNECTED,
            "last_error": last_error,
            "raw_token_response": token_payload,
            "raw_user_response": register_payload if isinstance(register_payload, dict) else {},
            "connected_at": timezone.now(),
        },
    )

    if last_error:
        return redirect(f"{reverse('polar_integration')}?{urlencode({'error': last_error})}")
    return redirect(f"{reverse('polar_integration')}?connected=1")


@login_required
@require_http_methods(["POST"])
def polar_sync_test_view(request):
    selected_target, _targets = _selected_polar_target(request)
    connection = selected_target["connection"] if selected_target else None
    if not connection or not connection.access_token:
        return redirect(f"{reverse('polar_integration')}?{urlencode({'error': 'No Polar account is connected yet.'})}")

    headers = {
        "Accept": "application/json",
        "Authorization": f"Bearer {connection.access_token}",
    }

    checks = [
        ("Exercises", f"{POLAR_EXERCISES_URL}?{urlencode({'samples': 'false', 'zones': 'false', 'route': 'false'})}"),
        ("Physical info", POLAR_PHYSICAL_INFO_URL),
        ("Daily activity", f"{POLAR_ACTIVITIES_URL}?{urlencode({'steps': 'false', 'activity_zones': 'false', 'inactivity_stamps': 'false'})}"),
    ]
    results = []
    error_message = ""
    for label, url in checks:
        try:
            status, payload = _polar_json_request(url, method="GET", headers=headers)
        except RuntimeError as exc:
            status = 0
            payload = {"error": str(exc)}

        if isinstance(payload, list):
            item_count = len(payload)
        elif isinstance(payload, dict) and isinstance(payload.get("exercises"), list):
            item_count = len(payload["exercises"])
        elif isinstance(payload, dict) and payload:
            item_count = 1
        else:
            item_count = 0

        pretty_payload = json.dumps(payload, indent=2, ensure_ascii=False)
        if len(pretty_payload) > 12000:
            pretty_payload = pretty_payload[:12000] + "\n... truncated ..."

        results.append({
            "label": label,
            "status": status,
            "item_count": item_count,
            "payload": pretty_payload,
        })

        if status >= 400 or status == 0:
            polar_message = ""
            if isinstance(payload, dict):
                polar_message = payload.get("error_description") or payload.get("error") or ""
            error_message = f"Polar {label.lower()} request failed with status {status}."
            if polar_message:
                error_message = f"{error_message} {polar_message}"
            break

    request.session["polar_sync_result"] = {"checks": results}

    if error_message:
        connection.status = PolarConnection.STATUS_ERROR
        connection.last_error = error_message
        connection.save(update_fields=["status", "last_error", "updated_at"])
        return redirect(f"{reverse('polar_integration')}?{urlencode({'error': error_message})}")

    connection.status = PolarConnection.STATUS_CONNECTED
    connection.last_error = ""
    connection.save(update_fields=["status", "last_error", "updated_at"])
    return redirect("polar_integration")


@login_required
@require_http_methods(["POST"])
def polar_steps_view(request):
    selected_target, _targets = _selected_polar_target(request)
    connection = selected_target["connection"] if selected_target else None
    if not connection or not connection.access_token:
        return redirect(f"{reverse('polar_integration')}?{urlencode({'error': 'No Polar account is connected yet.'})}")

    headers = {
        "Accept": "application/json",
        "Authorization": f"Bearer {connection.access_token}",
    }
    url = f"{POLAR_ACTIVITIES_URL}?{urlencode({'steps': 'false', 'activity_zones': 'false', 'inactivity_stamps': 'false'})}"
    try:
        status, payload = _polar_json_request(url, method="GET", headers=headers)
    except RuntimeError as exc:
        error_message = f"Polar steps request failed: {exc}"
        connection.status = PolarConnection.STATUS_ERROR
        connection.last_error = error_message
        connection.save(update_fields=["status", "last_error", "updated_at"])
        return redirect(f"{reverse('polar_integration')}?{urlencode({'error': error_message})}")

    if status >= 400:
        polar_message = ""
        if isinstance(payload, dict):
            polar_message = payload.get("error_description") or payload.get("error") or ""
        error_message = f"Polar steps request failed with status {status}."
        if polar_message:
            error_message = f"{error_message} {polar_message}"
        connection.status = PolarConnection.STATUS_ERROR
        connection.last_error = error_message
        connection.save(update_fields=["status", "last_error", "updated_at"])
        return redirect(f"{reverse('polar_integration')}?{urlencode({'error': error_message})}")

    rows = []
    if isinstance(payload, list):
        for item in payload:
            if not isinstance(item, dict):
                continue
            start_time = item.get("start_time") or ""
            steps = item.get("steps")
            if steps is None:
                continue
            rows.append({
                "date": start_time[:10] if start_time else "",
                "steps": int(steps),
            })

    rows = sorted(rows, key=lambda row: row["date"], reverse=True)[:21]
    values = [row["steps"] for row in rows]
    if values:
        average_steps = round(sum(values) / len(values))
        max_steps = max(values)
        min_steps = min(values)
    else:
        average_steps = max_steps = min_steps = 0

    request.session["polar_steps_result"] = {
        "status": status,
        "days": len(rows),
        "average_steps": average_steps,
        "max_steps": max_steps,
        "min_steps": min_steps,
        "rows": rows,
    }

    connection.status = PolarConnection.STATUS_CONNECTED
    connection.last_error = ""
    connection.save(update_fields=["status", "last_error", "updated_at"])
    return redirect("polar_integration")


@login_required
@require_GET
def coach_console_view(request):
    return redirect("planning_overview")


@login_required
@require_GET
def planning_overview_view(request):
    athlete = _athlete_for_user(request.user)
    is_athlete_user = bool(athlete and not request.user.is_staff and not request.user.is_superuser)
    groups = Group.objects.none() if is_athlete_user else _filter_owned(Group.objects.order_by("name"), request.user)
    return render(request, "core/planning.html", {
        "groups": groups,
        "today": date.today(),
        "is_athlete_user": is_athlete_user,
    })


def _trainer_planning_qs(user):
    return _filter_owned(
        TrainingPlan.objects.filter(plan_kind=TrainingPlan.PLAN_KIND_TRAINER),
        user,
    )


@login_required
@require_http_methods(["GET", "POST"])
def trainer_planning_view(request):
    errors = []
    form = {
        "name": "",
        "is_private": False,
    }

    if request.method == "POST":
        action = (request.POST.get("action") or "create").strip()

        form["name"] = (request.POST.get("name") or "").strip()
        form["is_private"] = (request.POST.get("is_private") == "on")

        if not form["name"]:
            errors.append("Name is required.")

        if not errors:
            try:
                plan = TrainingPlan.objects.create(
                    owner=request.user,
                    name=form["name"],
                    plan_kind=TrainingPlan.PLAN_KIND_TRAINER,
                    start_date=None,
                    end_date=None,
                    week_phases_enabled=False,
                    is_private=form["is_private"],
                )
            except IntegrityError:
                errors.append("Er bestaat al een planning met deze naam.")
            else:
                if (request.POST.get("next") or "").strip() == "overview":
                    return redirect("trainer_planning")
                return redirect("trainer_planning_detail", plan_id=plan.id)

    plannings = _trainer_planning_qs(request.user).order_by(Lower("name"))
    return render(
        request,
        "core/trainer_planning.html",
        {"plannings": plannings, "form": form, "errors": errors},
    )


@login_required
@require_http_methods(["POST"])
def trainer_planning_delete_view(request, plan_id: int):
    plan = get_object_or_404(_trainer_planning_qs(request.user), id=plan_id)
    plan.delete()
    return redirect("trainer_planning")


@login_required
@require_http_methods(["GET", "POST"])
def trainer_planning_detail_view(request, plan_id: int):
    plan = get_object_or_404(_trainer_planning_qs(request.user), id=plan_id)
    errors = []

    if request.method == "POST":
        new_name = (request.POST.get("name") or "").strip()
        plan.auto_wucd_enabled = request.POST.get("auto_wucd_enabled") == "on"
        plan.auto_wu_m = _clean_non_negative_int(request.POST.get("auto_wu_m"))
        plan.auto_cd_m = _clean_non_negative_int(request.POST.get("auto_cd_m"))
        if not new_name:
            errors.append("Name is required.")
        elif _trainer_planning_qs(request.user).exclude(id=plan.id).filter(name=new_name).exists():
            errors.append("Er bestaat al een planning met deze naam.")
        else:
            plan.name = new_name
            try:
                plan.save(update_fields=["name", "auto_wucd_enabled", "auto_wu_m", "auto_cd_m", "updated_at"])
            except IntegrityError:
                errors.append("Er bestaat al een planning met deze naam.")
            else:
                if request.POST.get("autosave") == "1":
                    return HttpResponse("", status=204)
                if (request.POST.get("next") or "").strip() == "overview":
                    return redirect("trainer_planning")
                return redirect("trainer_planning_detail", plan_id=plan.id)

    date_value = (request.GET.get("date") or "").strip()
    try:
        anchor_day = _parse_iso_date(date_value) if date_value else date.today()
    except ValueError:
        anchor_day = date.today()

    week_start = anchor_day - timedelta(days=anchor_day.weekday())
    prev_week = week_start - timedelta(days=7)
    next_week = week_start + timedelta(days=7)
    try:
        visible_weeks = int((request.GET.get("weeks") or "4").strip())
    except ValueError:
        visible_weeks = 4
    visible_weeks = max(1, min(12, visible_weeks))
    week_end = week_start + timedelta(days=(visible_weeks * 7) - 1)
    days = [week_start + timedelta(days=i) for i in range(visible_weeks * 7)]
    week_starts = [week_start + timedelta(days=7 * i) for i in range(visible_weeks)]
    week_options = [1, 2, 3, 4, 6, 8, 12]
    today_week_start = date.today() - timedelta(days=date.today().weekday())
    week_clipboard = request.session.get("week_clipboard") or {}
    clipboard_plan_id = week_clipboard.get("source_plan_id") if isinstance(week_clipboard, dict) else None
    clipboard_week_start = week_clipboard.get("source_week_start") if isinstance(week_clipboard, dict) else ""
    has_week_clipboard = bool(week_clipboard)

    slots = (
        TrainingSlot.objects
        .filter(plan=plan, athlete__isnull=True, date__in=days)
        .prefetch_related("segments")
    )
    slot_map = {(slot.date, int(slot.slot_index)): slot for slot in slots}

    week_rows = []
    for visible_week_start in week_starts:
        week_days = [visible_week_start + timedelta(days=i) for i in range(7)]
        rows = []
        for slot_index, label in ((1, "AM"), (2, "PM")):
            rows.append({
                "slot_index": slot_index,
                "label": label,
                "cells": [
                    {"day": day, "slot": slot_map.get((day, slot_index))}
                    for day in week_days
                ],
            })
        week_rows.append({
            "week_start": visible_week_start,
            "week_end": visible_week_start + timedelta(days=6),
            "days": week_days,
            "rows": rows,
            "is_current_week": visible_week_start == today_week_start,
            "has_clipboard_source": (
                clipboard_plan_id == plan.id and clipboard_week_start == visible_week_start.isoformat()
            ),
        })

    return render(
        request,
        "core/trainer_planning_detail.html",
        {
            "plan": plan,
            "week_start": week_start,
            "week_end": week_end,
            "prev_week": prev_week,
            "next_week": next_week,
            "visible_weeks": visible_weeks,
            "week_options": week_options,
            "date_value": anchor_day.isoformat(),
            "days": days,
            "week_rows": week_rows,
            "has_week_clipboard": has_week_clipboard,
            "selected_plan": plan,
            "selected_athlete": None,
            "display_mode": "core_only",
            "errors": errors,
        },
    )


def _parse_month_day(value: str):
    value = (value or "").strip()
    parts = value.split("-")
    if len(parts) != 2:
        raise ValueError("bad month-day")

    day = int(parts[0])
    month = int(parts[1])
    if month < 1 or month > 12:
        raise ValueError("bad month")
    if day < 1 or day > py_calendar.monthrange(2024, month)[1]:
        raise ValueError("bad day")
    return month, day


def _month_day_index(month: int, day: int) -> int:
    return date(2024, int(month), int(day)).timetuple().tm_yday


def _block_covered_days(start_month: int, start_day: int, end_month: int, end_day: int):
    start_idx = _month_day_index(start_month, start_day)
    end_idx = _month_day_index(end_month, end_day)
    if start_idx <= end_idx:
        return set(range(start_idx, end_idx + 1))
    return set(range(start_idx, 367)) | set(range(1, end_idx + 1))


def _validate_base_planning_coverage(block_values):
    coverage = {}
    for value in block_values:
        days = _block_covered_days(
            value["start_month"],
            value["start_day"],
            value["end_month"],
            value["end_day"],
        )
        for day_index in days:
            coverage.setdefault(day_index, []).append(value["label"] or f"Block {value['sort_order']}")

    missing = [day_index for day_index in range(1, 367) if day_index not in coverage]
    overlap = [day_index for day_index, labels in coverage.items() if len(labels) > 1]

    errors = []
    if missing:
        errors.append("Not every day of the year is covered.")
    if overlap:
        errors.append("Er zijn overlappende datumranges.")
    return errors


def _ensure_base_block_slots(block):
    existing = {
        (slot.weekday, slot.slot_index)
        for slot in block.slots.all()
    }
    to_create = []
    for weekday in range(7):
        for slot_index in (1, 2):
            if (weekday, slot_index) not in existing:
                to_create.append(AthleteBasePlanningSlot(
                    block=block,
                    weekday=weekday,
                    slot_index=slot_index,
                    mode=AthleteBasePlanningSlot.MODE_REST,
                ))
    if to_create:
        AthleteBasePlanningSlot.objects.bulk_create(to_create)


def _base_training_display_parts(text: str):
    labels = {
        "WU": "WU",
        "MOB": "Mob",
        "SPR": "Sprint",
        "CORE": "Core",
        "CORE2": "2nd",
        "ALT": "Alt",
        "CD": "CD",
    }
    values = {key: "" for key in labels}
    raw = (text or "").strip()
    if not raw:
        return []

    saw_key = False
    for line in raw.splitlines():
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip().upper()
        if key in values:
            values[key] = value.strip()
            saw_key = True

    if not saw_key:
        values["CORE"] = raw

    return [
        {"label": labels[key], "text": values[key]}
        for key in ("WU", "MOB", "SPR", "CORE", "CORE2", "ALT", "CD")
        if values[key]
    ]


def _base_pill_class(text: str):
    s = (text or "").lower()
    if "race" in s:
        return "base-pill-race"
    if "z6" in s or "z 6" in s:
        return "base-pill-z6"
    if "z5" in s or "z 5" in s or "t8" in s or "t15" in s or "t800" in s or "t1500" in s or "t4" in s:
        return "base-pill-z5"
    if "z4" in s or "z 4" in s or "t3" in s or "t5" in s or "t10" in s or "t3000" in s or "t5000" in s or "t10000" in s:
        return "base-pill-z4"
    if "z3" in s or "z 3" in s or "thm" in s:
        return "base-pill-z3"
    if "z2" in s or "z 2" in s or "tm" in s:
        return "base-pill-z2"
    return "base-pill-z1"


def _decorate_base_slot(slot):
    if not slot:
        return slot
    parts = _base_training_display_parts(getattr(slot, "training_text", ""))
    for part in parts:
        part["pill_class"] = _base_pill_class(part["text"])
    slot.display_parts = parts
    return slot


def _base_planning_rows(block):
    slots = {
        (slot.weekday, slot.slot_index): _decorate_base_slot(slot)
        for slot in block.slots.all()
    }
    day_labels = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    rows = []
    for weekday, label in enumerate(day_labels):
        rows.append({
            "weekday": weekday,
            "label": label,
            "am": slots.get((weekday, 1)),
            "pm": slots.get((weekday, 2)),
        })
    return rows


@login_required
@require_http_methods(["GET", "POST"])
@xframe_options_sameorigin
def athlete_base_planning_view(request):
    embedded = (request.GET.get("embedded") == "1") or (request.POST.get("embedded") == "1")
    redirect_suffix = "&embedded=1" if embedded else ""
    athletes = list(_filter_owned(Athlete.objects.order_by("name"), request.user))
    selected_athlete = None
    selected_id = (request.POST.get("athlete_id") or request.GET.get("athlete") or "").strip()
    if selected_id.isdigit():
        selected_athlete = _filter_owned(Athlete.objects.all(), request.user).filter(id=int(selected_id)).first()
    if not selected_athlete and athletes:
        selected_athlete = athletes[0]

    errors = []
    saved = False

    if request.method == "POST" and selected_athlete:
        action = (request.POST.get("action") or "").strip()

        if action == "add_block":
            sort_order = selected_athlete.base_planning_blocks.count() + 1
            block = AthleteBasePlanningBlock.objects.create(
                athlete=selected_athlete,
                label=f"Block {sort_order}",
                start_month=1,
                start_day=1,
                end_month=12,
                end_day=31,
                sort_order=sort_order,
            )
            _ensure_base_block_slots(block)
            return redirect(f"{reverse('athlete_base_planning')}?athlete={selected_athlete.id}{redirect_suffix}")

        if action == "copy_from":
            source_id = (request.POST.get("copy_from_athlete_id") or "").strip()
            source_athlete = None
            if source_id.isdigit():
                source_athlete = _filter_owned(Athlete.objects.all(), request.user).filter(id=int(source_id)).first()

            if not source_athlete:
                errors.append("Choose a valid athlete to copy from.")
            elif source_athlete.id == selected_athlete.id:
                errors.append("Choose a different athlete to copy from.")
            else:
                source_blocks = (
                    AthleteBasePlanningBlock.objects
                    .filter(athlete=source_athlete)
                    .prefetch_related("slots")
                    .order_by("sort_order", "start_month", "start_day", "id")
                )
                with transaction.atomic():
                    AthleteBasePlanningBlock.objects.filter(athlete=selected_athlete).delete()
                    for source_block in source_blocks:
                        target_block = AthleteBasePlanningBlock.objects.create(
                            athlete=selected_athlete,
                            label=source_block.label,
                            start_month=source_block.start_month,
                            start_day=source_block.start_day,
                            end_month=source_block.end_month,
                            end_day=source_block.end_day,
                            sort_order=source_block.sort_order,
                        )
                        for source_slot in source_block.slots.all():
                            AthleteBasePlanningSlot.objects.create(
                                block=target_block,
                                weekday=source_slot.weekday,
                                slot_index=source_slot.slot_index,
                                mode=source_slot.mode,
                                trainer_plan=source_slot.trainer_plan,
                                training_text=source_slot.training_text,
                            )
                return redirect(f"{reverse('athlete_base_planning')}?athlete={selected_athlete.id}{redirect_suffix}")

        if action == "save":
            block_ids = [
                int(value)
                for value in request.POST.getlist("block_id")
                if str(value).isdigit()
            ]
            blocks = {
                block.id: block
                for block in AthleteBasePlanningBlock.objects.filter(athlete=selected_athlete, id__in=block_ids)
            }

            block_values = []
            delete_ids = {
                int(value)
                for value in request.POST.getlist("delete_block")
                if str(value).isdigit()
            }

            for index, block_id in enumerate(block_ids, start=1):
                if block_id in delete_ids:
                    continue
                block = blocks.get(block_id)
                if not block:
                    continue
                prefix = f"block_{block_id}"
                label = (request.POST.get(f"{prefix}_label") or "").strip()
                try:
                    start_month, start_day = _parse_month_day(request.POST.get(f"{prefix}_start"))
                    end_month, end_day = _parse_month_day(request.POST.get(f"{prefix}_end"))
                except (TypeError, ValueError):
                    errors.append("Use date format DD-MM, for example 01-03.")
                    continue

                block_values.append({
                    "id": block_id,
                    "label": label,
                    "start_month": start_month,
                    "start_day": start_day,
                    "end_month": end_month,
                    "end_day": end_day,
                    "sort_order": index,
                })

            if not block_values:
                errors.append("Er moet minimaal een datumblok zijn.")

            errors.extend(_validate_base_planning_coverage(block_values))

            if not errors:
                trainer_plans = {
                    plan.id: plan
                    for plan in _trainer_planning_qs(request.user)
                }
                with transaction.atomic():
                    AthleteBasePlanningBlock.objects.filter(athlete=selected_athlete, id__in=delete_ids).delete()
                    for value in block_values:
                        block = blocks[value["id"]]
                        block.label = value["label"]
                        block.start_month = value["start_month"]
                        block.start_day = value["start_day"]
                        block.end_month = value["end_month"]
                        block.end_day = value["end_day"]
                        block.sort_order = value["sort_order"]
                        block.save()
                        _ensure_base_block_slots(block)

                        for slot in block.slots.all():
                            prefix = f"slot_{slot.id}"
                            mode = (request.POST.get(f"{prefix}_mode") or AthleteBasePlanningSlot.MODE_REST).strip()
                            if mode not in {
                                AthleteBasePlanningSlot.MODE_REST,
                                AthleteBasePlanningSlot.MODE_TRAINING,
                                AthleteBasePlanningSlot.MODE_TRAINER,
                            }:
                                mode = AthleteBasePlanningSlot.MODE_REST

                            slot.mode = mode
                            slot.training_text = (request.POST.get(f"{prefix}_training_text") or "").strip() if mode == AthleteBasePlanningSlot.MODE_TRAINING else ""

                            trainer_plan_id = (request.POST.get(f"{prefix}_trainer_plan") or "").strip()
                            if mode == AthleteBasePlanningSlot.MODE_TRAINER and trainer_plan_id.isdigit():
                                slot.trainer_plan = trainer_plans.get(int(trainer_plan_id))
                            else:
                                slot.trainer_plan = None
                            slot.save()
                saved = True

    blocks = []
    if selected_athlete:
        block_qs = (
            AthleteBasePlanningBlock.objects
            .filter(athlete=selected_athlete)
            .prefetch_related("slots", "slots__trainer_plan")
            .order_by("sort_order", "start_month", "start_day", "id")
        )
        for block in block_qs:
            _ensure_base_block_slots(block)
        block_qs = (
            AthleteBasePlanningBlock.objects
            .filter(athlete=selected_athlete)
            .prefetch_related("slots", "slots__trainer_plan")
            .order_by("sort_order", "start_month", "start_day", "id")
        )
        blocks = [{"block": block, "rows": _base_planning_rows(block)} for block in block_qs]

    return render(
        request,
        "core/athlete_base_planning.html",
        {
            "athletes": athletes,
            "selected_athlete": selected_athlete,
            "blocks": blocks,
            "trainer_plans": _trainer_planning_qs(request.user).order_by(Lower("name")),
            "errors": errors,
            "saved": saved,
            "mode_choices": AthleteBasePlanningSlot.MODE_CHOICES,
            "embedded": embedded,
        },
    )


def _clean_non_negative_int(value):
    try:
        return max(0, int((value or "").strip() or 0))
    except (TypeError, ValueError):
        return 0


@login_required
@require_http_methods(["GET", "POST"])
def coach_wucd_settings_view(request):
    athletes = list(_filter_owned(Athlete.objects.order_by("name"), request.user))

    if request.method == "POST":
        for athlete in athletes:
            prefix = f"athlete_{athlete.id}"
            athlete.auto_wucd_enabled = request.POST.get(f"{prefix}_enabled") == "on"
            athlete.auto_wu_m = _clean_non_negative_int(request.POST.get(f"{prefix}_wu_m"))
            athlete.auto_cd_m = _clean_non_negative_int(request.POST.get(f"{prefix}_cd_m"))
            athlete.save(update_fields=["auto_wucd_enabled", "auto_wu_m", "auto_cd_m"])

        return redirect("coach_wucd_settings")

    return render(request, "core/coach_wucd_settings.html", {
        "athletes": athletes,
    })


@login_required
@require_GET
def races_overview_view(request):
    return render(request, "core/races.html")


def _normalize_saved_training_order(user):
    templates = list(
        SavedTrainingTemplate.objects
        .filter(owner=user)
        .order_by("sort_order", "name", "id")
    )

    changed = []
    for index, template in enumerate(templates, start=1):
        if template.sort_order != index:
            template.sort_order = index
            changed.append(template)

    if changed:
        SavedTrainingTemplate.objects.bulk_update(changed, ["sort_order"])

    return templates


@login_required
@require_GET
def coach_saved_trainings_view(request):
    templates = _normalize_saved_training_order(request.user)
    return render(request, "core/coach_saved_trainings.html", {"templates": templates})


@login_required
@require_http_methods(["POST"])
def coach_saved_training_delete_view(request, template_id: int):
    template = get_object_or_404(
        SavedTrainingTemplate.objects.filter(owner=request.user),
        id=template_id,
    )
    template.delete()
    _normalize_saved_training_order(request.user)
    return redirect("coach_saved_trainings")


@login_required
@require_http_methods(["POST"])
def coach_saved_training_move_view(request, template_id: int, direction: str):
    templates = _normalize_saved_training_order(request.user)
    current_index = next((i for i, template in enumerate(templates) if template.id == template_id), None)

    if current_index is None:
        return redirect("coach_saved_trainings")

    if direction == "up":
        target_index = current_index - 1
    elif direction == "down":
        target_index = current_index + 1
    else:
        return redirect("coach_saved_trainings")

    if target_index < 0 or target_index >= len(templates):
        return redirect("coach_saved_trainings")

    current = templates[current_index]
    target = templates[target_index]
    current.sort_order, target.sort_order = target.sort_order, current.sort_order
    SavedTrainingTemplate.objects.bulk_update([current, target], ["sort_order"])

    return redirect("coach_saved_trainings")


def _standard_strength_programs_for_user(user):
    return list(
        StandardStrengthProgram.objects
        .filter(owner=user)
        .prefetch_related("exercises")
        .order_by("sort_order", "name", "id")
    )


def _standard_strength_form_rows(program=None, request_post=None):
    rows = []
    if request_post is not None:
        exercises = request_post.getlist("exercise")
        sets_values = request_post.getlist("sets")
        reps_values = request_post.getlist("reps")
        total = max(len(exercises), len(sets_values), len(reps_values), 0)
        for index in range(total):
            rows.append({
                "exercise": (exercises[index] if index < len(exercises) else "").strip(),
                "sets": (sets_values[index] if index < len(sets_values) else "").strip(),
                "reps": (reps_values[index] if index < len(reps_values) else "").strip(),
            })
    elif program:
        rows = [
            {"exercise": row.exercise, "sets": row.sets, "reps": row.reps}
            for row in program.exercises.all()
        ]

    while len(rows) < 6:
        rows.append({"exercise": "", "sets": "", "reps": ""})
    return rows


@login_required
@require_GET
def standard_strength_list_view(request):
    programs = _standard_strength_programs_for_user(request.user)
    return render(request, "core/standard_strength_list.html", {"programs": programs})


@login_required
@require_http_methods(["GET", "POST"])
def standard_strength_form_view(request, program_id=None):
    program = None
    if program_id is not None:
        program = get_object_or_404(
            StandardStrengthProgram.objects.filter(owner=request.user).prefetch_related("exercises"),
            id=program_id,
        )

    errors = []
    name = program.name if program else ""

    if request.method == "POST":
        name = (request.POST.get("name") or "").strip()
        rows = _standard_strength_form_rows(program=program, request_post=request.POST)
        filled_rows = [row for row in rows if row["exercise"] or row["sets"] or row["reps"]]

        if not name:
            errors.append("Name is required.")
        if not any(row["exercise"] for row in filled_rows):
            errors.append("Add at least one exercise.")

        if not errors:
            if not program:
                max_order = (
                    StandardStrengthProgram.objects
                    .filter(owner=request.user)
                    .order_by("-sort_order")
                    .values_list("sort_order", flat=True)
                    .first()
                    or 0
                )
                program = StandardStrengthProgram.objects.create(
                    owner=request.user,
                    name=name,
                    sort_order=max_order + 1,
                )
            else:
                program.name = name
                program.save(update_fields=["name", "updated_at"])

            program.exercises.all().delete()
            exercise_objects = []
            order = 1
            for row in filled_rows:
                if not row["exercise"]:
                    continue
                exercise_objects.append(StandardStrengthExercise(
                    program=program,
                    order=order,
                    exercise=row["exercise"],
                    sets=row["sets"],
                    reps=row["reps"],
                ))
                order += 1
            StandardStrengthExercise.objects.bulk_create(exercise_objects)
            return redirect("standard_strength_list")
    else:
        rows = _standard_strength_form_rows(program=program)

    return render(request, "core/standard_strength_form.html", {
        "program": program,
        "name": name,
        "rows": rows,
        "errors": errors,
    })


@login_required
@require_http_methods(["POST"])
def standard_strength_delete_view(request, program_id: int):
    program = get_object_or_404(StandardStrengthProgram.objects.filter(owner=request.user), id=program_id)
    program.delete()
    return redirect("standard_strength_list")


@login_required
@require_GET
def standard_strength_detail_view(request, program_id: int):
    program = get_object_or_404(
        StandardStrengthProgram.objects.prefetch_related("exercises"),
        id=program_id,
    )
    if program.owner_id and program.owner_id != request.user.id and not request.user.is_staff:
        athlete = _athlete_for_user(request.user)
        allowed = False
        if athlete:
            for segment in program.segments.select_related("slot", "slot__plan", "slot__athlete").all()[:200]:
                slot = segment.slot
                if slot.athlete_id == athlete.id:
                    allowed = True
                    break
                try:
                    if slot.plan_id and athlete.id in slot.plan.targeted_athlete_ids():
                        allowed = True
                        break
                except Exception:
                    continue
        if not allowed:
            return HttpResponse("Not allowed", status=403)
    next_url = (request.GET.get("next") or "").strip()
    if not next_url.startswith("/"):
        next_url = reverse("planning_overview")
    return render(request, "core/standard_strength_detail.html", {
        "program": program,
        "next_url": next_url,
    })


def _race_calendar_redirect_for_year(year, view_mode="calendar", period_mode="full"):
    view_mode = "calendar" if view_mode == "calendar" else "list"
    allowed_periods = {"full", "outdoor", "indoor", "current_next"}
    period_mode = period_mode if period_mode in allowed_periods else "full"
    return redirect(f"/race-calendar/?year={year}&view={view_mode}&period={period_mode}")


def _race_distance_raw_value(distance):
    if distance.distance == "custom" and distance.custom_distance_m:
        return str(distance.custom_distance_m)
    return str(distance.distance or "")


def _race_distance_numeric_value(distance):
    raw = _race_distance_raw_value(distance)
    digits = ""
    for char in raw:
        if char.isdigit():
            digits += char
        elif digits:
            break

    try:
        return int(digits)
    except (TypeError, ValueError):
        return 0


def _race_distance_is_steeple(distance):
    return _race_distance_raw_value(distance).upper().endswith("S")


def _race_distance_sort_value(distance):
    meters = _race_distance_numeric_value(distance)
    if not meters:
        return 999999
    if _race_distance_is_steeple(distance):
        return 100000 + meters
    return meters


def _race_distance_m(distance):
    try:
        return _race_distance_numeric_value(distance)
    except (TypeError, ValueError):
        return 0


def _sorted_race_distances(race):
    return sorted(
        list(race.distances.all()),
        key=lambda distance: (_race_distance_sort_value(distance), distance.id),
    )


def _race_training_marker(distance_m):
    try:
        d = int(distance_m or 0)
    except (TypeError, ValueError):
        d = 0

    if d <= 200:
        return "Z6"
    if d <= 599:
        return "T4"
    if d <= 1000:
        return "T8"
    if d <= 2000:
        return "T15"
    if d <= 3500:
        return "T3"
    if d <= 6000:
        return "T5"
    if d <= 12000:
        return "T10"
    if d <= 25000:
        return "THM"
    return "TM"


def _race_training_zone_fallback(distance_m):
    try:
        d = int(distance_m or 0)
    except (TypeError, ValueError):
        d = 0

    if d <= 200:
        return "6"
    if d <= 599:
        return "5"
    if d <= 1000:
        return "5"
    if d <= 2000:
        return "5"
    if d <= 3500:
        return "4"
    if d <= 6000:
        return "4"
    if d <= 12000:
        return "4"
    if d <= 25000:
        return "3"
    return "2"


def _race_selected_count(entry):
    if not entry:
        return 0

    coach_selected = bool(entry.coach_selected)
    athlete_selected = bool(getattr(entry, "athlete_selected", False))
    target_selected = bool(entry.target_selected)

    if target_selected:
        return 3
    if coach_selected or athlete_selected or target_selected:
        return 1
    return 0


def _race_line_text(race, distance, selected_count):
    distance_m = _race_distance_m(distance)
    marker = _race_training_marker(distance_m)
    race_label = "Race!" if selected_count >= 3 else "Race"
    steeple = " S" if _race_distance_is_steeple(distance) else ""
    return f'"{race.name}" {distance_m}m{steeple} {marker} {race_label}'


def _plans_for_race_override(athlete, race):
    race_date = race.date

    plans = []
    for plan in TrainingPlan.objects.all().order_by("start_date", "id"):
        if plan.start_date and race_date < plan.start_date:
            continue
        if plan.end_date and race_date > plan.end_date:
            continue
        try:
            if athlete.id in plan.targeted_athlete_ids():
                plans.append(plan)
        except Exception:
            continue

    flex_plan = _race_flex_planner_plan(getattr(race, "owner", None), race_date)
    if flex_plan and flex_plan not in plans:
        plans.append(flex_plan)

    return plans


def _race_flex_planner_plan(user, race_date):
    if not user:
        return None

    user_id = getattr(user, "id", None) or getattr(user, "pk", None) or "unknown"
    name = f"Flex Planner {user_id}"
    plan = TrainingPlan.objects.filter(owner=user, name__startswith="Flex Planner").order_by("id").first()
    if not plan:
        plan = TrainingPlan.objects.create(
            owner=user,
            name=name,
            is_private=True,
            week_phases_enabled=True,
            start_date=race_date,
            end_date=race_date,
        )
    else:
        changed = []
        if not plan.start_date or plan.start_date > race_date:
            plan.start_date = race_date
            changed.append("start_date")
        if not plan.end_date or plan.end_date < race_date:
            plan.end_date = race_date
            changed.append("end_date")
        if changed:
            plan.save(update_fields=changed)
    return plan


def _invalidate_race_training_stats_cache():
    try:
        cache.incr(STATS_VERSION_KEY)
    except Exception:
        cache.set(STATS_VERSION_KEY, 1, None)


def _is_generated_race_or_wucd_segment(seg):
    if seg.type in ("WU", "CD"):
        return True
    return (seg.special or "") in ("RACE", "IMPORTANT_RACE")


def _sync_race_training_override(athlete, race):
    plans = _plans_for_race_override(athlete, race)
    if not plans:
        return

    entries = list(
        RaceEntry.objects
        .filter(
            athlete=athlete,
            race_distance__race__date=race.date,
        )
        .select_related("race_distance", "race_distance__race")
        .order_by("race_distance__race__name", "race_distance__id")
    )

    selected_entries = [entry for entry in entries if _race_selected_count(entry) > 0]

    changed = False

    for plan in plans:
        existing_slot = TrainingSlot.objects.filter(
            plan=plan,
            athlete=athlete,
            date=race.date,
            slot_index=2,
        ).prefetch_related("segments").first()

        if not selected_entries:
            if existing_slot:
                existing_segments = list(existing_slot.segments.all())
                if existing_segments and all(_is_generated_race_or_wucd_segment(seg) for seg in existing_segments):
                    existing_slot.delete()
                    changed = True
            continue

        slot, _ = TrainingSlot.objects.update_or_create(
            plan=plan,
            athlete=athlete,
            date=race.date,
            slot_index=2,
            defaults={},
        )
        slot.segments.all().delete()

        auto_wu_text, auto_cd_text = auto_wucd_texts_for_target(athlete=athlete, plan=plan)
        if auto_wu_text:
            create_parsed_wucd_segment(slot, "WU", auto_wu_text, 0)

        for order, entry in enumerate(selected_entries, start=1):
            distance = entry.race_distance
            selected_count = _race_selected_count(entry)
            text = _race_line_text(distance.race, distance, selected_count)
            parsed = parse_segment_text(text, zone_required=False)

            segment = slot.segments.create(
                order=order,
                type="CORE",
                text=text,
                zone=str(parsed.zone or _race_training_zone_fallback(_race_distance_m(distance))),
                special=(parsed.special or ("IMPORTANT_RACE" if selected_count >= 3 else "RACE")),
                t_type=(parsed.t_type or ""),
                reps=int(parsed.reps or 1),
                distance_m=parsed.rep_distance_m or parsed.distance_m or _race_distance_m(distance),
                duration_s=parsed.duration_s,
                norm_distance_m=parsed.distance_m or _race_distance_m(distance),
                parse_ok=bool(parsed.ok),
                parse_message=parsed.message or "",
            )
            segment.save()

        if auto_cd_text:
            create_parsed_wucd_segment(slot, "CD", auto_cd_text, len(selected_entries) + 1)
        changed = True

    if changed:
        _invalidate_race_training_stats_cache()


def _add_months(d, months):
    month_index = (d.month - 1) + int(months)
    year = d.year + (month_index // 12)
    month = (month_index % 12) + 1
    day = min(d.day, py_calendar.monthrange(year, month)[1])
    return date(year, month, day)


def _race_calendar_period_bounds(year, period_mode, today):
    if period_mode == "outdoor":
        start_date = date(year, 4, 1)
        end_date = date(year, 10, 31)
        label = f"Outdoor {year}"
        previous_year = year - 1
        next_year = year + 1
    elif period_mode == "indoor":
        start_date = date(year, 11, 1)
        end_date = date(year + 1, 3, 31)
        label = f"Indoor {year}/{str(year + 1)[-2:]}"
        previous_year = year - 1
        next_year = year + 1
    elif period_mode == "current_next":
        start_date = date(today.year, today.month, 1)
        next_month = _add_months(start_date, 1)
        after_next_month = _add_months(start_date, 2)
        end_date = after_next_month - timedelta(days=1)
        label = f"{start_date.strftime('%B %Y')} / {next_month.strftime('%B %Y')}"
        previous_year = year - 1
        next_year = year + 1
    else:
        start_date = date(year, 1, 1)
        end_date = date(year, 12, 31)
        label = f"Full year {year}"
        previous_year = year - 1
        next_year = year + 1

    return {
        "start_date": start_date,
        "end_date": end_date,
        "label": label,
        "previous_year": previous_year,
        "next_year": next_year,
    }


def _race_calendar_month_sequence(start_date, end_date):
    months = []
    current = date(start_date.year, start_date.month, 1)
    last = date(end_date.year, end_date.month, 1)

    while current <= last:
        months.append((current.year, current.month))
        current = _add_months(current, 1)

    return months


@login_required
@require_http_methods(["GET", "POST"])
def race_calendar_view(request):
    today = date.today()

    try:
        year = int(request.GET.get("year") or request.POST.get("year") or today.year)
    except ValueError:
        year = today.year

    if year < 2000 or year > 2100:
        year = today.year

    view_mode = (request.GET.get("view") or request.POST.get("view") or "calendar").strip().lower()
    if view_mode not in ("list", "calendar"):
        view_mode = "list"

    period_mode = (request.GET.get("period") or request.POST.get("period") or "full").strip().lower()
    allowed_periods = {"full", "outdoor", "indoor", "current_next"}
    if period_mode not in allowed_periods:
        period_mode = "full"

    period = _race_calendar_period_bounds(year, period_mode, today)
    start_date = period["start_date"]
    end_date = period["end_date"]

    errors = []

    if request.method == "POST":
        name = (request.POST.get("name") or "").strip()
        date_raw = (request.POST.get("date") or "").strip()

        if not name:
            errors.append("Name is required.")

        try:
            race_date = date.fromisoformat(date_raw)
        except Exception:
            race_date = None
            errors.append("Date is invalid.")

        if not errors and race_date:
            RaceEvent.objects.create(
                owner=request.user,
                name=name,
                date=race_date,
            )
            return _race_calendar_redirect_for_year(year, view_mode, period_mode)

    races = list(
        RaceEvent.objects
        .filter(owner=request.user, date__gte=start_date, date__lte=end_date)
        .prefetch_related("distances")
        .order_by("date", "name", "id")
    )
    race_rows = [
        {"race": race, "distances": _sorted_race_distances(race)}
        for race in races
    ]

    race_rows_by_id = {row["race"].id: row for row in race_rows}
    races_by_date = {}
    for row in race_rows:
        races_by_date.setdefault(row["race"].date, []).append(row)

    month_rows = []
    cal = py_calendar.Calendar(firstweekday=0)
    month_names = [
        "January", "February", "March", "April", "May", "June",
        "July", "August", "September", "October", "November", "December",
    ]

    for month_year, month in _race_calendar_month_sequence(start_date, end_date):
        weeks = []
        for week in cal.monthdatescalendar(month_year, month):
            weeks.append([
                {
                    "day": day,
                    "in_month": day.month == month,
                    "races": races_by_date.get(day, []),
                }
                for day in week
            ])
        month_rows.append({
            "year": month_year,
            "month": month,
            "name": f"{month_names[month - 1]} {month_year}",
            "weeks": weeks,
        })

    period_options = [
        {"key": "current_next", "label": "Current / next month", "year": today.year},
        {"key": "outdoor", "label": f"Outdoor {year}", "year": year},
        {"key": "indoor", "label": f"Indoor {year}/{str(year + 1)[-2:]}", "year": year},
        {"key": "full", "label": f"Full year {year}", "year": year},
    ]

    return render(request, "core/race_calendar.html", {
        "year": year,
        "previous_year": period["previous_year"],
        "next_year": period["next_year"],
        "view_mode": view_mode,
        "period_mode": period_mode,
        "period_label": period["label"],
        "period_options": period_options,
        "race_rows": race_rows,
        "race_rows_by_id": race_rows_by_id,
        "month_rows": month_rows,
        "distance_choices": RaceEventDistance.DISTANCE_CHOICES,
        "errors": errors,
        "today": today,
    })



@login_required
@require_http_methods(["POST"])
def race_calendar_delete_view(request, race_id: int):
    race = get_object_or_404(RaceEvent.objects.filter(owner=request.user), id=race_id)
    year = race.date.year
    view_mode = (request.POST.get("view") or request.GET.get("view") or "list").strip().lower()
    period_mode = (request.POST.get("period") or request.GET.get("period") or "full").strip().lower()
    race.delete()
    return _race_calendar_redirect_for_year(year, view_mode, period_mode)


@login_required
@require_http_methods(["POST"])
def race_calendar_distance_add_view(request, race_id: int):
    race = get_object_or_404(RaceEvent.objects.filter(owner=request.user), id=race_id)
    selected_distances = request.POST.getlist("distances")
    remove_distance_ids = request.POST.getlist("remove_distances")
    custom_raw = (request.POST.get("custom_distance_m") or "").strip()
    allowed = {value for value, _ in RaceEventDistance.DISTANCE_CHOICES}

    if remove_distance_ids:
        RaceEventDistance.objects.filter(race=race, id__in=remove_distance_ids).delete()

    for distance in selected_distances:
        distance = (distance or "").strip()
        if not distance or distance == "custom" or distance not in allowed:
            continue

        RaceEventDistance.objects.get_or_create(
            race=race,
            distance=distance,
            custom_distance_m=None,
        )

    if custom_raw:
        try:
            custom_distance_m = int(custom_raw)
        except ValueError:
            custom_distance_m = None

        if custom_distance_m and custom_distance_m > 0:
            RaceEventDistance.objects.get_or_create(
                race=race,
                distance="custom",
                custom_distance_m=custom_distance_m,
            )

    view_mode = (request.POST.get("view") or request.GET.get("view") or "list").strip().lower()
    period_mode = (request.POST.get("period") or request.GET.get("period") or "full").strip().lower()
    return _race_calendar_redirect_for_year(race.date.year, view_mode, period_mode)


@login_required
@require_http_methods(["POST"])
def race_calendar_distance_delete_view(request, race_id: int, distance_id: int):
    race = get_object_or_404(RaceEvent.objects.filter(owner=request.user), id=race_id)
    distance = get_object_or_404(RaceEventDistance.objects.filter(race=race), id=distance_id)
    view_mode = (request.POST.get("view") or request.GET.get("view") or "list").strip().lower()
    period_mode = (request.POST.get("period") or request.GET.get("period") or "full").strip().lower()
    distance.delete()
    return _race_calendar_redirect_for_year(race.date.year, view_mode, period_mode)


@login_required
@require_http_methods(["GET", "POST"])
def race_select_view(request):
    today = date.today()

    try:
        year = int(request.GET.get("year") or request.POST.get("year") or today.year)
    except ValueError:
        year = today.year

    if year < 2000 or year > 2100:
        year = today.year

    view_mode = (request.GET.get("view") or request.POST.get("view") or "calendar").strip().lower()
    if view_mode not in ("list", "calendar"):
        view_mode = "list"

    period_mode = (request.GET.get("period") or request.POST.get("period") or "full").strip().lower()
    allowed_periods = {"full", "outdoor", "indoor", "current_next"}
    if period_mode not in allowed_periods:
        period_mode = "full"

    current_athlete = _athlete_for_user(request.user)
    is_athlete_user = bool(current_athlete and not request.user.is_staff and not request.user.is_superuser)
    data_owner = request.user

    race_owner_ids = []
    if is_athlete_user:
        owner_ids = set()

        if getattr(current_athlete, "owner_id", None):
            owner_ids.add(current_athlete.owner_id)

        for plan in TrainingPlan.objects.order_by("id"):
            try:
                if current_athlete.id in plan.targeted_athlete_ids():
                    owner_id = getattr(plan, "owner_id", None)
                    if owner_id:
                        owner_ids.add(owner_id)
            except Exception:
                continue

        for group in Group.objects.filter(athletes=current_athlete):
            owner_id = getattr(group, "owner_id", None)
            if owner_id:
                owner_ids.add(owner_id)

        race_owner_ids = sorted(owner_ids)
    else:
        race_owner_ids = [request.user.id]

    scope_mode = (request.GET.get("scope") or request.POST.get("scope") or "group").strip().lower()
    if scope_mode not in ("group", "athlete"):
        scope_mode = "group"
    if is_athlete_user:
        scope_mode = "athlete"

    period = _race_calendar_period_bounds(year, period_mode, today)
    start_date = period["start_date"]
    end_date = period["end_date"]

    if is_athlete_user:
        groups = []
        all_athletes = [current_athlete]
    else:
        groups = list(_filter_owned(Group.objects.prefetch_related("athletes").order_by("name"), data_owner))
        all_athletes = list(_filter_owned(Athlete.objects.order_by("name"), data_owner))

    selected_group_id = (request.GET.get("group") or request.POST.get("group") or "").strip()
    selected_athlete_id = (request.GET.get("athlete") or request.POST.get("athlete") or "").strip()
    if is_athlete_user:
        selected_group_id = ""
        selected_athlete_id = str(current_athlete.id)

    selected_group = None
    if selected_group_id:
        try:
            selected_group = next((g for g in groups if g.id == int(selected_group_id)), None)
        except ValueError:
            selected_group = None

    if selected_group is None and groups:
        selected_group = groups[0]
        selected_group_id = str(selected_group.id)

    selected_athlete = None
    if selected_athlete_id:
        try:
            selected_athlete = next((a for a in all_athletes if a.id == int(selected_athlete_id)), None)
        except ValueError:
            selected_athlete = None

    if selected_athlete is None and all_athletes:
        selected_athlete = all_athletes[0]
        selected_athlete_id = str(selected_athlete.id)

    if scope_mode == "athlete":
        athletes = [selected_athlete] if selected_athlete else []
    elif selected_group:
        athletes = list(selected_group.athletes.order_by("name"))
    else:
        athletes = []

    races = list(
        RaceEvent.objects
        .filter(owner_id__in=race_owner_ids, date__gte=start_date, date__lte=end_date)
        .prefetch_related("distances")
        .order_by("date", "name", "id")
    )

    race_distances = []
    distances_by_race_id = {}
    for race in races:
        distances = _sorted_race_distances(race)
        distances_by_race_id[race.id] = distances
        for distance in distances:
            race_distances.append(distance)

    if request.method == "POST":
        affected_race_athletes = set()
        existing_entries = {
            (entry.race_distance_id, entry.athlete_id): entry
            for entry in RaceEntry.objects.filter(
                race_distance__in=race_distances,
                athlete__in=athletes,
            )
        }

        with transaction.atomic():
            for athlete in athletes:
                for race in races:
                    distances = distances_by_race_id.get(race.id, [])
                    allowed_distance_ids = {str(distance.id) for distance in distances}
                    coach_selected_ids = {
                        value for value in request.POST.getlist(f"coach_distances_{race.id}_{athlete.id}")
                        if value in allowed_distance_ids
                    }
                    target_selected_ids = {
                        value for value in request.POST.getlist(f"target_distances_{race.id}_{athlete.id}")
                        if value in allowed_distance_ids
                    }
                    posted_selected_id_set = set(list(coach_selected_ids | target_selected_ids)[:3])

                    for distance in distances:
                        distance_id = str(distance.id)
                        existing_entry = existing_entries.get((distance.id, athlete.id))

                        coach_selected = distance_id in coach_selected_ids and distance_id in posted_selected_id_set
                        target_selected = distance_id in target_selected_ids and distance_id in posted_selected_id_set
                        athlete_selected = False

                        new_state = (coach_selected, athlete_selected, target_selected)
                        old_state = (
                            bool(existing_entry and existing_entry.coach_selected),
                            bool(existing_entry and existing_entry.athlete_selected),
                            bool(existing_entry and existing_entry.target_selected),
                        )
                        if new_state == old_state:
                            continue

                        affected_race_athletes.add((athlete.id, race.id))

                        if not coach_selected and not athlete_selected and not target_selected:
                            if existing_entry:
                                existing_entry.delete()
                            continue

                        if existing_entry:
                            existing_entry.coach_selected = coach_selected
                            existing_entry.athlete_selected = athlete_selected
                            existing_entry.target_selected = target_selected
                            existing_entry.save(update_fields=["coach_selected", "athlete_selected", "target_selected", "updated_at"])
                        else:
                            RaceEntry.objects.create(
                                race_distance=distance,
                                athlete=athlete,
                                coach_selected=coach_selected,
                                athlete_selected=athlete_selected,
                                target_selected=target_selected,
                            )

        athlete_by_id = {athlete.id: athlete for athlete in athletes}
        race_by_id = {race.id: race for race in races}
        for athlete_id, race_id in affected_race_athletes:
            athlete_obj = athlete_by_id.get(athlete_id)
            race_obj = race_by_id.get(race_id)
            if athlete_obj and race_obj:
                _sync_race_training_override(athlete_obj, race_obj)

        if scope_mode == "athlete":
            return redirect(f"/race-select/?year={year}&view={view_mode}&period={period_mode}&scope=athlete&athlete={selected_athlete_id}")
        return redirect(f"/race-select/?year={year}&view={view_mode}&period={period_mode}&scope=group&group={selected_group_id}")

    entries = {
        (entry.race_distance_id, entry.athlete_id): entry
        for entry in RaceEntry.objects.filter(
            race_distance__in=race_distances,
            athlete__in=athletes,
        )
    }

    rows = []
    races_by_date = {}

    for race in races:
        distances = distances_by_race_id.get(race.id, [])
        cells = []

        for athlete in athletes:
            distance_cells = []
            for distance in distances:
                entry = entries.get((distance.id, athlete.id))
                distance_cells.append({
                    "distance": distance,
                    "coach_selected": bool(entry and (entry.coach_selected or getattr(entry, "athlete_selected", False))),
                    "athlete_selected": bool(entry and getattr(entry, "athlete_selected", False)),
                    "target_selected": bool(entry and entry.target_selected),
                })

            cells.append({
                "athlete": athlete,
                "distance_cells": distance_cells,
            })

        row = {
            "race": race,
            "distances": distances,
            "cells": cells,
        }
        rows.append(row)
        races_by_date.setdefault(race.date, []).append(row)

    month_rows = []
    cal = py_calendar.Calendar(firstweekday=0)
    month_names = [
        "January", "February", "March", "April", "May", "June",
        "July", "August", "September", "October", "November", "December",
    ]

    for month_year, month in _race_calendar_month_sequence(start_date, end_date):
        weeks = []
        for week in cal.monthdatescalendar(month_year, month):
            weeks.append([
                {
                    "day": day,
                    "in_month": day.month == month,
                    "races": races_by_date.get(day, []),
                }
                for day in week
            ])
        month_rows.append({
            "year": month_year,
            "month": month,
            "name": f"{month_names[month - 1]} {month_year}",
            "weeks": weeks,
        })

    period_options = [
        {"key": "current_next", "label": "Current / next month", "year": today.year},
        {"key": "outdoor", "label": f"Outdoor {year}", "year": year},
        {"key": "indoor", "label": f"Indoor {year}/{str(year + 1)[-2:]}", "year": year},
        {"key": "full", "label": f"Full year {year}", "year": year},
    ]

    query_base = f"year={year}&view={view_mode}&period={period_mode}&scope={scope_mode}"
    if scope_mode == "athlete":
        query_base += f"&athlete={selected_athlete_id}"
    else:
        query_base += f"&group={selected_group_id}"

    all_period_races_count = RaceEvent.objects.filter(date__gte=start_date, date__lte=end_date).count()
    race_select_debug = {
        "user": getattr(request.user, "username", ""),
        "athlete": getattr(current_athlete, "name", "") if current_athlete else "",
        "athlete_id": getattr(current_athlete, "id", "") if current_athlete else "",
        "athlete_owner_id": getattr(current_athlete, "owner_id", "") if current_athlete else "",
        "race_owner_ids": race_owner_ids,
        "period": f"{start_date} – {end_date}",
        "athletes_count": len(athletes),
        "races_count": len(races),
        "race_distances_count": len(race_distances),
        "all_period_races_count": all_period_races_count,
    }

    return render(request, "core/race_select.html", {
        "year": year,
        "previous_year": period["previous_year"],
        "next_year": period["next_year"],
        "view_mode": view_mode,
        "period_mode": period_mode,
        "period_label": period["label"],
        "period_options": period_options,
        "scope_mode": scope_mode,
        "query_base": query_base,
        "groups": groups,
        "selected_group": selected_group,
        "selected_group_id": selected_group_id,
        "all_athletes": all_athletes,
        "selected_athlete": selected_athlete,
        "selected_athlete_id": selected_athlete_id,
        "athletes": athletes,
        "rows": rows,
        "month_rows": month_rows,
        "is_athlete_user": is_athlete_user,
        "current_athlete": current_athlete,
        "race_select_debug": race_select_debug,
    })


# -----------------------------
# Settings (persistent per coach)
# -----------------------------
@login_required
@require_http_methods(["GET", "POST"])
def settings_view(request):
    coach_settings, _ = CoachSettings.objects.get_or_create(user=request.user)

    if request.method == "POST":
        coach_settings.show_all_zones = (request.POST.get("show_all_zones") == "on")
        coach_settings.highlight_current_week = (request.POST.get("highlight_current_week") == "on")
        coach_settings.calendar_show_only_core = (request.POST.get("calendar_show_only_core") == "on")

        # ✅ NEW: Weekcolors Y/N
        coach_settings.weekcolors_enabled = (request.POST.get("weekcolors_enabled") == "on")

        unit = (request.POST.get("zone_input_unit") or "").strip().lower()
        if unit in ("pace", "kmh"):
            coach_settings.zone_input_unit = unit

        coach_settings.tb_show_wu = (request.POST.get("tb_show_wu") == "on")
        coach_settings.tb_show_mob = (request.POST.get("tb_show_mob") == "on")
        coach_settings.tb_show_sprint = (request.POST.get("tb_show_sprint") == "on")
        coach_settings.tb_show_core2 = (request.POST.get("tb_show_core2") == "on")
        coach_settings.tb_show_cd = (request.POST.get("tb_show_cd") == "on")

        coach_settings.save()

        # Sync to session
        request.session["show_all_zones"] = coach_settings.show_all_zones
        request.session["highlight_current_week"] = coach_settings.highlight_current_week
        request.session["calendar_show_only_core"] = coach_settings.calendar_show_only_core
        request.session["zone_input_unit"] = coach_settings.zone_input_unit

        # ✅ NEW: Weekcolors Y/N
        request.session["weekcolors_enabled"] = coach_settings.weekcolors_enabled

        request.session["tb_show_wu"] = coach_settings.tb_show_wu
        request.session["tb_show_mob"] = coach_settings.tb_show_mob
        request.session["tb_show_sprint"] = coach_settings.tb_show_sprint
        request.session["tb_show_core2"] = coach_settings.tb_show_core2
        request.session["tb_show_cd"] = coach_settings.tb_show_cd

        request.session.modified = True
        return redirect("/settings/")

    ctx = {
        "show_all_zones": coach_settings.show_all_zones,
        "highlight_current_week": coach_settings.highlight_current_week,
        "calendar_show_only_core": coach_settings.calendar_show_only_core,

        # ✅ NEW: Weekcolors Y/N
        "weekcolors_enabled": getattr(coach_settings, "weekcolors_enabled", True),

        "zone_input_unit": coach_settings.zone_input_unit or "pace",

        "tb_show_wu": coach_settings.tb_show_wu,
        "tb_show_mob": coach_settings.tb_show_mob,
        "tb_show_sprint": coach_settings.tb_show_sprint,
        "tb_show_core2": coach_settings.tb_show_core2,
        "tb_show_cd": coach_settings.tb_show_cd,
    }

    # Sync to session
    request.session["show_all_zones"] = ctx["show_all_zones"]
    request.session["highlight_current_week"] = ctx["highlight_current_week"]
    request.session["calendar_show_only_core"] = ctx["calendar_show_only_core"]
    request.session["zone_input_unit"] = ctx["zone_input_unit"]

    # ✅ NEW: Weekcolors Y/N
    request.session["weekcolors_enabled"] = ctx["weekcolors_enabled"]

    request.session["tb_show_wu"] = ctx["tb_show_wu"]
    request.session["tb_show_mob"] = ctx["tb_show_mob"]
    request.session["tb_show_sprint"] = ctx["tb_show_sprint"]
    request.session["tb_show_core2"] = ctx["tb_show_core2"]
    request.session["tb_show_cd"] = ctx["tb_show_cd"]

    request.session.modified = True

    return render(request, "core/settings.html", ctx)


# -----------------------------
# Plans CRUD
# -----------------------------


def _exclude_flex_planner_plans(qs):
    return qs.exclude(name__startswith="Flex Planner")


def _exclude_non_legacy_plans(qs):
    return _exclude_flex_planner_plans(qs).exclude(plan_kind=TrainingPlan.PLAN_KIND_TRAINER)


@login_required
@require_GET
def coach_plans_view(request):
    sort = request.GET.get("sort", "name")
    if sort == "start":
        qs = TrainingPlan.objects.order_by("start_date")
    elif sort == "end":
        qs = TrainingPlan.objects.order_by("end_date")
    else:
        qs = TrainingPlan.objects.order_by(Lower("name"))

    plans = _exclude_non_legacy_plans(_filter_owned(qs, request.user))
    return render(request, "core/coach_plans.html", {"plans": plans})


@login_required
@require_http_methods(["GET", "POST"])
def coach_plan_create_view(request):
    errors = []
    form = {
        "name": "",
        "start_date": "",
        "end_date": "",
        "week_phases_enabled": True,
        "copy_source_plan_id": "",
        "is_private": False,
    }
    source_sort = request.GET.get("sort", "name")
    if source_sort == "start":
        qs = TrainingPlan.objects.order_by("start_date")
    elif source_sort == "end":
        qs = TrainingPlan.objects.order_by("end_date")
    else:
        qs = TrainingPlan.objects.order_by("name")

    plans = _exclude_non_legacy_plans(_filter_owned(qs, request.user))

    if request.method == "POST":
        form["name"] = (request.POST.get("name") or "").strip()
        form["start_date"] = (request.POST.get("start_date") or "").strip()
        form["end_date"] = (request.POST.get("end_date") or "").strip()
        form["copy_source_plan_id"] = (request.POST.get("copy_source_plan_id") or "").strip()

        # ✅ NEW: plan setting
        form["week_phases_enabled"] = (request.POST.get("week_phases_enabled") == "on")
        form["is_private"] = (request.POST.get("is_private") == "on")

        if not form["name"]:
            errors.append("Name is required.")

        try:
            start_d = _parse_iso_date(form["start_date"])
        except ValueError:
            start_d = None
            errors.append("Start date is invalid (use YYYY-MM-DD).")

        try:
            end_d = _parse_iso_date(form["end_date"])
        except ValueError:
            end_d = None
            errors.append("End date is invalid (use YYYY-MM-DD).")

        if (start_d and not end_d) or (end_d and not start_d):
            errors.append("Enter either both dates or neither date (start + end).")

        if start_d and end_d and start_d > end_d:
            errors.append("Startdatum mag niet na einddatum liggen.")

        source_plan = None
        if form["copy_source_plan_id"]:
            try:
                source_plan_id = int(form["copy_source_plan_id"])
            except ValueError:
                source_plan_id = None
                errors.append("Source plan is invalid.")
            if source_plan_id is not None:
                source_plan = _exclude_non_legacy_plans(_filter_owned(TrainingPlan.objects.all(), request.user)).filter(id=source_plan_id).first()
                if not source_plan:
                    errors.append("Source plan was not found.")
                elif not start_d or not end_d or not source_plan.start_date or not source_plan.end_date:
                    errors.append("Copying a plan is only possible when both the new plan and the source plan have a start and end date.")

        if not errors:
            new_plan = TrainingPlan.objects.create(
                owner=request.user,
                name=form["name"],
                start_date=start_d,
                end_date=end_d,
                week_phases_enabled=form["week_phases_enabled"],
                is_private=form["is_private"],
            )
            if source_plan:
                _copy_plan_contents(source_plan, new_plan)
            return redirect("coach_plans")

    return render(
        request,
        "core/coach_plan_form.html",
        {"mode": "create", "plan": None, "form": form, "errors": errors, "source_plans": plans},
    )


@login_required
@require_http_methods(["GET", "POST"])
def coach_plan_edit_view(request, plan_id: int):
    plan = get_object_or_404(_exclude_non_legacy_plans(_filter_owned(TrainingPlan.objects.all(), request.user)), id=plan_id)

    errors = []
    form = {
        "name": plan.name or "",
        "start_date": plan.start_date.isoformat() if plan.start_date else "",
        "end_date": plan.end_date.isoformat() if plan.end_date else "",
        # ✅ NEW: plan setting (prefill)
        "week_phases_enabled": getattr(plan, "week_phases_enabled", True),
        "is_private": getattr(plan, "is_private", False),
    }

    if request.method == "POST":
        form["name"] = (request.POST.get("name") or "").strip()
        form["start_date"] = (request.POST.get("start_date") or "").strip()
        form["end_date"] = (request.POST.get("end_date") or "").strip()

        # ✅ NEW: plan setting
        form["week_phases_enabled"] = (request.POST.get("week_phases_enabled") == "on")
        form["is_private"] = (request.POST.get("is_private") == "on")

        if not form["name"]:
            errors.append("Name is required.")

        try:
            start_d = _parse_iso_date(form["start_date"])
        except ValueError:
            start_d = None
            errors.append("Start date is invalid (use YYYY-MM-DD).")

        try:
            end_d = _parse_iso_date(form["end_date"])
        except ValueError:
            end_d = None
            errors.append("End date is invalid (use YYYY-MM-DD).")

        if (start_d and not end_d) or (end_d and not start_d):
            errors.append("Enter either both dates or neither date (start + end).")

        if start_d and end_d and start_d > end_d:
            errors.append("Startdatum mag niet na einddatum liggen.")

        if not errors:
            plan.name = form["name"]
            plan.start_date = start_d
            plan.end_date = end_d

            # ✅ NEW: plan setting save
            plan.week_phases_enabled = form["week_phases_enabled"]
            plan.is_private = form["is_private"]

            plan.save()
            return redirect("coach_plans")

    return render(
        request,
        "core/coach_plan_form.html",
        {"mode": "edit", "plan": plan, "form": form, "errors": errors},
    )



# -----------------------------
# Plans DELETE
# -----------------------------
@login_required
@require_http_methods(["POST"])
def coach_plan_delete_view(request, plan_id: int):
    plan = get_object_or_404(_exclude_non_legacy_plans(_filter_owned(TrainingPlan.objects.all(), request.user)), id=plan_id)

    if plan.targeted_athlete_ids():
        return HttpResponse(
            f'<script>alert("Pls remove athletes from plan first."); window.location.href = "{reverse("coach_plans")}";</script>'
        )

    plan.delete()
    return redirect("coach_plans")

# -----------------------------
# Athletes CRUD (zones)
# -----------------------------
@login_required
@require_GET
def coach_athletes_view(request):
    athletes = list(_filter_owned(Athlete.objects.order_by("name"), request.user))
    current_year = date.today().year
    for athlete in athletes:
        try:
            athlete.age = current_year - int(athlete.birth_year)
        except (TypeError, ValueError):
            athlete.age = None
    return render(request, "core/coach_athletes.html", {"athletes": athletes})


@login_required
@require_http_methods(["GET", "POST"])
def coach_athlete_create_view(request):
    unit = request.session.get("zone_input_unit", "pace")
    unit_label = zone_unit_label(unit)

    errors = []
    zones_form = zones_form_from_speeds(unit, dict(DEFAULT_ZONE_SPEED_MPS))

    form = {
        "name": "",
        "birth_year": "",
        "gender": "",
        "vdot": "",
        "zone_method": "manual",
        "pr_800": "",
        "pr_1500": "",
        "pr_3000": "",
        "pr_5000": "",
        "pr_10000": "",
        "tm": "",
        "thm": "",
        "t4": "",
        "target_pr_800": "",
        "target_pr_1500": "",
        "target_pr_3000": "",
        "target_pr_5000": "",
        "target_pr_10000": "",
        "target_tm": "",
        "target_thm": "",
        "target_t4": "",
        "is_private": False,
        "view_weeks_ahead": 2,
        "training_reports_enabled": True,
        "week_report_enabled": False,
        "daily_vitals_enabled": False,
        "auto_wucd_enabled": False,
        "auto_wu_m": 0,
        "auto_cd_m": 0,
        "zone_input_unit": unit,
        "zone_input_unit_label": unit_label,
        **zones_form,
    }

    if request.method == "POST":
        if (request.POST.get("action") or "").strip() == "save_wucd":
            athlete.auto_wucd_enabled = request.POST.get("auto_wucd_enabled") == "on"
            athlete.auto_wu_m = _clean_non_negative_int(request.POST.get("auto_wu_m"))
            athlete.auto_cd_m = _clean_non_negative_int(request.POST.get("auto_cd_m"))
            athlete.save(update_fields=["auto_wucd_enabled", "auto_wu_m", "auto_cd_m"])
            form["auto_wucd_enabled"] = athlete.auto_wucd_enabled
            form["auto_wu_m"] = athlete.auto_wu_m
            form["auto_cd_m"] = athlete.auto_cd_m
            saved_notice = "WU settings saved."
            return render(
                request,
                "core/coach_athlete_form.html",
                {"mode": "edit", "athlete": athlete, "form": form, "errors": errors, "saved_notice": saved_notice, "active_tab": "wu-settings"},
            )

        form["name"] = (request.POST.get("name") or "").strip()
        form["birth_year"] = (request.POST.get("birth_year") or "").strip()
        form["gender"] = (request.POST.get("gender") or "").strip()
        form["vdot"] = (request.POST.get("vdot") or "").strip()
        form["zone_method"] = (request.POST.get("zone_method") or "").strip() or "manual"
        form["pr_800"] = (request.POST.get("pr_800") or "").strip()
        form["pr_1500"] = (request.POST.get("pr_1500") or "").strip()
        form["pr_3000"] = (request.POST.get("pr_3000") or "").strip()
        form["pr_5000"] = (request.POST.get("pr_5000") or "").strip()
        form["pr_10000"] = (request.POST.get("pr_10000") or "").strip()
        form["tm"] = (request.POST.get("tm") or "").strip()
        form["thm"] = (request.POST.get("thm") or "").strip()
        form["t4"] = (request.POST.get("t4") or "").strip()
        form["target_pr_800"] = (request.POST.get("target_pr_800") or "").strip()
        form["target_pr_1500"] = (request.POST.get("target_pr_1500") or "").strip()
        form["target_pr_3000"] = (request.POST.get("target_pr_3000") or "").strip()
        form["target_pr_5000"] = (request.POST.get("target_pr_5000") or "").strip()
        form["target_pr_10000"] = (request.POST.get("target_pr_10000") or "").strip()
        form["target_tm"] = (request.POST.get("target_tm") or "").strip()
        form["target_thm"] = (request.POST.get("target_thm") or "").strip()
        form["target_t4"] = (request.POST.get("target_t4") or "").strip()
        form["is_private"] = (request.POST.get("is_private") == "on")
        form["view_weeks_ahead"] = (request.POST.get("view_weeks_ahead") or "2").strip()
        form["training_reports_enabled"] = (request.POST.get("training_reports_enabled") == "on")
        form["week_report_enabled"] = (request.POST.get("week_report_enabled") == "on")
        form["daily_vitals_enabled"] = (request.POST.get("daily_vitals_enabled") == "on")
        form["auto_wucd_enabled"] = (request.POST.get("auto_wucd_enabled") == "on")
        form["auto_wu_m"] = (request.POST.get("auto_wu_m") or "0").strip()
        form["auto_cd_m"] = (request.POST.get("auto_cd_m") or "0").strip()

        for z in ("1", "2", "3", "4", "5"):
            form[f"z{z}_pace"] = (request.POST.get(f"z{z}_pace") or "").strip()

        if not form["name"]:
            errors.append("Name is required.")

        try:
            birth_year = _parse_int(form["birth_year"])
        except ValueError:
            birth_year = None
            errors.append("Birth year is invalid (use a number).")
        if birth_year is None:
            errors.append("Birth year is required.")
        elif birth_year < 1900 or birth_year > 2100:
            errors.append("Birth year does not look valid.")

        gender = (form["gender"] or "").strip().upper()
        if gender not in ("M", "V", "X"):
            errors.append("Gender is required and must be M, V, or X.")

        try:
            vdot = _parse_float(form["vdot"])
            if vdot is not None and vdot < 0:
                errors.append("VDOT kan niet negatief zijn.")
        except ValueError:
            vdot = None
            errors.append("VDOT is invalid (use a number).")

        try:
            view_weeks_ahead = int(form["view_weeks_ahead"])
            if view_weeks_ahead < 0:
                errors.append("Weeks ahead cannot be negative.")
        except ValueError:
            view_weeks_ahead = 2
            errors.append("Weeks ahead is invalid (use a number).")

        auto_wu_m = _clean_non_negative_int(form["auto_wu_m"])
        auto_cd_m = _clean_non_negative_int(form["auto_cd_m"])

        try:
            pr_800_s = _parse_pr_time_to_seconds(form["pr_800"])
        except ValueError:
            pr_800_s = None
            errors.append("T800 is required and must use format m:ss(.ms), h:mm:ss(.ms), or mm.ss.ms.")

        try:
            pr_1500_s = _parse_pr_time_to_seconds(form["pr_1500"])
        except ValueError:
            pr_1500_s = None
            errors.append("T1500 is required and must use format m:ss(.ms), h:mm:ss(.ms), or mm.ss.ms.")

        try:
            pr_3000_s = _parse_pr_time_to_seconds(form["pr_3000"])
        except ValueError:
            pr_3000_s = None
            errors.append("T3000 is required and must use format m:ss(.ms), h:mm:ss(.ms), or mm.ss.ms.")

        try:
            pr_5000_s = _parse_pr_time_to_seconds(form["pr_5000"])
        except ValueError:
            pr_5000_s = None
            errors.append("T5000 is required and must use format m:ss(.ms), h:mm:ss(.ms), or mm.ss.ms.")

        try:
            pr_10000_s = _parse_pr_time_to_seconds(form["pr_10000"])
        except ValueError:
            pr_10000_s = None
            errors.append("T10000 is required and must use format m:ss(.ms), h:mm:ss(.ms), or mm.ss.ms.")

        try:
            tm_s = _parse_pr_time_to_seconds(form["tm"]) if form["tm"] else None
        except ValueError:
            tm_s = None
            errors.append("TM invalid format.")

        try:
            thm_s = _parse_pr_time_to_seconds(form["thm"]) if form["thm"] else None
        except ValueError:
            thm_s = None
            errors.append("THM invalid format.")

        try:
            t4_s = _parse_pr_time_to_seconds(form["t4"]) if form["t4"] else None
        except ValueError:
            t4_s = None
            errors.append("T4 invalid format.")

        target_pr_800_s, target_pr_1500_s, target_pr_3000_s = None, None, None
        target_pr_5000_s, target_pr_10000_s, target_tm_s = None, None, None
        target_thm_s, target_t4_s = None, None
        for key, label in (
            ("target_pr_800", "Goal T800"),
            ("target_pr_1500", "Goal T1500"),
            ("target_pr_3000", "Goal T3000"),
            ("target_pr_5000", "Goal T5000"),
            ("target_pr_10000", "Goal T10000"),
            ("target_tm", "Goal TM"),
            ("target_thm", "Goal THM"),
            ("target_t4", "Goal T4"),
        ):
            try:
                value = _parse_pr_time_to_seconds(form[key]) if form[key] else None
            except ValueError:
                value = None
                errors.append(f"{label} invalid format.")
            if key == "target_pr_800":
                target_pr_800_s = value
            elif key == "target_pr_1500":
                target_pr_1500_s = value
            elif key == "target_pr_3000":
                target_pr_3000_s = value
            elif key == "target_pr_5000":
                target_pr_5000_s = value
            elif key == "target_pr_10000":
                target_pr_10000_s = value
            elif key == "target_tm":
                target_tm_s = value
            elif key == "target_thm":
                target_thm_s = value
            elif key == "target_t4":
                target_t4_s = value

        if form["zone_method"] != "manual":
            errors.append("Zone method is not supported yet. Choose 'manual' for now.")

        zone_speed_mps, z_errors, normalized_input, other_under = parse_manual_zones_required(
            request.POST, unit=unit
        )
        errors.extend(z_errors)

        for z in ("1", "2", "3", "4", "5"):
            form[f"z{z}_pace"] = normalized_input.get(z, form[f"z{z}_pace"])
            form[f"z{z}_other"] = other_under.get(z, form.get(f"z{z}_other", "—"))

        if not errors:
            Athlete.objects.create(
                owner=request.user,
                name=form["name"],
                birth_year=int(birth_year),
                gender=gender,
                vdot=vdot,
                zone_method=form["zone_method"],
                zone_speed_mps=zone_speed_mps,
                view_weeks_ahead=view_weeks_ahead,
                training_reports_enabled=form["training_reports_enabled"],
                week_report_enabled=form["week_report_enabled"],
                daily_vitals_enabled=form["daily_vitals_enabled"],
                auto_wucd_enabled=form["auto_wucd_enabled"],
                auto_wu_m=auto_wu_m,
                auto_cd_m=auto_cd_m,
                pr_800_s=pr_800_s,
                pr_1500_s=pr_1500_s,
                pr_3000_s=pr_3000_s,
                pr_5000_s=pr_5000_s,
                pr_10000_s=pr_10000_s,
                pr_tm_s=tm_s,
                pr_thm_s=thm_s,
                pr_400_s=t4_s,
                target_pr_800_s=target_pr_800_s,
                target_pr_1500_s=target_pr_1500_s,
                target_pr_3000_s=target_pr_3000_s,
                target_pr_5000_s=target_pr_5000_s,
                target_pr_10000_s=target_pr_10000_s,
                target_pr_tm_s=target_tm_s,
                target_pr_thm_s=target_thm_s,
                target_pr_400_s=target_t4_s,
                is_private=form["is_private"],
            )
            return redirect("coach_athletes")

    return render(
        request,
        "core/coach_athlete_form.html",
        {"mode": "create", "athlete": None, "form": form, "errors": errors},
    )


@login_required
@require_http_methods(["GET", "POST"])
def coach_athlete_edit_view(request, athlete_id: int):
    athlete = get_object_or_404(_filter_owned(Athlete.objects.all(), request.user), id=athlete_id)
    unit = request.session.get("zone_input_unit", "pace")
    unit_label = zone_unit_label(unit)

    speeds = athlete.get_zone_speed_mps()
    zones_form = zones_form_from_speeds(unit, speeds)

    errors = []
    saved_notice = "Opgeslagen." if request.GET.get("saved") == "1" else None
    active_tab = (request.GET.get("tab") or "general").strip()
    if active_tab not in {"general", "zones", "base-planning", "wu-settings"}:
        active_tab = "general"

    form = {
        "name": athlete.name or "",
        "birth_year": str(athlete.birth_year) if athlete.birth_year else "",
        "gender": athlete.gender or "",
        "vdot": (str(athlete.vdot) if athlete.vdot is not None else ""),
        "zone_method": getattr(athlete, "zone_method", "manual") or "manual",
        "pr_800": _format_pr_seconds(getattr(athlete, "pr_800_s", None)),
        "pr_1500": _format_pr_seconds(getattr(athlete, "pr_1500_s", None)),
        "pr_3000": _format_pr_seconds(getattr(athlete, "pr_3000_s", None)),
        "pr_5000": _format_pr_seconds(getattr(athlete, "pr_5000_s", None)),
        "pr_10000": _format_pr_seconds(getattr(athlete, "pr_10000_s", None)),
        "tm": _format_pr_seconds(getattr(athlete, "pr_tm_s", None)),
        "thm": _format_pr_seconds(getattr(athlete, "pr_thm_s", None)),
        "t4": _format_pr_seconds(getattr(athlete, "pr_400_s", None)),
        "target_pr_800": _format_pr_seconds(getattr(athlete, "target_pr_800_s", None)),
        "target_pr_1500": _format_pr_seconds(getattr(athlete, "target_pr_1500_s", None)),
        "target_pr_3000": _format_pr_seconds(getattr(athlete, "target_pr_3000_s", None)),
        "target_pr_5000": _format_pr_seconds(getattr(athlete, "target_pr_5000_s", None)),
        "target_pr_10000": _format_pr_seconds(getattr(athlete, "target_pr_10000_s", None)),
        "target_tm": _format_pr_seconds(getattr(athlete, "target_pr_tm_s", None)),
        "target_thm": _format_pr_seconds(getattr(athlete, "target_pr_thm_s", None)),
        "target_t4": _format_pr_seconds(getattr(athlete, "target_pr_400_s", None)),
        "is_private": getattr(athlete, "is_private", False),
        "view_weeks_ahead": getattr(athlete, "view_weeks_ahead", 2),
        "training_reports_enabled": getattr(athlete, "training_reports_enabled", True),
        "week_report_enabled": getattr(athlete, "week_report_enabled", False),
        "daily_vitals_enabled": getattr(athlete, "daily_vitals_enabled", False),
        "auto_wucd_enabled": getattr(athlete, "auto_wucd_enabled", False),
        "auto_wu_m": getattr(athlete, "auto_wu_m", 0),
        "auto_cd_m": getattr(athlete, "auto_cd_m", 0),
        "zone_input_unit": unit,
        "zone_input_unit_label": unit_label,
        **zones_form,
    }

    if request.method == "POST":
        form["name"] = (request.POST.get("name") or "").strip()
        form["birth_year"] = (request.POST.get("birth_year") or "").strip()
        form["gender"] = (request.POST.get("gender") or "").strip()
        form["vdot"] = (request.POST.get("vdot") or "").strip()
        form["zone_method"] = (request.POST.get("zone_method") or "").strip() or "manual"
        form["pr_800"] = (request.POST.get("pr_800") or "").strip()
        form["pr_1500"] = (request.POST.get("pr_1500") or "").strip()
        form["pr_3000"] = (request.POST.get("pr_3000") or "").strip()
        form["pr_5000"] = (request.POST.get("pr_5000") or "").strip()
        form["pr_10000"] = (request.POST.get("pr_10000") or "").strip()
        form["tm"] = (request.POST.get("tm") or "").strip()
        form["thm"] = (request.POST.get("thm") or "").strip()
        form["t4"] = (request.POST.get("t4") or "").strip()
        form["target_pr_800"] = (request.POST.get("target_pr_800") or "").strip()
        form["target_pr_1500"] = (request.POST.get("target_pr_1500") or "").strip()
        form["target_pr_3000"] = (request.POST.get("target_pr_3000") or "").strip()
        form["target_pr_5000"] = (request.POST.get("target_pr_5000") or "").strip()
        form["target_pr_10000"] = (request.POST.get("target_pr_10000") or "").strip()
        form["target_tm"] = (request.POST.get("target_tm") or "").strip()
        form["target_thm"] = (request.POST.get("target_thm") or "").strip()
        form["target_t4"] = (request.POST.get("target_t4") or "").strip()
        form["is_private"] = (request.POST.get("is_private") == "on")
        form["view_weeks_ahead"] = (request.POST.get("view_weeks_ahead") or "2").strip()
        form["training_reports_enabled"] = (request.POST.get("training_reports_enabled") == "on")
        form["week_report_enabled"] = (request.POST.get("week_report_enabled") == "on")
        form["daily_vitals_enabled"] = (request.POST.get("daily_vitals_enabled") == "on")
        form["auto_wucd_enabled"] = (request.POST.get("auto_wucd_enabled") == "on")
        form["auto_wu_m"] = (request.POST.get("auto_wu_m") or "0").strip()
        form["auto_cd_m"] = (request.POST.get("auto_cd_m") or "0").strip()

        for z in ("1", "2", "3", "4", "5"):
            form[f"z{z}_pace"] = (request.POST.get(f"z{z}_pace") or "").strip()

        if not form["name"]:
            errors.append("Name is required.")

        try:
            birth_year = _parse_int(form["birth_year"])
        except ValueError:
            birth_year = None
            errors.append("Birth year is invalid (use a number).")
        if birth_year is None:
            errors.append("Birth year is required.")
        elif birth_year < 1900 or birth_year > 2100:
            errors.append("Birth year does not look valid.")

        gender = (form["gender"] or "").strip().upper()
        if gender not in ("M", "V", "X"):
            errors.append("Gender is required and must be M, V, or X.")

        try:
            vdot = _parse_float(form["vdot"])
            if vdot is not None and vdot < 0:
                errors.append("VDOT kan niet negatief zijn.")
        except ValueError:
            vdot = None
            errors.append("VDOT is invalid (use a number).")

        try:
            view_weeks_ahead = int(form["view_weeks_ahead"])
            if view_weeks_ahead < 0:
                errors.append("Weeks ahead cannot be negative.")
        except ValueError:
            view_weeks_ahead = 2
            errors.append("Weeks ahead is invalid (use a number).")

        auto_wu_m = _clean_non_negative_int(form["auto_wu_m"])
        auto_cd_m = _clean_non_negative_int(form["auto_cd_m"])

        try:
            pr_800_s = _parse_pr_time_to_seconds(form["pr_800"])
        except ValueError:
            pr_800_s = None
            errors.append("T800 is required and must use format m:ss(.ms), h:mm:ss(.ms), or mm.ss.ms.")

        try:
            pr_1500_s = _parse_pr_time_to_seconds(form["pr_1500"])
        except ValueError:
            pr_1500_s = None
            errors.append("T1500 is required and must use format m:ss(.ms), h:mm:ss(.ms), or mm.ss.ms.")

        try:
            pr_3000_s = _parse_pr_time_to_seconds(form["pr_3000"])
        except ValueError:
            pr_3000_s = None
            errors.append("T3000 is required and must use format m:ss(.ms), h:mm:ss(.ms), or mm.ss.ms.")

        try:
            pr_5000_s = _parse_pr_time_to_seconds(form["pr_5000"])
        except ValueError:
            pr_5000_s = None
            errors.append("T5000 is required and must use format m:ss(.ms), h:mm:ss(.ms), or mm.ss.ms.")

        try:
            pr_10000_s = _parse_pr_time_to_seconds(form["pr_10000"])
        except ValueError:
            pr_10000_s = None
            errors.append("T10000 is required and must use format m:ss(.ms), h:mm:ss(.ms), or mm.ss.ms.")

        try:
            tm_s = _parse_pr_time_to_seconds(form["tm"]) if form["tm"] else None
        except ValueError:
            tm_s = None
            errors.append("TM invalid format.")

        try:
            thm_s = _parse_pr_time_to_seconds(form["thm"]) if form["thm"] else None
        except ValueError:
            thm_s = None
            errors.append("THM invalid format.")

        try:
            t4_s = _parse_pr_time_to_seconds(form["t4"]) if form["t4"] else None
        except ValueError:
            t4_s = None
            errors.append("T4 invalid format.")

        target_pr_800_s, target_pr_1500_s, target_pr_3000_s = None, None, None
        target_pr_5000_s, target_pr_10000_s, target_tm_s = None, None, None
        target_thm_s, target_t4_s = None, None
        for key, label in (
            ("target_pr_800", "Goal T800"),
            ("target_pr_1500", "Goal T1500"),
            ("target_pr_3000", "Goal T3000"),
            ("target_pr_5000", "Goal T5000"),
            ("target_pr_10000", "Goal T10000"),
            ("target_tm", "Goal TM"),
            ("target_thm", "Goal THM"),
            ("target_t4", "Goal T4"),
        ):
            try:
                value = _parse_pr_time_to_seconds(form[key]) if form[key] else None
            except ValueError:
                value = None
                errors.append(f"{label} invalid format.")
            if key == "target_pr_800":
                target_pr_800_s = value
            elif key == "target_pr_1500":
                target_pr_1500_s = value
            elif key == "target_pr_3000":
                target_pr_3000_s = value
            elif key == "target_pr_5000":
                target_pr_5000_s = value
            elif key == "target_pr_10000":
                target_pr_10000_s = value
            elif key == "target_tm":
                target_tm_s = value
            elif key == "target_thm":
                target_thm_s = value
            elif key == "target_t4":
                target_t4_s = value

        if form["zone_method"] != "manual":
            errors.append("Zone method is not supported yet. Choose 'manual' for now.")

        zone_speed_mps, z_errors, normalized_input, other_under = parse_manual_zones_required(
            request.POST, unit=unit
        )
        errors.extend(z_errors)

        for z in ("1", "2", "3", "4", "5"):
            form[f"z{z}_pace"] = normalized_input.get(z, form[f"z{z}_pace"])
            form[f"z{z}_other"] = other_under.get(z, form.get(f"z{z}_other", "—"))

        if not errors:
            athlete.name = form["name"]
            athlete.birth_year = int(birth_year)
            athlete.gender = gender
            athlete.vdot = vdot
            athlete.zone_method = form["zone_method"]
            athlete.zone_speed_mps = zone_speed_mps
            athlete.view_weeks_ahead = view_weeks_ahead
            athlete.training_reports_enabled = form["training_reports_enabled"]
            athlete.week_report_enabled = form["week_report_enabled"]
            athlete.daily_vitals_enabled = form["daily_vitals_enabled"]
            athlete.auto_wucd_enabled = form["auto_wucd_enabled"]
            athlete.auto_wu_m = auto_wu_m
            athlete.auto_cd_m = auto_cd_m
            athlete.pr_800_s = pr_800_s
            athlete.pr_1500_s = pr_1500_s
            athlete.pr_3000_s = pr_3000_s
            athlete.pr_5000_s = pr_5000_s
            athlete.pr_10000_s = pr_10000_s
            athlete.pr_tm_s = tm_s
            athlete.pr_thm_s = thm_s
            athlete.pr_400_s = t4_s
            athlete.target_pr_800_s = target_pr_800_s
            athlete.target_pr_1500_s = target_pr_1500_s
            athlete.target_pr_3000_s = target_pr_3000_s
            athlete.target_pr_5000_s = target_pr_5000_s
            athlete.target_pr_10000_s = target_pr_10000_s
            athlete.target_pr_tm_s = target_tm_s
            athlete.target_pr_thm_s = target_thm_s
            athlete.target_pr_400_s = target_t4_s
            athlete.is_private = form["is_private"]
            athlete.save()

            return redirect(f"{reverse('coach_athlete_edit', args=[athlete.id])}?tab=zones&saved=1")

    return render(
        request,
        "core/coach_athlete_form.html",
        {"mode": "edit", "athlete": athlete, "form": form, "errors": errors, "saved_notice": saved_notice, "active_tab": active_tab},
    )


@login_required
@require_http_methods(["POST"])
def coach_athlete_target_prs_view(request, athlete_id: int):
    athlete = get_object_or_404(_filter_owned(Athlete.objects.all(), request.user), id=athlete_id)
    values, errors = _parse_optional_target_prs(request.POST)
    if errors:
        return JsonResponse({"ok": False, "errors": errors}, status=400)

    for field, value in values.items():
        setattr(athlete, field, value)
    athlete.save(update_fields=list(values.keys()))

    return JsonResponse({
        "ok": True,
        "values": {field: _format_pr_seconds(value) for field, value in values.items()},
    })


# -----------------------------
# Groups CRUD
# -----------------------------
@login_required
@require_GET
def coach_groups_view(request):
    groups = _filter_owned(Group.objects.prefetch_related("athletes").order_by("name"), request.user)
    return render(request, "core/coach_groups.html", {"groups": groups})


@login_required
@require_http_methods(["GET", "POST"])
def coach_group_create_view(request):
    errors = []
    athletes_all = _filter_owned(Athlete.objects.order_by("name"), request.user)
    form = {"name": "", "athlete_ids": []}

    if request.method == "POST":
        form["name"] = (request.POST.get("name") or "").strip()
        form["athlete_ids"] = _clean_int_list(request.POST.getlist("athlete_ids"))

        if not form["name"]:
            errors.append("Group name is required.")

        if not errors:
            g = Group.objects.create(owner=request.user, name=form["name"])
            g.athletes.set(_filter_owned(Athlete.objects.filter(id__in=form["athlete_ids"]), request.user))
            return redirect("coach_groups")

    return render(
        request,
        "core/coach_group_form.html",
        {"mode": "create", "group": None, "errors": errors, "athletes_all": athletes_all, "form": form},
    )


@login_required
@require_http_methods(["GET", "POST"])
def coach_group_edit_view(request, group_id: int):
    group = get_object_or_404(_filter_owned(Group.objects.all(), request.user), id=group_id)
    athletes_all = _filter_owned(Athlete.objects.order_by("name"), request.user)

    selected_ids = set(group.athletes.values_list("id", flat=True))
    errors = []
    form = {"name": group.name or "", "athlete_ids": list(selected_ids)}

    if request.method == "POST":
        form["name"] = (request.POST.get("name") or "").strip()
        form["athlete_ids"] = _clean_int_list(request.POST.getlist("athlete_ids"))

        if not form["name"]:
            errors.append("Group name is required.")

        if not errors:
            group.name = form["name"]
            group.save()
            group.athletes.set(_filter_owned(Athlete.objects.filter(id__in=form["athlete_ids"]), request.user))
            return redirect("coach_groups")

    return render(
        request,
        "core/coach_group_form.html",
        {"mode": "edit", "group": group, "errors": errors, "athletes_all": athletes_all, "form": form},
    )


# -----------------------------
# Assignments (editable)
# -----------------------------
@login_required
@require_GET
def coach_assignments_view(request):
    sort = request.GET.get("sort", "name")
    if sort == "start":
        qs = TrainingPlan.objects.order_by("start_date")
    elif sort == "end":
        qs = TrainingPlan.objects.order_by("end_date")
    else:
        qs = TrainingPlan.objects.order_by(Lower("name"))

    plans = _filter_owned(qs.prefetch_related("groups", "athletes"), request.user)

    rows = []
    for p in plans:
        rows.append(
            {
                "plan": p,
                "start_date": p.start_date,
                "end_date": p.end_date,
                "group_names": list(p.groups.order_by("name").values_list("name", flat=True)),
                "direct_athletes": list(p.athletes.order_by("name").values_list("name", flat=True)),
                "count_groups": p.groups.count(),
                "count_direct": p.athletes.count(),
                "count_total": len(p.targeted_athlete_ids()),
            }
        )
    return render(request, "core/coach_assignments.html", {"rows": rows})


@login_required
@require_http_methods(["GET", "POST"])
def coach_assignment_edit_view(request, plan_id: int):
    plan = get_object_or_404(_filter_owned(TrainingPlan.objects.all(), request.user), id=plan_id)

    groups_all = _filter_owned(Group.objects.order_by("name"), request.user)
    athletes_all = _filter_owned(Athlete.objects.order_by("name"), request.user)

    selected_group_ids = set(plan.groups.values_list("id", flat=True))
    selected_direct_ids = set(plan.athletes.values_list("id", flat=True))

    errors = []
    form = {"group_ids": list(selected_group_ids), "athlete_ids": list(selected_direct_ids)}

    if request.method == "POST":
        form["group_ids"] = _clean_int_list(request.POST.getlist("group_ids"))
        form["athlete_ids"] = _clean_int_list(request.POST.getlist("athlete_ids"))

        if not plan.start_date or not plan.end_date:
            errors.append("Fill in start_date and end_date for this plan before linking targets.")

        if plan.start_date and plan.end_date:
            selected_group_athlete_ids = set(
                _filter_owned(Athlete.objects.filter(groups__id__in=form["group_ids"]), request.user).values_list("id", flat=True)
            )
            desired_athlete_ids = set(form["athlete_ids"]) | selected_group_athlete_ids

            for aid in sorted(desired_athlete_ids):
                other_plans = _plans_targeting_athlete(aid).exclude(id=plan.id)
                for op in other_plans:
                    if not op.start_date or not op.end_date:
                        a = Athlete.objects.filter(id=aid).first()
                        a_name = a.name if a else f"athlete_id={aid}"
                        errors.append(
                            f"Overlap/conflict: {a_name} is already in plan '{op.name}', but that plan has no start/end date."
                        )
                        continue
                    if _ranges_overlap(plan.start_date, plan.end_date, op.start_date, op.end_date):
                        a = Athlete.objects.filter(id=aid).first()
                        a_name = a.name if a else f"athlete_id={aid}"
                        errors.append(
                            f"Overlap/conflict: {a_name} is already in plan '{op.name}' ({op.start_date} to {op.end_date})."
                        )

        if not errors:
            plan.groups.set(_filter_owned(Group.objects.filter(id__in=form["group_ids"]), request.user))

            existing_ids = set(PlanMembership.objects.filter(plan=plan).values_list("athlete_id", flat=True))
            desired_direct_ids = set(form["athlete_ids"])

            to_remove = existing_ids - desired_direct_ids
            if to_remove:
                PlanMembership.objects.filter(plan=plan, athlete_id__in=to_remove).delete()

            to_add = desired_direct_ids - existing_ids
            for aid in to_add:
                PlanMembership.objects.create(plan=plan, athlete_id=aid)

            return redirect("coach_assignments")

    return render(
        request,
        "core/coach_assignment_form.html",
        {"plan": plan, "groups_all": groups_all, "athletes_all": athletes_all, "errors": errors, "form": form},
    )


# -----------------------------
# Athletes DELETE
# -----------------------------
@login_required
@require_http_methods(["POST"])
def coach_athlete_delete_view(request, athlete_id: int):
    athlete = get_object_or_404(_filter_owned(Athlete.objects.all(), request.user), id=athlete_id)
    athlete.delete()
    return redirect("coach_athletes")


# -----------------------------
# Groups DELETE
# -----------------------------
@login_required
@require_http_methods(["POST"])
def coach_group_delete_view(request, group_id: int):
    group = get_object_or_404(_filter_owned(Group.objects.all(), request.user), id=group_id)
    group.delete()
    return redirect("coach_groups")

from core.models import AthleteDayCheck, AthleteDayComment
from core.views.calendar import (
    _VirtualSegment,
    _VirtualSlot,
    _annotate_slot_segment_display_times,
    _base_planning_slot_for_day,
    _get_athlete_year_flex_plan,
    _is_flex_planner_plan,
    _slot_has_race,
    _slot_is_visually_empty,
    _virtual_race_slot_from_entries,
    _virtual_slot_from_base_training,
)


def _daily_status_badge(status):
    status = (status or "").strip()
    if status == "done_as_planned":
        return {"symbol": "✓", "color": "#00cc00"}
    if status == "too_hard_fast":
        return {"symbol": "↑", "color": "#f28c28"}
    if status == "adjusted_ok":
        return {"symbol": "✓", "color": "#f28c28"}
    if status == "lighter_slower":
        return {"symbol": "↓", "color": "#f28c28"}
    if status == "not_done":
        return {"symbol": "✕", "color": "#cc0000"}
    return {"symbol": "", "color": ""}


@login_required
def daily_overview_view(request):
    from datetime import date
    from django.db.models import Q

    today = date.today()
    date_value = (request.GET.get("date") or today.isoformat()).strip()
    slot_filter = (request.GET.get("slots") or "both").strip().lower()
    if slot_filter not in {"am", "pm", "both"}:
        slot_filter = "both"

    selection_mode = (request.GET.get("selection") or "all").strip().lower()
    if selection_mode not in {"all", "selection", "trains"}:
        selection_mode = "all"

    try:
        d = date.fromisoformat(date_value)
    except Exception:
        d = today
        date_value = d.isoformat()

    all_athletes = list(_filter_owned(Athlete.objects.order_by("name"), request.user))
    all_athlete_ids = {athlete.id for athlete in all_athletes}
    coach_settings, _ = CoachSettings.objects.get_or_create(user=request.user)
    dco_train_athlete_ids = {
        int(value)
        for value in (coach_settings.dco_train_athlete_ids or [])
        if str(value).isdigit() and int(value) in all_athlete_ids
    }

    if request.method == "POST" and request.POST.get("action") == "save_dco_trains":
        new_train_ids = [
            int(value)
            for value in request.POST.getlist("train_athletes")
            if str(value).isdigit() and int(value) in all_athlete_ids
        ]
        coach_settings.dco_train_athlete_ids = new_train_ids
        coach_settings.save(update_fields=["dco_train_athlete_ids", "updated_at"])

        redirect_query = {
            "date": request.POST.get("date") or date_value,
            "slots": request.POST.get("slots") or slot_filter,
            "selection": request.POST.get("selection") or selection_mode,
        }
        posted_selected = [
            value
            for value in request.POST.getlist("athletes")
            if str(value).isdigit() and int(value) in all_athlete_ids
        ]
        if redirect_query["selection"] == "selection":
            redirect_query["athletes"] = posted_selected
        return redirect(f"{reverse('daily_overview')}?{urlencode(redirect_query, doseq=True)}")

    selected_athlete_ids = {
        int(value)
        for value in request.GET.getlist("athletes")
        if str(value).isdigit()
    }

    if selection_mode == "selection":
        athletes = [athlete for athlete in all_athletes if athlete.id in selected_athlete_ids]
    elif selection_mode == "trains":
        athletes = [athlete for athlete in all_athletes if athlete.id in dco_train_athlete_ids]
        selected_athlete_ids = set(dco_train_athlete_ids)
    else:
        athletes = all_athletes
        selected_athlete_ids = {athlete.id for athlete in athletes}

    show_results = request.GET.get("ok") == "1"
    athlete_ids = [a.id for a in athletes]

    check_map = {}
    for check in AthleteDayCheck.objects.filter(date=d, athlete_id__in=athlete_ids):
        check_map[(check.athlete_id, int(check.slot_index or 1))] = check.effective_status

    comment_map = {}
    for comment in AthleteDayComment.objects.filter(date=d, athlete_id__in=athlete_ids):
        comment_map[comment.athlete_id] = comment

    accessible_plans = list(_filter_owned(TrainingPlan.objects.order_by("name"), request.user).exclude(name__startswith="Flex Planner"))
    flex_plan = _get_athlete_year_flex_plan(request.user, athletes[0] if athletes else None, d, d + timedelta(days=1))

    plan_targets = {}
    for plan in accessible_plans:
        if _is_flex_planner_plan(plan):
            continue
        try:
            target_ids = set(plan.targeted_athlete_ids())
        except Exception:
            target_ids = set()
        if target_ids:
            plan_targets[plan.id] = target_ids

    relevant_plan_ids = set()
    plan_for_athlete = {}
    if flex_plan:
        relevant_plan_ids.add(flex_plan.id)

    for athlete in athletes:
        matching_plan = None
        for plan in accessible_plans:
            if athlete.id not in plan_targets.get(plan.id, set()):
                continue
            if plan.start_date and plan.start_date > d:
                continue
            if plan.end_date and plan.end_date < d:
                continue
            matching_plan = plan
            break

        if matching_plan:
            plan_for_athlete[athlete.id] = matching_plan
            relevant_plan_ids.add(matching_plan.id)
        elif flex_plan:
            plan_for_athlete[athlete.id] = flex_plan
            relevant_plan_ids.add(flex_plan.id)

    slot_lookup = {}
    has_fix_keys = set()
    if relevant_plan_ids and athlete_ids:
        slot_qs = (
            TrainingSlot.objects
            .filter(plan_id__in=relevant_plan_ids, date=d)
            .filter(Q(athlete__isnull=True) | Q(athlete_id__in=athlete_ids))
            .prefetch_related("segments")
            .select_related("plan", "athlete")
        )
        for slot in slot_qs:
            slot_lookup[(slot.plan_id, slot.athlete_id or None, slot.date, int(slot.slot_index))] = slot
            if slot.athlete_id:
                has_fix_keys.add((slot.plan_id, slot.athlete_id, slot.date, int(slot.slot_index)))

    base_blocks_by_athlete = {}
    trainer_plan_ids = set()
    if athlete_ids:
        base_slot_qs = AthleteBasePlanningSlot.objects.select_related("trainer_plan").order_by("weekday", "slot_index")
        base_blocks = (
            AthleteBasePlanningBlock.objects
            .filter(athlete_id__in=athlete_ids)
            .prefetch_related(Prefetch("slots", queryset=base_slot_qs, to_attr="_prefetched_base_slots"))
            .order_by("athlete_id", "sort_order", "start_month", "start_day", "id")
        )
        for block in base_blocks:
            base_blocks_by_athlete.setdefault(block.athlete_id, []).append(block)
            for base_slot in getattr(block, "_prefetched_base_slots", []):
                if base_slot.mode == AthleteBasePlanningSlot.MODE_TRAINER and base_slot.trainer_plan_id:
                    trainer_plan_ids.add(base_slot.trainer_plan_id)

    trainer_slot_lookup = {}
    if trainer_plan_ids:
        trainer_slot_qs = (
            TrainingSlot.objects
            .filter(plan_id__in=trainer_plan_ids, athlete__isnull=True, date=d)
            .prefetch_related("segments")
            .select_related("plan")
        )
        for trainer_slot in trainer_slot_qs:
            trainer_slot_lookup[(trainer_slot.plan_id, trainer_slot.date, int(trainer_slot.slot_index))] = trainer_slot

    race_entries_by_athlete = {}
    if athlete_ids:
        race_entry_qs = (
            RaceEntry.objects
            .filter(athlete_id__in=athlete_ids, race_distance__race__date=d)
            .filter(Q(coach_selected=True) | Q(athlete_selected=True) | Q(target_selected=True))
            .select_related("race_distance", "race_distance__race")
            .order_by("race_distance__race__name", "race_distance__id")
        )
        for entry in race_entry_qs:
            race_entries_by_athlete.setdefault(entry.athlete_id, []).append(entry)

    def effective_daily_slot(athlete, slot_index):
        plan = plan_for_athlete.get(athlete.id)
        slot = None
        is_override = False
        flex_blocks_base = False

        if plan:
            override_slot = slot_lookup.get((plan.id, athlete.id, d, slot_index))
            base_slot = slot_lookup.get((plan.id, None, d, slot_index))
            slot = override_slot or base_slot
            is_override = override_slot is not None

        if flex_plan:
            flex_override_slot = slot_lookup.get((flex_plan.id, athlete.id, d, slot_index))
            if flex_override_slot is not None:
                if _slot_is_visually_empty(flex_override_slot):
                    if not _slot_has_race(slot):
                        slot = None
                        flex_blocks_base = True
                else:
                    slot = flex_override_slot
                    is_override = True

        if slot_index == 2 and not is_override:
            race_slot = _virtual_race_slot_from_entries(race_entries_by_athlete.get(athlete.id, []))
            if race_slot:
                slot = race_slot

        if not slot and not flex_blocks_base:
            base_planning_slot = _base_planning_slot_for_day(base_blocks_by_athlete, athlete.id, d, slot_index)
            if base_planning_slot:
                if base_planning_slot.mode == AthleteBasePlanningSlot.MODE_TRAINING:
                    slot = _virtual_slot_from_base_training(base_planning_slot.training_text)
                elif base_planning_slot.mode == AthleteBasePlanningSlot.MODE_TRAINER and base_planning_slot.trainer_plan_id:
                    slot = trainer_slot_lookup.get((base_planning_slot.trainer_plan_id, d, slot_index))
                    if _slot_is_visually_empty(slot) and base_planning_slot.trainer_plan:
                        slot = _VirtualSlot([_VirtualSegment(text=base_planning_slot.trainer_plan.name, type="GROUP")])

        _annotate_slot_segment_display_times(slot, athlete)
        return None if _slot_is_visually_empty(slot) else slot

    rows = []

    for athlete in athletes:

        status1 = check_map.get((athlete.id, 1), "")
        status2 = check_map.get((athlete.id, 2), "")
        slot1 = effective_daily_slot(athlete, 1)
        slot2 = effective_daily_slot(athlete, 2)

        rows.append({
            "athlete": athlete,
            "slot1": slot1,
            "slot2": slot2,
            "check1_badge": _daily_status_badge(status1),
            "check2_badge": _daily_status_badge(status2),
            "comment": comment_map.get(athlete.id),
        })

    selection_query = {
        "date": date_value,
        "slots": slot_filter,
        "selection": selection_mode,
    }
    if selection_mode == "selection":
        selection_query["athletes"] = [str(athlete_id) for athlete_id in sorted(selected_athlete_ids)]
    selection_url = f"{reverse('daily_overview')}?{urlencode(selection_query, doseq=True)}"

    return render(request, "core/daily_overview.html", {
        "rows": rows,
        "date": d,
        "date_value": date_value,
        "slot_filter": slot_filter,
        "selection_mode": selection_mode,
        "all_athletes": all_athletes,
        "selected_athlete_ids": selected_athlete_ids,
        "dco_train_athlete_ids": dco_train_athlete_ids,
        "show_results": show_results,
        "show_am": slot_filter in {"am", "both"},
        "show_pm": slot_filter in {"pm", "both"},
        "selection_url": selection_url,
    })
