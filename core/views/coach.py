from datetime import date, timedelta
import calendar as py_calendar
import base64
import json
import math
import os
import re
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
from django.db.models import Prefetch, Q
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


def _polar_connection_for_athlete_request(request, athlete_id):
    athlete = None
    athlete_id_str = str(athlete_id or "").strip()
    if athlete_id_str.isdigit():
        if request.user.is_staff or request.user.is_superuser:
            athlete = _filter_owned(Athlete.objects.all(), request.user).filter(id=int(athlete_id_str)).first()
        else:
            own_athlete = _athlete_for_user(request.user)
            if own_athlete and own_athlete.id == int(athlete_id_str):
                athlete = own_athlete
    if not athlete:
        return None, None

    athlete_user = _user_for_athlete(athlete)
    if not athlete_user:
        return athlete, None
    return athlete, PolarConnection.objects.filter(user=athlete_user).first()


def _polar_duration_seconds(value):
    text = str(value or "").strip().upper()
    match = re.fullmatch(r"PT(?:(\d+(?:\.\d+)?)H)?(?:(\d+(?:\.\d+)?)M)?(?:(\d+(?:\.\d+)?)S)?", text)
    if not match:
        return None
    hours = float(match.group(1) or 0)
    minutes = float(match.group(2) or 0)
    seconds = float(match.group(3) or 0)
    return int(round((hours * 3600) + (minutes * 60) + seconds))


def _format_seconds_hms(seconds):
    if seconds is None:
        return ""
    seconds = int(seconds)
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


def _format_pace(seconds, distance_m=1000.0):
    if not seconds or not distance_m:
        return ""
    pace_seconds = float(seconds) * (1000.0 / float(distance_m))
    minutes = int(pace_seconds // 60)
    secs = int(round(pace_seconds % 60))
    if secs == 60:
        minutes += 1
        secs = 0
    return f"{minutes}:{secs:02d}/km"


@login_required
@require_GET
def dashboard_view(request):
    athlete = _athlete_for_user(request.user)
    is_athlete_user = bool(athlete and not request.user.is_staff and not request.user.is_superuser)

    return render(request, "core/dashboard.html", {
        "is_athlete_user": is_athlete_user,
        "is_trainer_user": bool(request.user.is_staff or request.user.is_superuser),
        "current_athlete": athlete,
    })


POLAR_AUTHORIZATION_URL = "https://flow.polar.com/oauth2/authorization"
POLAR_TOKEN_URL = "https://polarremote.com/v2/oauth2/token"
POLAR_V4_AUTHORIZATION_URL = "https://auth.polar.com/oauth/authorize"
POLAR_V4_TOKEN_URL = "https://auth.polar.com/oauth/token"
POLAR_REGISTER_USER_URL = "https://www.polaraccesslink.com/v3/users"
POLAR_EXERCISES_URL = "https://www.polaraccesslink.com/v3/exercises"
POLAR_PHYSICAL_INFO_URL = "https://www.polaraccesslink.com/v3/users/physical-info"
POLAR_ACTIVITIES_URL = "https://www.polaraccesslink.com/v3/users/activities"
POLAR_V4_TRAINING_SESSIONS_URL = "https://www.polaraccesslink.com/v4/data/training-sessions/list"


def _polar_exercises_url(include_detail=True):
    params = {
        "samples": "true" if include_detail else "false",
        "zones": "true" if include_detail else "false",
        "route": "true" if include_detail else "false",
    }
    return f"{POLAR_EXERCISES_URL}?{urlencode(params)}"


def _polar_value(data, *names, default=None):
    for name in names:
        if isinstance(data, dict) and name in data:
            return data.get(name)
    return default


def _polar_sample_type(sample):
    value = _polar_value(sample, "sample_type", "sample-type")
    return str(value) if value is not None else ""


def _polar_sample_values(sample):
    raw = _polar_value(sample, "data", default="")
    values = []
    parts = raw if isinstance(raw, list) else str(raw or "").split(",")
    for part in parts:
        if part is None:
            values.append(None)
            continue
        if isinstance(part, (int, float)):
            values.append(float(part))
            continue
        part = str(part).strip().strip("[]'\"")
        if not part or part.upper() == "NULL":
            values.append(None)
            continue
        try:
            values.append(float(part))
        except ValueError:
            values.append(None)
    return values


def _polar_sample_rate(sample):
    value = _polar_value(sample, "recording_rate", "recording-rate", default=1)
    try:
        value = float(value)
    except (TypeError, ValueError):
        value = 1.0
    return value if value > 0 else 1.0


def _polar_sample_map(exercise):
    sample_map = {}
    for sample in exercise.get("samples") or []:
        if not isinstance(sample, dict):
            continue
        sample_map[_polar_sample_type(sample)] = sample
    return sample_map


def _splits_from_cumulative_distance(values, rate_seconds, split_m=1000.0, max_count=None):
    points = []
    for index, distance_m in enumerate(values):
        if distance_m is None:
            continue
        try:
            distance_m = float(distance_m)
        except (TypeError, ValueError):
            continue
        if distance_m >= 0:
            points.append((index * rate_seconds, distance_m))
    return _splits_from_time_distance_points(points, split_m=split_m, max_count=max_count)


def _splits_from_speed(values, rate_seconds, split_m=1000.0, max_count=None):
    points = [(0.0, 0.0)]
    elapsed = 0.0
    distance_m = 0.0
    for speed_kmh in values:
        if speed_kmh is not None:
            try:
                distance_m += (float(speed_kmh) * 1000.0 / 3600.0) * rate_seconds
            except (TypeError, ValueError):
                pass
        elapsed += rate_seconds
        points.append((elapsed, distance_m))
    return _splits_from_time_distance_points(points, split_m=split_m, max_count=max_count)


def _polar_route_time_seconds(point, fallback_index):
    seconds = _polar_duration_seconds(point.get("time") or "")
    if seconds is not None:
        return float(seconds)
    return float(fallback_index)


def _haversine_m(lat1, lon1, lat2, lon2):
    radius_m = 6371000.0
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lon2 - lon1)
    a = (math.sin(d_phi / 2) ** 2) + math.cos(phi1) * math.cos(phi2) * (math.sin(d_lambda / 2) ** 2)
    return radius_m * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _splits_from_route(route, split_m=1000.0, max_count=None):
    points = []
    previous = None
    distance_m = 0.0
    for index, point in enumerate(route or []):
        if not isinstance(point, dict):
            continue
        try:
            lat = float(point.get("latitude"))
            lon = float(point.get("longitude"))
        except (TypeError, ValueError):
            continue
        elapsed = _polar_route_time_seconds(point, index)
        if previous:
            distance_m += _haversine_m(previous["lat"], previous["lon"], lat, lon)
        points.append((elapsed, distance_m))
        previous = {"lat": lat, "lon": lon}
    return _splits_from_time_distance_points(points, split_m=split_m, max_count=max_count)


def _time_distance_points_from_exercise(exercise):
    samples = _polar_sample_map(exercise)
    if "10" in samples:
        sample = samples["10"]
        rate_seconds = _polar_sample_rate(sample)
        points = []
        for index, distance_m in enumerate(_polar_sample_values(sample)):
            if distance_m is None:
                continue
            try:
                distance_m = float(distance_m)
            except (TypeError, ValueError):
                continue
            if distance_m >= 0:
                points.append((index * rate_seconds, distance_m))
        return "distance samples", points

    if "1" in samples:
        sample = samples["1"]
        rate_seconds = _polar_sample_rate(sample)
        points = [(0.0, 0.0)]
        elapsed = 0.0
        distance_m = 0.0
        for speed_kmh in _polar_sample_values(sample):
            if speed_kmh is not None:
                try:
                    distance_m += (float(speed_kmh) * 1000.0 / 3600.0) * rate_seconds
                except (TypeError, ValueError):
                    pass
            elapsed += rate_seconds
            points.append((elapsed, distance_m))
        return "speed samples", points

    if isinstance(exercise.get("route"), list):
        points = []
        previous = None
        distance_m = 0.0
        for index, point in enumerate(exercise.get("route") or []):
            if not isinstance(point, dict):
                continue
            try:
                lat = float(point.get("latitude"))
                lon = float(point.get("longitude"))
            except (TypeError, ValueError):
                continue
            elapsed = _polar_route_time_seconds(point, index)
            if previous:
                distance_m += _haversine_m(previous["lat"], previous["lon"], lat, lon)
            points.append((elapsed, distance_m))
            previous = {"lat": lat, "lon": lon}
        return "route", points

    return "", []


def _splits_from_time_distance_points(points, split_m=1000.0, max_count=None):
    if len(points) < 2:
        return []
    split_m = float(split_m or 1000.0)
    if split_m <= 0:
        split_m = 1000.0
    points = sorted(points, key=lambda item: item[0])
    max_distance = max(distance for _time, distance in points)
    splits = []
    previous_threshold_m = 0.0
    previous_threshold_t = 0.0
    threshold_m = split_m
    point_index = 1
    while threshold_m <= max_distance:
        if max_count and len(splits) >= max_count:
            break
        while point_index < len(points) and points[point_index][1] < threshold_m:
            point_index += 1
        if point_index >= len(points):
            break
        t1, d1 = points[point_index - 1]
        t2, d2 = points[point_index]
        if d2 <= d1:
            threshold_t = t2
        else:
            threshold_t = t1 + ((threshold_m - d1) / (d2 - d1)) * (t2 - t1)
        duration = threshold_t - previous_threshold_t
        label = f"{int(threshold_m / 1000)} km" if split_m == 1000.0 else f"{len(splits) + 1} x {int(round(split_m))}m"
        splits.append({
            "label": label,
            "distance_m": round(split_m),
            "duration": _format_seconds_hms(round(duration)),
            "duration_s": duration,
            "pace": _format_pace(duration, split_m),
        })
        previous_threshold_m = threshold_m
        previous_threshold_t = threshold_t
        threshold_m += split_m

    final_t, final_d = points[-1]
    partial_m = final_d - previous_threshold_m
    partial_t = final_t - previous_threshold_t
    if not max_count and partial_m >= 50 and partial_t > 0:
        splits.append({
            "label": f"{final_d / 1000:.2f} km",
            "distance_m": round(partial_m),
            "duration": _format_seconds_hms(round(partial_t)),
            "duration_s": partial_t,
            "pace": _format_pace(partial_t, partial_m),
        })
    return splits


def _polar_exercise_splits(exercise):
    samples = _polar_sample_map(exercise)
    source = ""
    splits = []
    if "10" in samples:
        source = "distance samples"
        sample = samples["10"]
        splits = _splits_from_cumulative_distance(_polar_sample_values(sample), _polar_sample_rate(sample))
    if not splits and "1" in samples:
        source = "speed samples"
        sample = samples["1"]
        splits = _splits_from_speed(_polar_sample_values(sample), _polar_sample_rate(sample))
    if not splits and isinstance(exercise.get("route"), list):
        source = "route"
        splits = _splits_from_route(exercise.get("route"))

    distance_m = None
    try:
        distance_m = float(exercise.get("distance")) if exercise.get("distance") is not None else None
    except (TypeError, ValueError):
        distance_m = None
    duration_s = _polar_duration_seconds(exercise.get("duration") or "")
    return {
        "id": exercise.get("id") or "",
        "start_time": exercise.get("start_time") or "",
        "sport": exercise.get("sport") or exercise.get("detailed_sport_info") or "",
        "duration": _format_seconds_hms(duration_s),
        "distance_km": round(distance_m / 1000.0, 2) if distance_m is not None else None,
        "average_pace": _format_pace(duration_s, distance_m) if duration_s and distance_m else "",
        "sample_types": ", ".join(sorted(samples.keys(), key=lambda item: int(item) if item.isdigit() else 99)),
        "source": source,
        "splits": splits,
    }


def _polar_splits_for_distance(exercise, split_m, max_count=None):
    samples = _polar_sample_map(exercise)
    if "10" in samples:
        sample = samples["10"]
        return "distance samples", _splits_from_cumulative_distance(
            _polar_sample_values(sample),
            _polar_sample_rate(sample),
            split_m=split_m,
            max_count=max_count,
        )
    if "1" in samples:
        sample = samples["1"]
        return "speed samples", _splits_from_speed(
            _polar_sample_values(sample),
            _polar_sample_rate(sample),
            split_m=split_m,
            max_count=max_count,
        )
    if isinstance(exercise.get("route"), list):
        return "route", _splits_from_route(exercise.get("route"), split_m=split_m, max_count=max_count)
    return "", []


def _planned_rep_spec(plan_text):
    text = str(plan_text or "").lower().replace(",", ".")
    match = re.search(r"(\d+)\s*\*\s*(?:\(\s*)?(\d+(?:\.\d+)?)\s*m", text)
    if not match:
        return None
    reps = int(match.group(1))
    distance_m = float(match.group(2))
    if reps <= 0 or distance_m <= 0:
        return None
    return {"reps": reps, "distance_m": distance_m}


def _planned_single_distance_spec(plan_text):
    text = str(plan_text or "").lower().replace(",", ".")
    if "*" in text:
        return None
    distances = []
    for value, unit in re.findall(r"(\d+(?:\.\d+)?)\s*(km|k|m)\b", text, re.I):
        meters = _ayc_like_meters(value, unit)
        if meters > 0:
            distances.append(meters)
    if not distances:
        return None
    distance_m = sum(distances)
    return {"distance_m": distance_m} if distance_m > 0 else None


def _planned_interval_structure(plan_text):
    text = str(plan_text or "").lower().replace(",", ".")
    match = re.search(r"(\d+)\s*\*\s*\(([^)]+)\)", text)
    simple_match = None
    if not match:
        simple_match = re.search(r"(\d+)\s*\*\s*(\d+(?:\.\d+)?)\s*(km|k|m)\b", text, re.I)
        if not simple_match:
            return None

    try:
        sets = int(match.group(1) if match else 1)
    except (TypeError, ValueError):
        return None
    if sets <= 0:
        return None

    if simple_match:
        try:
            simple_reps = int(simple_match.group(1))
        except (TypeError, ValueError):
            return None
        meters = _ayc_like_meters(simple_match.group(2), simple_match.group(3))
        if simple_reps <= 0 or meters <= 0:
            return None
        inner = "-".join([f"{int(round(meters))}m"] * simple_reps)
        match_start = simple_match.start()
        match_end = simple_match.end()
    else:
        inner = match.group(2) or ""
        match_start = match.start()
        match_end = match.end()
    parts = [part.strip() for part in re.split(r"\s*-\s*", inner) if part.strip()]
    distances = []
    for value, unit in re.findall(r"(\d+(?:\.\d+)?)\s*(km|k|m)\b", inner, re.I):
        meters = _ayc_like_meters(value, unit)
        if meters > 0:
            distances.append(round(meters))

    durations = []
    if not distances:
        for part in parts:
            seconds = _coach_duration_token_seconds(part)
            if seconds is None:
                durations = []
                break
            durations.append(seconds)

    if not distances and not durations:
        return None

    pause_s = _coach_suffix_duration_seconds(text, "p")
    set_pause_s = _coach_suffix_duration_seconds(text, "sp", default_unit="min")
    lead_in_s, lead_out_s = _planned_easy_bookends_s(text, match_start, match_end)
    lead_in_m, lead_out_m = _planned_easy_bookends_m(text, match_start, match_end)
    out = {
        "sets": sets,
        "pattern_type": "distance" if distances else "duration",
        "reps_total": sets * len(distances or durations),
        "pause_s": pause_s,
        "set_pause_s": set_pause_s,
        "lead_in_s": lead_in_s,
        "lead_out_s": lead_out_s,
        "lead_in_m": lead_in_m,
        "lead_out_m": lead_out_m,
        "pause": _format_seconds_hms(pause_s) if pause_s else "",
        "set_pause": _format_seconds_hms(set_pause_s) if set_pause_s else "",
    }
    if distances:
        out["pattern_m"] = distances
        out["core_distance_m"] = sets * sum(distances)
    else:
        out["pattern_s"] = durations
        out["core_duration_s"] = sets * sum(durations)
    return out


def _ayc_like_meters(value, unit):
    try:
        n = float(str(value or "0").replace(",", "."))
    except (TypeError, ValueError):
        return 0.0
    return n * 1000.0 if str(unit or "m").lower() in ("km", "k") else n


def _coach_duration_token_seconds(token):
    s = str(token or "").replace("”", '"').replace("“", '"').replace("″", '"').replace("’", "'").replace("‘", "'").replace("′", "'")
    s = re.sub(r"\bz\s*[1-6]\b", "", s, flags=re.I).strip()
    s = re.sub(r"\b(?:tm|thm|t4|t\s*(?:10|5|3|15|8|800|1500|3000|5000|10000))\b", "", s, flags=re.I).strip()
    m = re.fullmatch(r"(\d{1,2}):(\d{2})(?::(\d{2}))?", s)
    if m:
        a = int(m.group(1))
        b = int(m.group(2))
        c = m.group(3)
        return (a * 3600) + (b * 60) + int(c) if c is not None else (a * 60) + b
    m = re.fullmatch(r"(\d+(?:[.,]\d+)?)\s*(?:\"|sec|secs|second|seconds|s)", s, re.I)
    if m:
        return int(round(float(m.group(1).replace(",", "."))))
    m = re.fullmatch(r"(\d+(?:[.,]\d+)?)\s*(?:'|min|mins|minute|minutes)", s, re.I)
    if m:
        return int(round(float(m.group(1).replace(",", ".")) * 60))
    return None


def _coach_distance_token_m(token):
    s = str(token or "").replace(",", ".")
    s = re.sub(r"\bz\s*[1-6]\b", "", s, flags=re.I).strip()
    s = re.sub(r"\b(?:tm|thm|t4|t\s*(?:10|5|3|15|8|800|1500|3000|5000|10000))\b", "", s, flags=re.I).strip()
    total = 0.0
    for value, unit in re.findall(r"(\d+(?:\.\d+)?)\s*(km|k|m)\b", s, flags=re.I):
        total += _ayc_like_meters(value, unit)
    return total if total > 0 else None


def _coach_suffix_duration_seconds(text, label, default_unit="s"):
    normalised = str(text or "").replace("”", '"').replace("“", '"').replace("″", '"').replace("’", "'").replace("‘", "'").replace("′", "'")
    pattern = rf"\b{re.escape(label)}\s*(\d+(?:[.,]\d+)?)(?:\s*(\"|sec|secs|second|seconds|s|min|mins|minute|minutes|'))?"
    matches = list(re.finditer(pattern, normalised, re.I))
    if not matches:
        return 0
    match = matches[-1]
    try:
        value = float(match.group(1).replace(",", "."))
    except (TypeError, ValueError):
        return 0
    explicit_unit = match.group(2)
    unit = (explicit_unit or default_unit or "s").lower()
    if not explicit_unit and str(label or "").lower() in ("p", "sp"):
        unit = "s" if value >= 15 else "min"
    if unit in ("min", "mins", "minute", "minutes", "'"):
        return int(round(value * 60))
    return int(round(value))


def _planned_easy_bookends_s(text, main_start, main_end):
    chunks = []
    offset = 0
    for chunk in re.split(r"\s*//\s*", text or ""):
        start = (text or "").find(chunk, offset)
        end = start + len(chunk) if start >= 0 else offset + len(chunk)
        chunks.append((start, end, chunk))
        offset = end

    before = 0
    after = 0
    for start, end, chunk in chunks:
        seconds = _coach_duration_token_seconds(chunk)
        if seconds is None:
            continue
        if end <= main_start:
            before += seconds
        elif start >= main_end:
            after += seconds
    return before, after


def _planned_easy_bookends_m(text, main_start, main_end):
    chunks = []
    offset = 0
    for chunk in re.split(r"\s*//\s*", text or ""):
        start = (text or "").find(chunk, offset)
        end = start + len(chunk) if start >= 0 else offset + len(chunk)
        chunks.append((start, end, chunk))
        offset = end

    before = 0.0
    after = 0.0
    for start, end, chunk in chunks:
        meters = _coach_distance_token_m(chunk)
        if meters is None:
            continue
        if end <= main_start:
            before += meters
        elif start >= main_end:
            after += meters
    return before, after


def _seconds_label_to_seconds(label):
    parts = [int(part) for part in str(label or "").split(":") if part.isdigit()]
    if len(parts) == 3:
        return parts[0] * 3600 + parts[1] * 60 + parts[2]
    if len(parts) == 2:
        return parts[0] * 60 + parts[1]
    return parts[0] if parts else None


def _first_athlete_attr_value(athlete, names):
    for name in names:
        if hasattr(athlete, name):
            value = getattr(athlete, name, None)
            if value not in (None, ""):
                return name, value
    return None, None


def _watch_pr_seconds_from_attrs(athlete, names):
    name, value = _first_athlete_attr_value(athlete, names)
    if value in (None, ""):
        return None
    if str(name or "").endswith("_s"):
        try:
            seconds = float(value)
        except (TypeError, ValueError):
            seconds = None
        return seconds if seconds and seconds > 0 else None
    try:
        return _parse_pr_time_to_seconds(str(value))
    except ValueError:
        return None


def _watch_t_reference_speeds(athlete):
    distances = {
        "TM": 42195.0,
        "THM": 21097.5,
        "T10": 10000.0,
        "T5": 5000.0,
        "T3": 3000.0,
        "T15": 1500.0,
        "T8": 800.0,
        "T4": 400.0,
    }
    attr_names = {
        "TM": ["pr_tm_s", "pr_tm", "pr_marathon_s", "pr_marathon", "pr_m_s", "pr_m"],
        "THM": ["pr_thm_s", "pr_thm", "pr_half_marathon_s", "pr_half_marathon", "pr_hm_s", "pr_hm"],
        "T10": ["pr_10000_s", "pr_10000", "pr_10k_s", "pr_10k", "pr_t10_s", "pr_t10"],
        "T5": ["pr_5000_s", "pr_5000", "pr_5k_s", "pr_5k", "pr_t5_s", "pr_t5"],
        "T3": ["pr_3000_s", "pr_3000", "pr_3k_s", "pr_3k", "pr_t3_s", "pr_t3"],
        "T15": ["pr_1500_s", "pr_1500", "pr_t15_s", "pr_t15"],
        "T8": ["pr_800_s", "pr_800", "pr_t8_s", "pr_t8"],
        "T4": ["pr_t4_s", "pr_t4", "pr_400_s", "pr_400"],
    }
    speeds = {}
    for label, names in attr_names.items():
        seconds = _watch_pr_seconds_from_attrs(athlete, names)
        distance_m = distances.get(label)
        if seconds and distance_m:
            speeds[label] = distance_m / float(seconds)
    return speeds


def _watch_z_reference_speeds(athlete):
    try:
        raw = athlete.get_zone_speed_mps()
    except Exception:
        raw = getattr(athlete, "zone_speed_mps", {}) or {}
    speeds = {}
    if isinstance(raw, dict):
        for zone in ["1", "2", "3", "4", "5", "6"]:
            try:
                speed = float(raw.get(zone) or raw.get(str(zone)) or 0)
            except (TypeError, ValueError):
                speed = 0
            if speed > 0:
                speeds[f"Z{zone}"] = speed
    return speeds


def _closest_watch_label(speed_mps, references):
    if not speed_mps or not references:
        return ""
    return min(references.items(), key=lambda item: abs(float(item[1]) - float(speed_mps)))[0]


def _threshold_watch_label(speed_mps, references):
    if not speed_mps or not references:
        return ""
    thresholds = []
    for label, reference_speed in references.items():
        try:
            reference_speed = float(reference_speed)
        except (TypeError, ValueError):
            continue
        if reference_speed > 0:
            thresholds.append((reference_speed, label))
    thresholds.sort()
    selected = ""
    for reference_speed, label in thresholds:
        if float(speed_mps) + 1e-9 >= reference_speed:
            selected = label
        else:
            break
    return selected


def _km_label(value_m):
    km = float(value_m or 0) / 1000.0
    return f"{km:.1f}"


def _watch_split_display_speed(split, duration_s, distance_m):
    pace_s = _pace_label_seconds_per_km((split or {}).get("pace") or "")
    if pace_s and pace_s > 0:
        return 1000.0 / float(pace_s)
    return distance_m / duration_s if duration_s > 0 and distance_m > 0 else 0.0


def _watch_zone_totals_summary(athlete, splits):
    z_refs = _watch_z_reference_speeds(athlete)
    t_refs = _watch_t_reference_speeds(athlete)
    if not z_refs and not t_refs:
        return ""

    z_totals = {}
    t_totals = {}
    for split in splits or []:
        duration_s = float(split.get("duration_s") or _seconds_label_to_seconds(split.get("duration") or "") or 0)
        distance_m = float(split.get("distance_m") or 0)
        if duration_s <= 0 or distance_m <= 0:
            continue
        speed = _watch_split_display_speed(split, duration_s, distance_m)
        z_label = _closest_watch_label(speed, z_refs)
        t_label = _threshold_watch_label(speed, t_refs)
        if z_label:
            z_totals[z_label] = z_totals.get(z_label, 0.0) + distance_m
        if t_label:
            t_totals[t_label] = t_totals.get(t_label, 0.0) + distance_m

    lines = []
    if z_totals:
        zone_order = ["Z1", "Z2", "Z3", "Z4", "Z5", "Z6"]
        lines.append(", ".join(f"{label} {_km_label(z_totals[label])}" for label in zone_order if z_totals.get(label)))
    if t_totals:
        t_order = ["TM", "THM", "T10", "T5", "T3", "T15", "T8", "T4"]
        lines.append(", ".join(f"{label} {_km_label(t_totals[label])}" for label in t_order if t_totals.get(label)))
    return "\n".join(lines)


def _watch_activity_zone_totals_from_samples(athlete, activities, split_m=50.0):
    if not athlete:
        return "", ""
    best = None
    for activity in activities or []:
        source, splits = _polar_splits_for_distance(activity.get("raw") or {}, split_m, max_count=None)
        if not splits:
            continue
        distance_m = float(activity.get("distance_m") or 0)
        if distance_m <= 0:
            distance_m = sum(float(split.get("distance_m") or 0) for split in splits)
        if best is None or distance_m > best["distance_m"]:
            best = {
                "activity_id": activity.get("id") or "",
                "distance_m": distance_m,
                "source": source,
                "splits": splits,
            }
    if not best:
        return "", ""
    return best["activity_id"], _watch_zone_totals_summary(athlete, best["splits"])


def _rep_times_text(splits, limit=40):
    times = [split.get("duration") for split in splits if split.get("duration")]
    if len(times) <= limit:
        return ", ".join(times)
    return ", ".join(times[:limit]) + f", +{len(times) - limit} more"


def _watch_split_brief(split):
    return {
        "label": split.get("label") or "",
        "distance_m": split.get("distance_m"),
        "duration": split.get("duration") or "",
        "pace": split.get("pace") or "",
    }


def _block_from_equal_splits(splits, start_index, distance_m):
    if not splits:
        return None
    try:
        split_m = float(splits[0].get("distance_m") or 0)
    except (TypeError, ValueError):
        split_m = 0.0
    if split_m <= 0:
        return None

    remaining = float(distance_m or 0)
    cursor = int(start_index)
    duration_s = 0.0
    used_m = 0.0
    while remaining > 0 and cursor < len(splits):
        split = splits[cursor]
        split_duration_s = _seconds_label_to_seconds(split.get("duration") or "")
        if split_duration_s is None:
            return None
        take_m = min(split_m, remaining)
        duration_s += float(split_duration_s) * (take_m / split_m)
        used_m += take_m
        remaining -= take_m
        cursor += 1

    if remaining > 1:
        return None
    return {
        "distance_m": round(used_m),
        "duration": _format_seconds_hms(round(duration_s)),
        "pace": _format_pace(duration_s, used_m),
        "start_m": round(start_index * split_m),
        "end_m": round(start_index * split_m + used_m),
        "next_index": cursor,
        "duration_s": duration_s,
    }


def _block_from_duration_splits(splits, start_index, duration_target_s):
    if not splits:
        return None
    try:
        split_m = float(splits[0].get("distance_m") or 0)
    except (TypeError, ValueError):
        split_m = 0.0
    if split_m <= 0:
        return None

    remaining = float(duration_target_s or 0)
    cursor = int(start_index)
    used_s = 0.0
    used_m = 0.0
    while remaining > 0 and cursor < len(splits):
        split = splits[cursor]
        split_duration_s = _seconds_label_to_seconds(split.get("duration") or "")
        if not split_duration_s:
            return None
        take_s = min(float(split_duration_s), remaining)
        used_s += take_s
        used_m += split_m * (take_s / float(split_duration_s))
        remaining -= take_s
        cursor += 1

    if remaining > 1:
        return None
    return {
        "distance_m": round(used_m),
        "duration": _format_seconds_hms(round(used_s)),
        "pace": _format_pace(used_s, used_m),
        "start_m": round(start_index * split_m),
        "end_m": round(start_index * split_m + used_m),
        "next_index": cursor,
        "duration_s": used_s,
    }


def _skip_duration_splits(splits, start_index, duration_target_s, label):
    if not duration_target_s:
        return {"next_index": int(start_index), "block": None}
    block = _block_from_duration_splits(splits, start_index, duration_target_s)
    if not block:
        return None
    return {
        "next_index": int(block["next_index"]),
        "block": {
            "type": "recovery",
            "label": label,
            "duration": block["duration"],
            "duration_s": block.get("duration_s") or "",
            "distance_m": block["distance_m"],
            "pace": block["pace"],
            "start_m": block["start_m"],
            "end_m": block["end_m"],
        },
    }


def _distance_at_elapsed(points, target_s):
    if not points:
        return None
    target_s = float(target_s or 0)
    points = sorted(points, key=lambda item: item[0])
    if target_s <= points[0][0]:
        return float(points[0][1])
    for index in range(1, len(points)):
        t1, d1 = points[index - 1]
        t2, d2 = points[index]
        if t2 < target_s:
            continue
        if t2 <= t1:
            return float(d2)
        return float(d1) + ((target_s - t1) / (t2 - t1)) * (float(d2) - float(d1))
    return float(points[-1][1])


def _elapsed_at_distance(points, target_m):
    if not points:
        return None
    target_m = float(target_m or 0)
    points = sorted(points, key=lambda item: item[0])
    if target_m <= points[0][1]:
        return float(points[0][0])
    for index in range(1, len(points)):
        t1, d1 = points[index - 1]
        t2, d2 = points[index]
        if d2 < target_m:
            continue
        if d2 <= d1:
            return float(t2)
        return float(t1) + ((target_m - d1) / (d2 - d1)) * (float(t2) - float(t1))
    return None


def _duration_block_from_points(points, start_s, duration_s):
    end_s = float(start_s or 0) + float(duration_s or 0)
    start_m = _distance_at_elapsed(points, start_s)
    end_m = _distance_at_elapsed(points, end_s)
    if start_m is None or end_m is None:
        return None
    used_m = max(0.0, end_m - start_m)
    return {
        "distance_m": round(used_m),
        "duration": _format_seconds_hms(round(duration_s)),
        "pace": _format_pace(duration_s, used_m),
        "start_m": round(start_m),
        "end_m": round(end_m),
        "duration_s": float(duration_s or 0),
    }


def _distance_block_from_points(points, start_s, distance_m):
    start_s = float(start_s or 0)
    distance_m = float(distance_m or 0)
    if distance_m <= 0:
        return None
    start_m = _distance_at_elapsed(points, start_s)
    if start_m is None:
        return None
    end_m = start_m + distance_m
    end_s = _elapsed_at_distance(points, end_m)
    if end_s is None or end_s <= start_s:
        return None
    duration_s = end_s - start_s
    return {
        "distance_m": round(distance_m),
        "duration": _format_seconds_hms(round(duration_s)),
        "pace": _format_pace(duration_s, distance_m),
        "start_m": round(start_m),
        "end_m": round(end_m),
        "start_s": round(start_s),
        "end_s": round(end_s),
        "duration_s": duration_s,
    }


def _candidate_sequences_from_duration_points(points, structure, activity_duration_s=None, max_sequences=3):
    if not points or not structure or structure.get("pattern_type") != "duration":
        return []
    pattern = structure.get("pattern_s") or []
    sets = int(structure.get("sets") or 0)
    if not pattern or sets <= 0:
        return []

    pause_s = int(structure.get("pause_s") or 0)
    set_pause_s = int(structure.get("set_pause_s") or 0)
    lead_in_s = int(structure.get("lead_in_s") or 0)
    lead_out_s = int(structure.get("lead_out_s") or 0)
    core_s = sets * sum(int(item or 0) for item in pattern)
    recovery_s = (sets * max(0, len(pattern) - 1) * pause_s) + (max(0, sets - 1) * set_pause_s)
    planned_total_s = lead_in_s + core_s + recovery_s + lead_out_s
    if planned_total_s <= 0:
        return []

    points = sorted(points, key=lambda item: item[0])
    final_time_s = float(activity_duration_s or points[-1][0] or 0)
    latest_start_s = max(0, min(180, int(final_time_s - planned_total_s + 60)))
    step_s = 5 if latest_start_s <= 60 else 10
    candidates = []

    for offset_s in range(0, latest_start_s + 1, step_s):
        cursor_s = float(offset_s)
        sequence = []
        recovery_blocks = []
        if offset_s > 0:
            pre_block = _duration_block_from_points(points, 0, offset_s)
            if pre_block and float(pre_block.get("distance_m") or 0) > 0:
                pre_block.update({"type": "recovery", "label": "extra before planned structure"})
                recovery_blocks.append(pre_block)
        if lead_in_s:
            lead_block = _duration_block_from_points(points, cursor_s, lead_in_s)
            if lead_block:
                lead_block.update({"type": "recovery", "label": "lead-in/easy"})
                recovery_blocks.append(lead_block)
            cursor_s += lead_in_s

        total_work_s = 0.0
        total_work_m = 0.0
        ok = True
        for set_number in range(1, sets + 1):
            for rep_number, duration_s in enumerate(pattern, start=1):
                block = _duration_block_from_points(points, cursor_s, duration_s)
                if not block:
                    ok = False
                    break
                block.update({
                    "set": set_number,
                    "rep": rep_number,
                    "planned_duration": _format_seconds_hms(int(duration_s)),
                })
                sequence.append(block)
                total_work_s += float(duration_s or 0)
                total_work_m += float(block.get("distance_m") or 0)
                cursor_s += float(duration_s or 0)

                if rep_number < len(pattern) and pause_s:
                    recovery = _duration_block_from_points(points, cursor_s, pause_s)
                    if recovery:
                        recovery.update({"type": "recovery", "label": f"Set {set_number} recovery after rep {rep_number}"})
                        recovery_blocks.append(recovery)
                    cursor_s += pause_s
            if not ok:
                break
            if set_number < sets and set_pause_s:
                recovery = _duration_block_from_points(points, cursor_s, set_pause_s)
                if recovery:
                    recovery.update({"type": "recovery", "label": f"Recovery between set {set_number} and {set_number + 1}"})
                    recovery_blocks.append(recovery)
                cursor_s += set_pause_s
        if not ok or not sequence:
            continue
        if lead_out_s:
            lead_out = _duration_block_from_points(points, cursor_s, lead_out_s)
            if lead_out:
                lead_out.update({"type": "recovery", "label": "lead-out/easy"})
                recovery_blocks.append(lead_out)
            cursor_s += lead_out_s
        if cursor_s > final_time_s + 30:
            continue
        trailing_s = final_time_s - cursor_s
        if trailing_s > 10:
            trailing = _duration_block_from_points(points, cursor_s, trailing_s)
            if trailing and float(trailing.get("distance_m") or 0) > 0:
                trailing.update({"type": "recovery", "label": "extra after planned structure"})
                recovery_blocks.append(trailing)
        candidates.append({
            "start_s": offset_s,
            "end_s": round(cursor_s),
            "start_m": sequence[0]["start_m"],
            "end_m": sequence[-1]["end_m"],
            "average_pace": _format_pace(total_work_s, total_work_m),
            "total_duration": _format_seconds_hms(round(total_work_s)),
            "recovery_blocks": recovery_blocks[:20],
            "blocks": sequence,
        })

    return sorted(candidates, key=lambda item: abs(float(item.get("start_s") or 0)))[:max_sequences]


def _candidate_sequences_from_distance_points(points, structure, activity_duration_s=None, max_sequences=3):
    if not points or not structure or structure.get("pattern_type") != "distance":
        return []
    pattern = structure.get("pattern_m") or []
    sets = int(structure.get("sets") or 0)
    if not pattern or sets <= 0:
        return []

    pause_s = int(structure.get("pause_s") or 0)
    set_pause_s = int(structure.get("set_pause_s") or 0)
    lead_in_m = float(structure.get("lead_in_m") or 0)
    lead_out_m = float(structure.get("lead_out_m") or 0)
    if not pause_s and not set_pause_s:
        return []

    points = sorted(points, key=lambda item: item[0])
    final_time_s = float(activity_duration_s or points[-1][0] or 0)
    total_distance_m = float(points[-1][1] or 0)

    start_s = _elapsed_at_distance(points, lead_in_m) if lead_in_m > 0 else 0.0
    if start_s is None:
        return []

    sequence = []
    recovery_blocks = []
    if lead_in_m > 0:
        lead_in = _duration_block_from_points(points, 0, start_s)
        if lead_in:
            lead_in.update({"type": "recovery", "label": "lead-in/easy"})
            recovery_blocks.append(lead_in)

    cursor_s = float(start_s)
    total_work_s = 0.0
    total_work_m = 0.0
    ok = True
    for set_number in range(1, sets + 1):
        for rep_number, distance_m in enumerate(pattern, start=1):
            block = _distance_block_from_points(points, cursor_s, distance_m)
            if not block:
                ok = False
                break
            block.update({"set": set_number, "rep": rep_number})
            sequence.append(block)
            total_work_s += float(block.get("duration_s") or 0)
            total_work_m += float(block.get("distance_m") or 0)
            cursor_s = float(block.get("end_s") or cursor_s)

            if rep_number < len(pattern) and pause_s:
                recovery = _duration_block_from_points(points, cursor_s, pause_s)
                if recovery:
                    recovery.update({"type": "recovery", "label": f"Set {set_number} recovery after rep {rep_number}"})
                    recovery_blocks.append(recovery)
                cursor_s += pause_s
        if not ok:
            break
        if set_number < sets and set_pause_s:
            recovery = _duration_block_from_points(points, cursor_s, set_pause_s)
            if recovery:
                recovery.update({"type": "recovery", "label": f"Recovery between set {set_number} and {set_number + 1}"})
                recovery_blocks.append(recovery)
            cursor_s += set_pause_s
    if not ok or not sequence or cursor_s > final_time_s + 30:
        return []

    if lead_out_m > 0:
        remaining_after_m = total_distance_m - float(sequence[-1].get("end_m") or 0)
        if remaining_after_m < (lead_out_m * 0.65):
            return []
        lead_out_end_s = _elapsed_at_distance(points, min(total_distance_m, float(sequence[-1].get("end_m") or 0) + lead_out_m))
        if lead_out_end_s and lead_out_end_s > cursor_s:
            lead_out = _duration_block_from_points(points, cursor_s, lead_out_end_s - cursor_s)
            if lead_out:
                lead_out.update({"type": "recovery", "label": "lead-out/easy"})
                recovery_blocks.append(lead_out)
            cursor_s = lead_out_end_s

    trailing_s = final_time_s - cursor_s
    if trailing_s > 10:
        trailing = _duration_block_from_points(points, cursor_s, trailing_s)
        if trailing and float(trailing.get("distance_m") or 0) > 0:
            trailing.update({"type": "recovery", "label": "extra after planned structure"})
            recovery_blocks.append(trailing)

    return [{
        "start_s": round(start_s),
        "end_s": round(cursor_s),
        "start_m": sequence[0]["start_m"],
        "end_m": sequence[-1]["end_m"],
        "average_pace": _format_pace(total_work_s, total_work_m),
        "total_duration": _format_seconds_hms(round(total_work_s)),
        "recovery_blocks": recovery_blocks[:20],
        "blocks": sequence,
    }][:max_sequences]


def _candidate_sequences_from_structure(splits, structure, max_sequences=6, activity_distance_m=None):
    if not splits or not structure:
        return []

    pattern = structure.get("pattern_m") or structure.get("pattern_s") or []
    sets = int(structure.get("sets") or 0)
    if not pattern or sets <= 0:
        return []
    pattern_type = structure.get("pattern_type") or ("duration" if structure.get("pattern_s") else "distance")

    try:
        split_m = float(splits[0].get("distance_m") or 0)
    except (TypeError, ValueError):
        split_m = 0.0
    if split_m <= 0:
        return []

    total_core_m = float(structure.get("core_distance_m") or 0)
    total_core_s = float(structure.get("core_duration_s") or 0)
    pause_s = int(structure.get("pause_s") or 0)
    set_pause_s = int(structure.get("set_pause_s") or 0)
    lead_in_s = int(structure.get("lead_in_s") or 0)
    lead_in_m = float(structure.get("lead_in_m") or 0)
    lead_out_m = float(structure.get("lead_out_m") or 0)
    try:
        total_activity_m = float(activity_distance_m or 0)
    except (TypeError, ValueError):
        total_activity_m = 0.0
    if total_activity_m <= 0:
        total_activity_m = len(splits) * split_m
    if total_core_m <= 0 and pattern_type == "distance":
        total_core_m = float(sets * sum(pattern))
    if total_core_s <= 0 and pattern_type == "duration":
        total_core_s = float(sets * sum(pattern))
    distance_for_window_m = total_core_m if total_core_m > 0 else (len(splits) * split_m * 0.75)
    max_start_index = (
        max(0, len(splits) - 1)
        if pattern_type == "duration"
        else max(0, int((total_activity_m - lead_out_m - distance_for_window_m) // split_m))
    )
    candidates = []

    for start_index in range(0, max_start_index + 1):
        cursor = start_index
        sequence = []
        recovery_blocks = []
        total_duration_s = 0.0
        ok = True

        lead_skip = _skip_duration_splits(splits, cursor, lead_in_s, "lead-in/easy")
        if lead_skip is None:
            continue
        cursor = int(lead_skip["next_index"])
        if lead_skip.get("block"):
            recovery_blocks.append(lead_skip["block"])

        for set_number in range(1, sets + 1):
            for rep_number, distance_m in enumerate(pattern, start=1):
                block = (
                    _block_from_duration_splits(splits, cursor, distance_m)
                    if pattern_type == "duration"
                    else _block_from_equal_splits(splits, cursor, distance_m)
                )
                if not block:
                    ok = False
                    break
                sequence.append({
                    "set": set_number,
                    "rep": rep_number,
                    "planned_duration": _format_seconds_hms(int(distance_m)) if pattern_type == "duration" else "",
                    "distance_m": block["distance_m"],
                    "duration": block["duration"],
                    "duration_s": block.get("duration_s") or "",
                    "pace": block["pace"],
                    "start_m": block["start_m"],
                    "end_m": block["end_m"],
                })
                total_duration_s += float(block.get("duration_s") or 0)
                cursor = int(block["next_index"])

                if rep_number < len(pattern) and pause_s:
                    skipped = _skip_duration_splits(splits, cursor, pause_s, f"Set {set_number} recovery after rep {rep_number}")
                    if skipped is None:
                        ok = False
                        break
                    cursor = int(skipped["next_index"])
                    if skipped.get("block"):
                        recovery_blocks.append(skipped["block"])
            if not ok:
                break
            if set_number < sets and set_pause_s:
                skipped = _skip_duration_splits(splits, cursor, set_pause_s, f"Recovery between set {set_number} and {set_number + 1}")
                if skipped is None:
                    ok = False
                    break
                cursor = int(skipped["next_index"])
                if skipped.get("block"):
                    recovery_blocks.append(skipped["block"])
        if not ok or not sequence:
            continue
        if pattern_type == "distance" and lead_out_m > 0:
            remaining_after_m = total_activity_m - float(sequence[-1].get("end_m") or 0)
            if remaining_after_m < (lead_out_m * 0.75):
                continue
        candidates.append({
            "start_m": round(start_index * split_m),
            "end_m": sequence[-1]["end_m"],
            "average_pace": _format_pace(total_duration_s, total_core_m or (sequence[-1]["end_m"] - sequence[0]["start_m"])),
            "total_duration": _format_seconds_hms(round(total_duration_s)),
            "recovery_blocks": recovery_blocks[:20],
            "blocks": sequence,
        })

    def _candidate_score(candidate):
        blocks = candidate.get("blocks") or []
        work_seconds = []
        for block in blocks:
            try:
                duration = float(block.get("duration_s") or _seconds_label_to_seconds(block.get("duration") or "") or 0)
            except (TypeError, ValueError):
                duration = 0.0
            if duration > 0:
                work_seconds.append(duration)
        seconds = sum(work_seconds) if work_seconds else (_seconds_label_to_seconds(candidate.get("total_duration") or "") or 999999)
        if work_seconds:
            sorted_work = sorted(work_seconds)
            median_work = sorted_work[len(sorted_work) // 2]
            variability = sum(abs(duration - median_work) for duration in work_seconds) / float(len(work_seconds))
            first_outlier = max(0.0, work_seconds[0] - median_work) if len(work_seconds) > 2 else 0.0
        else:
            median_work = 0.0
            variability = 999999.0
            first_outlier = 999999.0

        recovery_seconds = []
        recovery_m = 0.0
        for block in candidate.get("recovery_blocks") or []:
            label = str(block.get("label") or "").lower()
            if "recovery after rep" not in label:
                continue
            try:
                duration = float(block.get("duration_s") or _seconds_label_to_seconds(block.get("duration") or "") or 0)
            except (TypeError, ValueError):
                duration = 0.0
            if duration > 0:
                recovery_seconds.append(duration)
                try:
                    recovery_m += float(block.get("distance_m") or 0)
                except (TypeError, ValueError):
                    pass
        avg_recovery_s = sum(recovery_seconds) / float(len(recovery_seconds)) if recovery_seconds else 0.0
        recovery_penalty = abs(avg_recovery_s - float(pause_s)) if pause_s and avg_recovery_s else 0.0
        try:
            work_m = sum(float(block.get("distance_m") or 0) for block in blocks)
        except (TypeError, ValueError):
            work_m = 0.0
        work_speed = work_m / seconds if work_m > 0 and seconds > 0 else 0.0
        recovery_speed = recovery_m / sum(recovery_seconds) if recovery_m > 0 and recovery_seconds else 0.0
        contrast_penalty = 0.0
        if work_speed and recovery_speed:
            contrast_penalty = max(0.0, recovery_speed - (work_speed * 0.92)) * 100.0
        expected_start_m = lead_in_m if lead_in_m else (0.0 if lead_in_s else 2000.0)
        if lead_in_s:
            lead_blocks = candidate.get("recovery_blocks") or []
            if lead_blocks:
                expected_start_m = float(lead_blocks[0].get("start_m") or 0)
        start_penalty = abs(float(candidate.get("start_m") or 0) - expected_start_m) / max(split_m, 1.0)
        return (
            round(first_outlier, 3),
            round(variability, 3),
            round(contrast_penalty, 3),
            round(recovery_penalty, 3),
            round(start_penalty, 3),
            seconds,
        )

    return sorted(candidates, key=_candidate_score)[:max_sequences]


def _watch_activity_ai_payload(activity, planned_structure=None, max_splits=160):
    raw = activity.get("raw") or {}
    source, splits = _polar_splits_for_distance(raw, 100.0, max_count=max_splits)
    if not splits:
        source, splits = _polar_splits_for_distance(raw, 200.0, max_count=max_splits)
    if not splits:
        split_info = _polar_exercise_splits(raw)
        source = split_info.get("source") or ""
        splits = split_info.get("splits") or []

    split_payload = [_watch_split_brief(split) for split in splits[:max_splits]]
    candidate_sequences = []
    point_source = ""
    point_count = 0
    if planned_structure and planned_structure.get("pattern_type") in ("duration", "distance"):
        point_source, points = _time_distance_points_from_exercise(raw)
        point_count = len(points or [])
        if planned_structure.get("pattern_type") == "duration":
            candidate_sequences = _candidate_sequences_from_duration_points(
                points,
                planned_structure,
                activity_duration_s=activity.get("duration_seconds"),
            )
        else:
            candidate_sequences = _candidate_sequences_from_distance_points(
                points,
                planned_structure,
                activity_duration_s=activity.get("duration_seconds"),
            )
    payload = {
        "id": activity.get("id") or "",
        "start_time": activity.get("start_time") or "",
        "sport": activity.get("sport") or "",
        "duration": activity.get("duration_label") or activity.get("duration") or "",
        "duration_seconds": activity.get("duration_seconds"),
        "distance_m": round(activity.get("distance_m") or 0),
        "distance_km": activity.get("distance_km"),
        "avg_hr": activity.get("avg_hr"),
        "max_hr": activity.get("max_hr"),
        "split_source": source,
        "splits": split_payload,
        "splits_truncated": len(splits) > max_splits,
        "point_source": point_source,
        "point_count": point_count,
    }
    if planned_structure:
        payload["candidate_sequences"] = candidate_sequences or _candidate_sequences_from_structure(
            split_payload,
            planned_structure,
            activity_distance_m=activity.get("distance_m"),
        )
    return payload


def _clean_ai_suggestion_text(value, max_len=1800):
    text = str(value or "").strip()
    if len(text) > max_len:
        return text[:max_len].rstrip() + "..."
    return text


def _normalise_ai_watch_suggestion(data, fallback_activity_id=""):
    if not isinstance(data, dict):
        return None

    title = _clean_ai_suggestion_text(data.get("title") or "AI watch suggestion", max_len=180)
    summary = _clean_ai_suggestion_text(data.get("summary") or "", max_len=1800)
    if not summary:
        return None

    splits = []
    for index, item in enumerate(data.get("splits") or [], start=1):
        if not isinstance(item, dict):
            continue
        label = _clean_ai_suggestion_text(item.get("label") or f"Rep {index}", max_len=80)
        duration = _clean_ai_suggestion_text(item.get("duration") or item.get("time") or "", max_len=40)
        pace = _clean_ai_suggestion_text(item.get("pace") or "", max_len=40)
        try:
            distance_m = round(float(item.get("distance_m") or item.get("planned_m") or 0))
        except (TypeError, ValueError):
            distance_m = 0
        splits.append({
            "label": label,
            "distance_m": distance_m or "",
            "duration": duration,
            "pace": pace,
        })
        if len(splits) >= 80:
            break

    try:
        confidence = float(data.get("confidence"))
    except (TypeError, ValueError):
        confidence = None

    return {
        "mode": "ai",
        "activity_id": data.get("activity_id") or fallback_activity_id or "ai-watch-suggestion",
        "title": title,
        "summary": summary,
        "splits": splits,
        "confidence": confidence,
        "ai": True,
    }


def _pace_label_seconds_per_km(label):
    match = re.search(r"(\d{1,2}):(\d{2})(?=\s*/\s*km\b)", str(label or ""), flags=re.I)
    if not match:
        return None
    return (int(match.group(1)) * 60) + int(match.group(2))


def _split_with_inferred_watch_values(split):
    item = dict(split or {})
    duration_s = item.get("duration_s")
    if duration_s in (None, ""):
        duration_s = _seconds_label_to_seconds(item.get("duration") or "")
    try:
        duration_s = float(duration_s or 0)
    except (TypeError, ValueError):
        duration_s = 0.0

    try:
        distance_m = float(item.get("distance_m") or 0)
    except (TypeError, ValueError):
        distance_m = 0.0

    pace_s = _pace_label_seconds_per_km(item.get("pace") or "")
    inferred_m = 0.0
    if duration_s > 0 and pace_s and pace_s > 0:
        inferred_m = duration_s * 1000.0 / float(pace_s)
    if distance_m <= 0 and inferred_m > 0:
        distance_m = inferred_m
    elif distance_m > 0 and inferred_m > 0:
        conflict_ratio = abs(distance_m - inferred_m) / max(distance_m, inferred_m)
        if conflict_ratio > 0.35:
            distance_m = inferred_m

    if duration_s <= 0 and distance_m > 0 and pace_s and pace_s > 0:
        duration_s = distance_m * float(pace_s) / 1000.0

    if distance_m > 0:
        item["distance_m"] = distance_m
        rounded_m = int(round(distance_m))
        label = str(item.get("label") or "")
        if label and re.search(r"\d+(?:\.\d+)?\s*(?:km|k|m)\b", label, flags=re.I):
            replacement = f"{rounded_m}m"
            item["label"] = re.sub(r"\d+(?:\.\d+)?\s*(?:km|k|m)\b", replacement, label, count=1, flags=re.I)
    if duration_s > 0:
        item["duration_s"] = duration_s
    return item


def _ai_suggestion_total_splits(suggestion, activity_payloads):
    splits = [_split_with_inferred_watch_values(split) for split in (suggestion or {}).get("splits") or []]
    usable_splits = [
        split for split in splits
        if float(split.get("distance_m") or 0) > 0 and float(split.get("duration_s") or 0) > 0
    ]
    if not usable_splits:
        return []

    activity_id = (suggestion or {}).get("activity_id") or ""
    activity = None
    for candidate in activity_payloads or []:
        if activity_id and candidate.get("id") == activity_id:
            activity = candidate
            break
    if activity is None and activity_payloads:
        activity = activity_payloads[0]

    total = list(usable_splits)
    if activity:
        used_m = sum(float(split.get("distance_m") or 0) for split in usable_splits)
        used_s = sum(float(split.get("duration_s") or 0) for split in usable_splits)
        remaining_m = float(activity.get("distance_m") or 0) - used_m
        remaining_s = float(activity.get("duration_seconds") or 0) - used_s
        if remaining_m > 50 and remaining_s > 0:
            total.append({
                "label": "Unmatched easy/recovery",
                "distance_m": remaining_m,
                "duration": _format_seconds_hms(round(remaining_s)),
                "duration_s": remaining_s,
                "pace": _format_pace(remaining_s, remaining_m),
            })
    return total


def _candidate_blocks_as_splits(activity_payloads, expected_reps=0):
    best = None
    for activity in activity_payloads or []:
        for candidate in activity.get("candidate_sequences") or []:
            blocks = candidate.get("blocks") or []
            if expected_reps and len(blocks) != expected_reps:
                continue
            if not blocks:
                continue
            score = _seconds_label_to_seconds(candidate.get("total_duration") or "") or 999999
            if best is None or score < best["score"]:
                best = {
                    "score": score,
                    "activity_id": activity.get("id") or "",
                    "activity": activity,
                    "blocks": blocks,
                    "recovery_blocks": candidate.get("recovery_blocks") or [],
                }

    if not best:
        return "", [], []

    def _split_from_block(block, default_label="Rep"):
        set_number = block.get("set")
        rep_number = block.get("rep")
        planned_duration = block.get("planned_duration") or ""
        label = f"Set {set_number}, Rep {rep_number}" if set_number and rep_number else (block.get("label") or default_label)
        if planned_duration:
            label = f"{label} ({planned_duration})"
        return {
            "label": label,
            "distance_m": block.get("distance_m") or "",
            "duration": block.get("duration") or "",
            "duration_s": block.get("duration_s") or "",
            "pace": block.get("pace") or "",
        }

    splits = [_split_from_block(block) for block in best["blocks"]]
    total_splits = splits + [_split_from_block(block, default_label="Recovery") for block in best["recovery_blocks"]]
    used_m = sum(float(split.get("distance_m") or 0) for split in total_splits)
    used_s = sum(float(split.get("duration_s") or 0) for split in total_splits)
    activity = best.get("activity") or {}
    remaining_m = float(activity.get("distance_m") or 0) - used_m
    remaining_s = float(activity.get("duration_seconds") or 0) - used_s
    if remaining_m > 50 and remaining_s > 0:
        total_splits.append({
            "label": "Unmatched easy/recovery",
            "distance_m": remaining_m,
            "duration": _format_seconds_hms(round(remaining_s)),
            "duration_s": remaining_s,
            "pace": _format_pace(remaining_s, remaining_m),
        })
    return best["activity_id"], splits, total_splits


def _build_structured_watch_suggestion(plan_text, planned_structure, activity_payloads, athlete=None):
    expected_reps = int((planned_structure or {}).get("reps_total") or 0)
    if not expected_reps:
        return None

    activity_id, splits, total_splits = _candidate_blocks_as_splits(activity_payloads, expected_reps=expected_reps)
    if not splits:
        return None

    bits = [
        f"Planned: {plan_text}",
        f"Matched {len(splits)} work reps from the planned pattern",
    ]
    if planned_structure.get("lead_in_s"):
        bits.append(f"lead-in {_format_seconds_hms(int(planned_structure['lead_in_s']))}")
    if planned_structure.get("pause_s"):
        bits.append(f"recovery {_format_seconds_hms(int(planned_structure['pause_s']))} between reps")
    if planned_structure.get("set_pause_s"):
        bits.append(f"set recovery {_format_seconds_hms(int(planned_structure['set_pause_s']))}")
    if planned_structure.get("lead_out_s"):
        bits.append(f"lead-out {_format_seconds_hms(int(planned_structure['lead_out_s']))}")

    zone_totals = _watch_zone_totals_summary(athlete, total_splits) if athlete else ""
    return {
        "mode": "structured",
        "activity_id": activity_id or "structured-watch-suggestion",
        "title": "Structured workout match",
        "summary": " | ".join(bits),
        "splits": splits,
        "zone_totals": zone_totals,
        "confidence": 0.75,
        "ai": False,
    }


def _build_ai_watch_suggestion(plan_text, activities, athlete=None):
    if not plan_text:
        return None, "AI unavailable: no planned training text."
    if not activities:
        return None, "AI unavailable: no watch activities."

    planned_structure = _planned_interval_structure(plan_text)
    activity_payloads = [
        _watch_activity_ai_payload(activity, planned_structure=planned_structure)
        for activity in activities[:3]
    ]
    fallback_activity_id = activity_payloads[0].get("id") if activity_payloads else ""

    structured_suggestion = _build_structured_watch_suggestion(plan_text, planned_structure, activity_payloads, athlete=athlete)
    if structured_suggestion:
        return structured_suggestion, "Structured watch suggestion created."
    if planned_structure:
        expected_reps = int(planned_structure.get("reps_total") or 0)
        sample_activity_id, fallback_zone_totals = _watch_activity_zone_totals_from_samples(athlete, activities)
        diagnostics = []
        for activity in activity_payloads[:1]:
            split_count = len(activity.get("splits") or [])
            point_count = int(activity.get("point_count") or 0)
            point_source = activity.get("point_source") or activity.get("split_source") or "no sample source"
            diagnostics.append(f"sample source: {point_source}, points: {point_count}, 100m splits: {split_count}")
        diagnostic_text = f" | {'; '.join(diagnostics)}" if diagnostics else ""
        return {
            "mode": "structured_unmatched",
            "activity_id": sample_activity_id or fallback_activity_id or "structured-watch-unmatched",
            "title": "Structured workout match",
            "summary": (
                f"Planned: {plan_text} | Mila recognised {expected_reps} planned work reps, "
                f"but could not match them reliably from the watch samples yet.{diagnostic_text}"
            ),
            "splits": [],
            "zone_totals": fallback_zone_totals,
            "confidence": 0.2,
            "ai": False,
        }, "Structured watch match was inconclusive."

    api_key = (os.environ.get("OPENAI_API_KEY") or "").strip()
    if not api_key:
        return None, "AI unavailable: OPENAI_API_KEY is not set."

    model = (os.environ.get("OPENAI_MODEL") or "gpt-4o-mini").strip()
    system_prompt = (
        "You interpret running watch data for a coaching planner. "
        "Match the planned workout text against watch splits. "
        "The input may include warmup, cooldown and recovery jogging. "
        "Return only compact JSON. Do not invent exact precision when confidence is low."
    )
    user_payload = {
        "planned_workout": plan_text,
        "parsed_planned_structure": planned_structure,
        "activities": activity_payloads,
        "task": (
            "Detect whether the watch activity matches the planned workout. "
            "Handle flexible coach notation such as 3*(330m-330m-330m-1050m) z4 p30 sp2. "
            "If parsed_planned_structure is present, use it as the required structure. "
            "For example sets=3 and pattern_m=[330,330,330,1050] means 12 reps total, not 4 reps total. "
            "If pattern_s is present, the planned reps are time-based; report the detected distance, duration and pace per planned time block. "
            "pause_s and set_pause_s are recovery gaps; candidate_sequences already skip them between work reps/sets. "
            "Use recovery_blocks to judge plausibility, but do not report recovery blocks as work reps. "
            "Prefer candidate_sequences when available; choose the most plausible sequence or explain low confidence. "
            "Prefer set/rep summaries over listing every 100m split. "
            "If there is extra distance, label it as warmup/cooldown/recovery/dribble when likely. "
            "Return JSON with keys: title, summary, confidence, activity_id, splits. "
            "splits should list the relevant planned reps compactly, with label, distance_m, duration, pace. "
            "Do not collapse repeated sets into a single set."
        ),
    }
    body = json.dumps({
        "model": model,
        "temperature": 0.1,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)},
        ],
    }).encode("utf-8")

    request = Request(
        "https://api.openai.com/v1/chat/completions",
        data=body,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=30) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        message = f"AI unavailable: OpenAI returned HTTP {exc.code}."
        try:
            raw = exc.read().decode("utf-8")
            payload = json.loads(raw)
            detail = payload.get("error", {}).get("message") if isinstance(payload, dict) else ""
            if detail:
                message = f"{message} {detail}"
        except Exception:
            pass
        return None, message[:500]
    except URLError as exc:
        return None, f"AI unavailable: network error ({exc.reason})."
    except TimeoutError:
        return None, "AI unavailable: OpenAI request timed out."
    except (ValueError, OSError) as exc:
        return None, f"AI unavailable: OpenAI request failed ({exc})."

    try:
        content = payload["choices"][0]["message"]["content"]
        data = json.loads(content)
    except (KeyError, IndexError, TypeError, ValueError):
        return None, "AI unavailable: OpenAI response could not be parsed."

    suggestion = _normalise_ai_watch_suggestion(data, fallback_activity_id=fallback_activity_id)
    if not suggestion:
        return None, "AI unavailable: OpenAI response did not contain a usable suggestion."
    suggestion["splits"] = [_split_with_inferred_watch_values(split) for split in suggestion.get("splits") or []]

    expected_reps = int((planned_structure or {}).get("reps_total") or 0)
    has_candidate_totals = False
    if expected_reps:
        candidate_activity_id, candidate_splits, candidate_total_splits = _candidate_blocks_as_splits(activity_payloads, expected_reps=expected_reps)
        if candidate_splits:
            suggestion["splits"] = candidate_splits
            suggestion["zone_totals"] = _watch_zone_totals_summary(athlete, candidate_total_splits) if athlete else ""
            has_candidate_totals = True
            suggestion["activity_id"] = candidate_activity_id or suggestion.get("activity_id") or fallback_activity_id
            if len(candidate_splits) != len(data.get("splits") or []):
                suggestion["summary"] = (
                    f"{suggestion.get('summary') or ''} "
                    f"Mila kept the structured work-rep list at {len(candidate_splits)} reps from the planned pattern."
                ).strip()
    if athlete and not has_candidate_totals:
        ai_total_splits = _ai_suggestion_total_splits(suggestion, activity_payloads)
        if ai_total_splits:
            suggestion["zone_totals"] = _watch_zone_totals_summary(athlete, ai_total_splits)
    if athlete and not has_candidate_totals and not suggestion.get("zone_totals"):
        sample_activity_id, fallback_zone_totals = _watch_activity_zone_totals_from_samples(athlete, activities)
        if fallback_zone_totals:
            suggestion["zone_totals"] = fallback_zone_totals
            suggestion["activity_id"] = suggestion.get("activity_id") or sample_activity_id or fallback_activity_id
    return suggestion, "AI suggestion created."


def _build_plan_watch_suggestion(plan_text, activities, athlete=None):
    spec = _planned_rep_spec(plan_text)
    if not spec:
        distance_spec = _planned_single_distance_spec(plan_text)
        if not distance_spec:
            return None
        planned_m = float(distance_spec.get("distance_m") or 0)
        best_activity = None
        best_ratio = None
        for activity in activities or []:
            distance_m = float(activity.get("distance_m") or 0)
            duration_s = activity.get("duration_seconds")
            if distance_m <= 0 or not duration_s:
                continue
            ratio = abs(distance_m - planned_m) / max(distance_m, planned_m)
            if ratio <= 0.15 and (best_ratio is None or ratio < best_ratio):
                best_activity = activity
                best_ratio = ratio
        if not best_activity:
            return None
        distance_m = float(best_activity.get("distance_m") or planned_m)
        duration_s = best_activity.get("duration_seconds")
        splits = [{
            "label": "Total",
            "distance_m": round(distance_m),
            "duration": _format_seconds_hms(duration_s),
            "duration_s": duration_s,
            "pace": _format_pace(duration_s, distance_m),
        }]
        return {
            "mode": "direct_distance_activity",
            "activity_id": best_activity.get("id") or "",
            "title": "Mila distance activity match",
            "summary": (
                f"Planned: {plan_text} | Watch activity matched as one continuous run: "
                f"{distance_m / 1000.0:.2f} km in {_format_seconds_hms(duration_s)}."
            ),
            "splits": splits,
            "zone_totals": _watch_zone_totals_summary(athlete, splits) if athlete else "",
            "confidence": 0.95,
            "ai": False,
        }
    rep_distance = spec["distance_m"]
    reps = spec["reps"]
    loose_rep_activities = []
    for activity in activities:
        distance_m = activity.get("distance_m")
        duration_s = activity.get("duration_seconds")
        if distance_m is None or duration_s is None:
            continue
        if rep_distance * 0.75 <= distance_m <= rep_distance * 1.25:
            loose_rep_activities.append(activity)

    if len(loose_rep_activities) >= max(2, min(reps, 3)):
        loose_rep_activities = sorted(loose_rep_activities, key=lambda item: item.get("start_time") or "")[:reps]
        splits = []
        for index, activity in enumerate(loose_rep_activities, start=1):
            duration_s = activity.get("duration_seconds")
            distance_m = activity.get("distance_m") or rep_distance
            splits.append({
                "label": f"Rep {index}",
                "distance_m": round(distance_m),
                "duration": _format_seconds_hms(duration_s),
                "pace": _format_pace(duration_s, distance_m),
            })
        return {
            "mode": "rep_only",
            "title": f"Detected {len(splits)} separate reps around {int(round(rep_distance))}m",
            "summary": f"Planned: {plan_text} | Detected: {len(splits)} reps around {int(round(rep_distance))}m | Rep times: {_rep_times_text(splits)}",
            "splits": splits,
            "zone_totals": _watch_zone_totals_summary(athlete, splits) if athlete else "",
        }

    best = None
    for activity in activities:
        source, splits = _polar_splits_for_distance(activity.get("raw") or {}, rep_distance, max_count=reps)
        if not splits:
            continue
        score = min(len(splits), reps)
        if best is None or score > best["score"]:
            best = {"activity": activity, "source": source, "splits": splits, "score": score}
    if best:
        splits = best["splits"]
        return {
            "mode": "direct_distance_splits",
            "activity_id": best["activity"].get("id") or "",
            "title": f"Mila distance split analysis ({int(round(rep_distance))}m)",
            "summary": (
                f"Planned: {plan_text} | Mila split the watch activity into "
                f"{len(splits)} blocks of {int(round(rep_distance))}m from {best['source']}."
            ),
            "splits": splits,
            "zone_totals": _watch_zone_totals_summary(athlete, splits) if athlete else "",
            "confidence": 0.9,
            "ai": False,
        }
    sample_activity_id, fallback_zone_totals = _watch_activity_zone_totals_from_samples(athlete, activities)
    return {
        "mode": "unclear",
        "activity_id": sample_activity_id or "",
        "title": f"Planned {reps} x {int(round(rep_distance))}m, but no matching split source found",
        "summary": f"Planned: {plan_text} | Watch data found, but no distance/speed/route samples for {int(round(rep_distance))}m reps.",
        "splits": [],
        "zone_totals": fallback_zone_totals,
    }


def _should_use_direct_distance_splits(plan_text, activities):
    spec = _planned_rep_spec(plan_text)
    if not spec:
        distance_spec = _planned_single_distance_spec(plan_text)
        if not distance_spec or not activities:
            return False
        planned_m = float(distance_spec.get("distance_m") or 0)
        if planned_m <= 0:
            return False
        activity_m = max(float(activity.get("distance_m") or 0) for activity in activities or [])
        if activity_m <= 0:
            return False
        return abs(activity_m - planned_m) / max(activity_m, planned_m) <= 0.15
    if not spec or not activities:
        return False
    reps = int(spec.get("reps") or 0)
    rep_distance = float(spec.get("distance_m") or 0)
    planned_m = reps * rep_distance
    if reps <= 0 or rep_distance <= 0 or planned_m <= 0:
        return False
    activity_m = max(float(activity.get("distance_m") or 0) for activity in activities or [])
    if activity_m <= 0:
        return False
    distance_ratio = abs(activity_m - planned_m) / max(activity_m, planned_m)
    return distance_ratio <= 0.15 or reps >= 20


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
    splits_result = request.session.pop("polar_splits_result", None)
    v4_result = request.session.pop("polar_v4_result", None)
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
        "splits_result": splits_result,
        "v4_result": v4_result,
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
def polar_v4_connect_view(request):
    config = _polar_config()
    missing = _polar_missing_config(config)
    if missing:
        return redirect(f"{reverse('polar_integration')}?{urlencode({'error': 'Missing Polar configuration: ' + ', '.join(missing)})}")

    state = secrets.token_urlsafe(32)
    request.session["polar_oauth_state"] = state
    request.session["polar_oauth_flow"] = "v4"
    params = {
        "response_type": "code",
        "client_id": config["client_id"],
        "redirect_uri": config["redirect_uri"],
        "scope": "training_sessions:read",
        "state": state,
    }
    return redirect(f"{POLAR_V4_AUTHORIZATION_URL}?{urlencode(params)}")


def _polar_v4_callback(request, code, config):
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
            POLAR_V4_TOKEN_URL,
            method="POST",
            data=token_body,
            headers=token_headers,
        )
    except RuntimeError as exc:
        return redirect(f"{reverse('polar_integration')}?{urlencode({'error': 'Polar v4 token request failed: ' + str(exc)})}")

    if token_status >= 400:
        polar_message = ""
        if isinstance(token_payload, dict):
            polar_message = token_payload.get("error_description") or token_payload.get("error") or token_payload.get("message") or ""
        error_message = f"Polar v4 token request failed with status {token_status}."
        if polar_message:
            error_message = f"{error_message} {polar_message}"
        return redirect(f"{reverse('polar_integration')}?{urlencode({'error': error_message})}")

    access_token = token_payload.get("access_token", "")
    if not access_token:
        return redirect(f"{reverse('polar_integration')}?{urlencode({'error': 'Polar v4 token response was incomplete.'})}")

    connection, _created = PolarConnection.objects.get_or_create(
        user=request.user,
        defaults={"member_id": f"mila-user-{request.user.id}"},
    )
    _save_polar_v4_token(connection, token_payload)
    return redirect(f"{reverse('polar_integration')}?connected=1")


def _save_polar_v4_token(connection, token_payload):
    connection.v4_access_token = token_payload.get("access_token", "")
    refresh_token = token_payload.get("refresh_token", "")
    if refresh_token:
        connection.v4_refresh_token = refresh_token
    connection.v4_token_type = token_payload.get("token_type", "")
    connection.v4_expires_in = token_payload.get("expires_in")
    connection.v4_scope = token_payload.get("scope", "")
    connection.raw_v4_token_response = token_payload if isinstance(token_payload, dict) else {}
    connection.v4_connected_at = timezone.now()
    connection.status = PolarConnection.STATUS_CONNECTED
    connection.last_error = ""
    connection.save(update_fields=[
        "v4_access_token", "v4_refresh_token", "v4_token_type", "v4_expires_in",
        "v4_scope", "raw_v4_token_response", "v4_connected_at",
        "status", "last_error", "updated_at",
    ])


def _refresh_polar_v4_token(connection):
    if not connection or not connection.v4_refresh_token:
        return False, "No Polar v4 refresh token is available."
    config = _polar_config()
    missing = _polar_missing_config(config)
    if missing:
        return False, "Missing Polar configuration: " + ", ".join(missing)

    token_body = urlencode({
        "grant_type": "refresh_token",
        "refresh_token": connection.v4_refresh_token,
    }).encode("utf-8")
    token_headers = {
        "Accept": "application/json",
        "Content-Type": "application/x-www-form-urlencoded",
        "Authorization": _polar_basic_auth_header(config["client_id"], config["client_secret"]),
    }
    try:
        token_status, token_payload = _polar_json_request(
            POLAR_V4_TOKEN_URL,
            method="POST",
            data=token_body,
            headers=token_headers,
        )
    except RuntimeError as exc:
        return False, str(exc)

    if token_status >= 400:
        polar_message = ""
        if isinstance(token_payload, dict):
            polar_message = token_payload.get("error_description") or token_payload.get("error") or token_payload.get("message") or ""
        message = f"Polar v4 refresh failed with status {token_status}."
        if polar_message:
            message = f"{message} {polar_message}"
        return False, message
    if not isinstance(token_payload, dict) or not token_payload.get("access_token"):
        return False, "Polar v4 refresh response did not contain an access token."
    _save_polar_v4_token(connection, token_payload)
    return True, ""


@login_required
@require_GET
def polar_callback_view(request):
    expected_state = request.session.pop("polar_oauth_state", "")
    oauth_flow = request.session.pop("polar_oauth_flow", "")
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
    if oauth_flow == "v4":
        return _polar_v4_callback(request, code, config)

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
        ("Exercises", _polar_exercises_url(include_detail=True)),
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
@require_http_methods(["POST"])
def polar_splits_view(request):
    selected_target, _targets = _selected_polar_target(request)
    connection = selected_target["connection"] if selected_target else None
    if not connection or not connection.access_token:
        return redirect(f"{reverse('polar_integration')}?{urlencode({'error': 'No Polar account is connected yet.'})}")

    headers = {
        "Accept": "application/json",
        "Authorization": f"Bearer {connection.access_token}",
    }
    try:
        status, payload = _polar_json_request(_polar_exercises_url(include_detail=True), method="GET", headers=headers)
    except RuntimeError as exc:
        error_message = f"Polar splits request failed: {exc}"
        connection.status = PolarConnection.STATUS_ERROR
        connection.last_error = error_message
        connection.save(update_fields=["status", "last_error", "updated_at"])
        return redirect(f"{reverse('polar_integration')}?{urlencode({'error': error_message})}")

    if status >= 400:
        polar_message = ""
        if isinstance(payload, dict):
            polar_message = payload.get("error_description") or payload.get("error") or ""
        error_message = f"Polar splits request failed with status {status}."
        if polar_message:
            error_message = f"{error_message} {polar_message}"
        connection.status = PolarConnection.STATUS_ERROR
        connection.last_error = error_message
        connection.save(update_fields=["status", "last_error", "updated_at"])
        return redirect(f"{reverse('polar_integration')}?{urlencode({'error': error_message})}")

    rows = []
    if isinstance(payload, list):
        rows = [_polar_exercise_splits(item) for item in payload if isinstance(item, dict)]

    request.session["polar_splits_result"] = {
        "status": status,
        "exercise_count": len(rows),
        "rows": rows,
    }
    connection.status = PolarConnection.STATUS_CONNECTED
    connection.last_error = ""
    connection.save(update_fields=["status", "last_error", "updated_at"])
    return redirect("polar_integration")


@login_required
@require_http_methods(["POST"])
def polar_v4_laps_test_view(request):
    selected_target, _targets = _selected_polar_target(request)
    connection = selected_target["connection"] if selected_target else None
    if not connection or not connection.access_token:
        return redirect(f"{reverse('polar_integration')}?{urlencode({'error': 'No Polar account is connected yet.'})}")
    if not connection.v4_access_token:
        return redirect(f"{reverse('polar_integration')}?{urlencode({'error': 'No Polar v4 account is connected yet. Use Connect Polar v4 first.'})}")

    headers = {
        "Accept": "application/json",
        "Authorization": f"Bearer {connection.v4_access_token}",
    }
    features = ["laps", "pause-times", "statistics", "zones"]
    today = date.today()
    checks = []
    found_sessions = []
    error_message = ""
    last_query = ""
    refreshed_v4_token = False
    date_formats = [
        ("date-time", "{day}T00:00:00"),
        ("date-time-ms", "{day}T00:00:00.000"),
        ("date-time-z", "{day}T00:00:00Z"),
        ("date-time-ms-z", "{day}T00:00:00.000Z"),
        ("date-time-offset", "{day}T00:00:00+00:00"),
        ("date-time-ms-offset", "{day}T00:00:00.000+00:00"),
        ("date-time-compact-offset", "{day}T00:00:00+0000"),
        ("date-only", "{day}"),
    ]

    for offset in range(0, 21):
        day = today - timedelta(days=offset)
        next_day = day + timedelta(days=1)
        for format_label, format_value in date_formats:
            from_value = format_value.format(day=day.isoformat())
            to_value = format_value.format(day=next_day.isoformat())
            params = [("from", from_value), ("to", to_value)]
            params.extend(("features", feature) for feature in features)
            url = f"{POLAR_V4_TRAINING_SESSIONS_URL}?{urlencode(params)}"
            last_query = url

            try:
                status, payload = _polar_json_request(url, method="GET", headers=headers)
            except RuntimeError as exc:
                status = 0
                payload = {"error": str(exc)}
            refreshed_this_request = False
            if status == 401 and not refreshed_v4_token:
                refreshed_v4_token = True
                refresh_ok, refresh_error = _refresh_polar_v4_token(connection)
                if refresh_ok:
                    refreshed_this_request = True
                    headers["Authorization"] = f"Bearer {connection.v4_access_token}"
                    try:
                        status, payload = _polar_json_request(url, method="GET", headers=headers)
                    except RuntimeError as exc:
                        status = 0
                        payload = {"error": str(exc)}
                else:
                    payload = {"error": refresh_error or "Polar v4 token refresh failed."}

            sessions = []
            if isinstance(payload, dict):
                sessions = payload.get("trainingSessions") or payload.get("training-sessions") or payload.get("sessions") or []
            elif isinstance(payload, list):
                sessions = payload
            if not isinstance(sessions, list):
                sessions = []

            manual_laps = 0
            auto_laps = 0
            lap_preview = []
            for session in sessions:
                if not isinstance(session, dict):
                    continue
                laps, auto = _polar_v4_laps_from_session(session)
                manual_laps += len(laps or []) if isinstance(laps, list) else 0
                auto_laps += len(auto or []) if isinstance(auto, list) else 0
                if len(lap_preview) < 30:
                    lap_preview.extend(_polar_v4_lap_preview_rows(laps, limit=30 - len(lap_preview)))

            polar_message = ""
            if isinstance(payload, dict):
                polar_message = payload.get("error_description") or payload.get("message") or payload.get("error") or ""

            checks.append({
                "date": day.isoformat(),
                "format": format_label,
                "status": status,
                "sessions": len(sessions),
                "manual_laps": manual_laps,
                "auto_laps": auto_laps,
                "refreshed": refreshed_this_request,
                "query": url,
            })

            date_parse_error = status == 400 and "from" in str(polar_message).lower() and "datetime" in str(polar_message).lower()
            if date_parse_error:
                continue

            if status >= 400 or status == 0:
                error_message = f"Polar v4 request failed with status {status}."
                if polar_message:
                    error_message = f"{error_message} {polar_message}"
                break

            if sessions:
                found_sessions = sessions
                pretty_payload = json.dumps(payload, indent=2, ensure_ascii=False)
                if len(pretty_payload) > 20000:
                    pretty_payload = pretty_payload[:20000] + "\n... truncated ..."
                request.session["polar_v4_result"] = {
                    "status": status,
                    "date": day.isoformat(),
                    "features": ", ".join(features),
                    "query": last_query,
                    "checks": checks,
                    "session_count": len(sessions),
                    "manual_laps": manual_laps,
                    "auto_laps": auto_laps,
                    "lap_preview": lap_preview,
                    "session_debug": "\n\n".join(_polar_v4_session_debug(session) for session in sessions[:3]),
                    "payload": pretty_payload,
                }
                break
            break
        if found_sessions or error_message:
            break

    if not found_sessions and not error_message and checks:
        all_date_parse_errors = all(
            int(check.get("status") or 0) == 400
            for check in checks
        )
        if all_date_parse_errors:
            error_message = "Polar v4 request failed: none of the tested datetime formats were accepted."

    if not found_sessions and not error_message:
        request.session["polar_v4_result"] = {
            "status": checks[-1]["status"] if checks else "",
            "date": "",
            "features": ", ".join(features),
            "query": last_query,
            "checks": checks,
            "session_count": 0,
            "manual_laps": 0,
            "auto_laps": 0,
            "payload": "No v4 training sessions found in the last 21 days.",
        }

    if error_message:
        request.session["polar_v4_result"] = {
            "status": checks[-1]["status"] if checks else 0,
            "date": checks[-1]["date"] if checks else "",
            "features": ", ".join(features),
            "query": last_query,
            "checks": checks,
            "session_count": 0,
            "manual_laps": 0,
            "auto_laps": 0,
            "payload": json.dumps(payload, indent=2, ensure_ascii=False) if "payload" in locals() else "",
        }
        connection.status = PolarConnection.STATUS_ERROR
        connection.last_error = error_message
        connection.save(update_fields=["status", "last_error", "updated_at"])
        return redirect(f"{reverse('polar_integration')}?{urlencode({'error': error_message})}")

    connection.status = PolarConnection.STATUS_CONNECTED
    connection.last_error = ""
    connection.save(update_fields=["status", "last_error", "updated_at"])
    return redirect("polar_integration")


def _polar_v4_laps_from_session(session):
    if not isinstance(session, dict):
        return [], []
    manual = []
    auto = []

    def collect_from_laps_obj(value):
        if not isinstance(value, dict):
            return
        laps = value.get("laps") or value.get("manualLaps") or value.get("manual-laps") or []
        auto_laps = value.get("autoLaps") or value.get("auto-laps") or []
        if isinstance(laps, list):
            manual.extend(laps)
        if isinstance(auto_laps, list):
            auto.extend(auto_laps)

    collect_from_laps_obj(session.get("laps"))
    exercises = session.get("exercises") if isinstance(session.get("exercises"), list) else []
    for exercise in exercises:
        if isinstance(exercise, dict):
            collect_from_laps_obj(exercise.get("laps"))
    return manual, auto


def _polar_v4_duration_label_from_millis(value):
    try:
        millis = float(value)
    except (TypeError, ValueError):
        return ""
    return _format_seconds_hms(round(millis / 1000.0))


def _polar_v4_pace_label(duration_millis, distance_m):
    try:
        seconds = float(duration_millis) / 1000.0
        distance_m = float(distance_m)
    except (TypeError, ValueError):
        return ""
    return _format_pace(seconds, distance_m) if seconds > 0 and distance_m > 0 else ""


def _polar_v4_lap_preview_rows(laps, limit=30):
    rows = []
    for index, lap in enumerate(laps or [], start=1):
        if not isinstance(lap, dict):
            continue
        duration = (
            _polar_v4_duration_label_from_millis(lap.get("durationMillis"))
            or _polar_v4_duration_label_from_millis(lap.get("duration"))
            or str(lap.get("duration") or "")
        )
        distance = lap.get("distanceMeters", lap.get("distance"))
        pace = _polar_v4_pace_label(lap.get("durationMillis") or lap.get("duration"), distance)
        rows.append({
            "index": index,
            "duration": duration or "-",
            "distance": f"{float(distance) / 1000.0:.2f} km" if distance not in (None, "") else "-",
            "pace": pace or "-",
        })
        if len(rows) >= limit:
            break
    return rows


def _polar_v4_split_from_lap(lap, index):
    if not isinstance(lap, dict):
        return None
    duration_millis = lap.get("durationMillis", lap.get("duration"))
    distance_m = lap.get("distanceMeters", lap.get("distance"))
    try:
        duration_s = float(duration_millis) / 1000.0
        distance_m = float(distance_m)
    except (TypeError, ValueError):
        return None
    if duration_s <= 0 or distance_m <= 0:
        return None
    return {
        "label": f"Lap {index}",
        "distance_m": round(distance_m),
        "duration": _format_seconds_hms(round(duration_s)),
        "duration_s": duration_s,
        "pace": _format_pace(duration_s, distance_m),
    }


def _polar_v4_activity_label(session):
    if not isinstance(session, dict):
        return "Polar v4 activity"
    start_time = session.get("startTime") or session.get("start_time") or ""
    sport = session.get("sport") or ""
    distance_m = session.get("distanceMeters") or session.get("distance")
    duration_ms = session.get("durationMillis") or session.get("duration")
    try:
        distance_label = f"{float(distance_m) / 1000.0:.2f} km"
    except (TypeError, ValueError):
        distance_label = ""
    duration_label = _polar_v4_duration_label_from_millis(duration_ms)
    bits = [str(item) for item in [start_time, sport, distance_label, duration_label] if item]
    return " | ".join(bits) or "Polar v4 activity"


def _build_polar_v4_lap_suggestion(plan_text, sessions, athlete=None):
    best = None
    for session in sessions or []:
        if not isinstance(session, dict):
            continue
        manual_laps, auto_laps = _polar_v4_laps_from_session(session)
        if not manual_laps:
            continue
        splits = []
        for index, lap in enumerate(manual_laps, start=1):
            split = _polar_v4_split_from_lap(lap, index)
            if split:
                splits.append(split)
        if not splits:
            continue
        score = len(splits)
        if best is None or score > best["score"]:
            best = {
                "score": score,
                "session": session,
                "splits": splits,
                "manual_count": len(manual_laps),
                "auto_count": len(auto_laps or []),
            }
    if not best:
        return None

    session = best["session"]
    identifier = session.get("identifier") if isinstance(session.get("identifier"), dict) else {}
    activity_id = identifier.get("id") or session.get("id") or "polar-v4-lap-suggestion"
    total_distance_m = sum(float(split.get("distance_m") or 0) for split in best["splits"])
    total_duration_s = sum(float(split.get("duration_s") or 0) for split in best["splits"])
    summary_bits = []
    if plan_text:
        summary_bits.append(f"Planned: {plan_text}")
    summary_bits.append(
        f"V4 manual laps: {best['manual_count']} laps"
        + (f", {best['auto_count']} auto laps available" if best["auto_count"] else "")
    )
    if total_distance_m > 0 and total_duration_s > 0:
        summary_bits.append(
            f"Total from laps: {total_distance_m / 1000.0:.2f} km in {_format_seconds_hms(round(total_duration_s))}"
        )
    summary_bits.append(_polar_v4_activity_label(session))
    return {
        "mode": "polar_v4_laps",
        "activity_id": f"polar-v4:{activity_id}",
        "title": "V4 lap suggestion",
        "summary": " | ".join(summary_bits),
        "splits": best["splits"],
        "zone_totals": _watch_zone_totals_summary(athlete, best["splits"]) if athlete else "",
        "confidence": 0.98,
        "ai": False,
    }


def _polar_v4_sessions_for_day(connection, target_date):
    if not connection or not connection.v4_access_token:
        return [], "No Polar v4 account is connected."
    headers = {
        "Accept": "application/json",
        "Authorization": f"Bearer {connection.v4_access_token}",
    }
    next_day = target_date + timedelta(days=1)
    params = [
        ("from", f"{target_date.isoformat()}T00:00:00"),
        ("to", f"{next_day.isoformat()}T00:00:00"),
    ]
    for feature in ["laps", "pause-times", "statistics", "zones"]:
        params.append(("features", feature))
    url = f"{POLAR_V4_TRAINING_SESSIONS_URL}?{urlencode(params)}"
    try:
        status, payload = _polar_json_request(url, method="GET", headers=headers)
    except RuntimeError as exc:
        return [], f"Polar v4 sync failed: {exc}"
    if status == 401:
        refresh_ok, refresh_error = _refresh_polar_v4_token(connection)
        if refresh_ok:
            headers["Authorization"] = f"Bearer {connection.v4_access_token}"
            try:
                status, payload = _polar_json_request(url, method="GET", headers=headers)
            except RuntimeError as exc:
                return [], f"Polar v4 sync failed after refresh: {exc}"
        else:
            return [], refresh_error or "Polar v4 token refresh failed."
    if status >= 400:
        polar_message = ""
        if isinstance(payload, dict):
            polar_message = payload.get("error_description") or payload.get("message") or payload.get("error") or ""
        message = f"Polar v4 sync failed with status {status}."
        if polar_message:
            message = f"{message} {polar_message}"
        return [], message
    sessions = []
    if isinstance(payload, dict):
        sessions = payload.get("trainingSessions") or payload.get("training-sessions") or payload.get("sessions") or []
    elif isinstance(payload, list):
        sessions = payload
    return sessions if isinstance(sessions, list) else [], ""


def _polar_v4_session_debug(session):
    if not isinstance(session, dict):
        return "Session debug: session is not an object."

    def describe(value):
        if isinstance(value, list):
            return f"list({len(value)})"
        if isinstance(value, dict):
            return f"dict({len(value)})"
        if value is None:
            return "null"
        return type(value).__name__

    wanted = ("lap", "phase", "split", "segment", "pause", "zone", "route", "sample")
    matches = []

    def walk(value, path="", depth=0):
        if depth > 4:
            return
        if isinstance(value, dict):
            for key, child in value.items():
                child_path = f"{path}.{key}" if path else str(key)
                if any(term in str(key).lower() for term in wanted):
                    matches.append(f"{child_path}: {describe(child)}")
                walk(child, child_path, depth + 1)
        elif isinstance(value, list):
            if value and depth < 4:
                walk(value[0], f"{path}[0]", depth + 1)

    walk(session)
    top_keys = ", ".join(sorted(str(key) for key in session.keys()))
    if not matches:
        matches.append("No lap/phase/split/segment/pause/zone/route/sample keys found.")
    return f"Top keys: {top_keys or '-'}\nCandidates:\n" + "\n".join(matches[:80])


def _polar_activity_debug_summary(raw):
    if not isinstance(raw, dict):
        return "Watch debug: raw activity is not an object."
    top_keys = sorted(str(key) for key in raw.keys())
    samples = raw.get("samples") if isinstance(raw.get("samples"), list) else []
    sample_bits = []
    for sample in samples:
        if not isinstance(sample, dict):
            continue
        sample_type = _polar_sample_type(sample) or "?"
        values = _polar_sample_values(sample)
        sample_bits.append(f"{sample_type}({len(values)})")

    interesting = []
    for key in [
        "laps", "manual_laps", "manual-laps", "automatic_laps", "automatic-laps",
        "phases", "segments", "split_times", "split-times", "zones", "heart_rate_zones",
        "route", "samples",
    ]:
        if key not in raw:
            continue
        value = raw.get(key)
        if isinstance(value, list):
            interesting.append(f"{key}: list({len(value)})")
        elif isinstance(value, dict):
            interesting.append(f"{key}: dict({len(value)})")
        elif value is None:
            interesting.append(f"{key}: null")
        else:
            interesting.append(f"{key}: {type(value).__name__}")

    compact_keys = ", ".join(top_keys[:40])
    if len(top_keys) > 40:
        compact_keys += f", +{len(top_keys) - 40} more"
    return (
        "Watch debug:\n"
        f"top keys: {compact_keys or '-'}\n"
        f"samples: {', '.join(sample_bits) if sample_bits else 'not found'}\n"
        f"lap/phase candidates: {', '.join(interesting) if interesting else 'not found'}"
    )


def _watch_plan_is_clear_mismatch(plan_text, activities, suggestion):
    """Only flag differences that are large enough to be unambiguous."""
    if not plan_text or not activities:
        return False
    suggestion = suggestion or {}
    if suggestion.get("mode") in {"structured_unmatched", "unclear"}:
        return True
    try:
        confidence = float(suggestion.get("confidence"))
    except (TypeError, ValueError):
        confidence = None
    if confidence is not None and confidence < 0.35:
        return True
    structure = _planned_interval_structure(plan_text)
    if structure:
        expected_reps = int(structure.get("reps_total") or 0)
        detected_reps = len(suggestion.get("splits") or [])
        if expected_reps and detected_reps:
            allowed_difference = max(1, round(expected_reps * 0.35))
            if abs(expected_reps - detected_reps) > allowed_difference:
                return True
    distance_spec = _planned_single_distance_spec(plan_text)
    if distance_spec:
        planned_m = float(distance_spec.get("distance_m") or 0)
        measured = [float(item.get("distance_m") or 0) for item in activities]
        measured = [value for value in measured if value > 0]
        if planned_m > 0 and measured:
            closest_m = min(measured, key=lambda value: abs(value - planned_m))
            if abs(closest_m - planned_m) / max(closest_m, planned_m) > 0.4:
                return True
    return False


def _watch_activities_for_plan(plan_text, activities):
    """Keep another sport on the same day out of the plan interpretation."""
    activities = list(activities or [])
    if not activities:
        return []
    text = str(plan_text or "").lower()
    cycling_planned = any(term in text for term in ("cycling", "bike", "biking", "fiets", "fietsen"))

    def sport(activity):
        return str(activity.get("sport") or "").upper()

    if cycling_planned:
        selected = [activity for activity in activities if any(term in sport(activity) for term in ("CYCL", "BIKE"))]
    else:
        selected = [activity for activity in activities if any(term in sport(activity) for term in ("RUN", "JOG"))]
    return selected or activities


def _watch_v4_sessions_for_plan(plan_text, sessions):
    sessions = list(sessions or [])
    if not sessions:
        return []
    text = str(plan_text or "").lower()
    cycling_planned = any(term in text for term in ("cycling", "bike", "biking", "fiets", "fietsen"))

    def sport(session):
        return str(
            session.get("sport") or session.get("sportId") or session.get("sport-id")
            or session.get("detailedSportInfo") or session.get("detailed-sport-info") or ""
        ).upper()

    if cycling_planned:
        selected = [session for session in sessions if any(term in sport(session) for term in ("CYCL", "BIKE"))]
    else:
        selected = [session for session in sessions if any(term in sport(session) for term in ("RUN", "JOG"))]
    return selected or sessions


def _watch_quantile(values, fraction):
    ordered = sorted(float(value) for value in values)
    if not ordered:
        return 0.0
    index = min(len(ordered) - 1, max(0, round((len(ordered) - 1) * fraction)))
    return ordered[index]


def _watch_pace_pattern_suggestion(activity, athlete=None):
    """Detect sustained faster sections from the raw one-second speed curve."""
    raw = activity.get("raw") or {}
    speed_sample = _polar_sample_map(raw).get("1")
    if not speed_sample:
        return None
    rate = _polar_sample_rate(speed_sample)
    raw_speeds = _polar_sample_values(speed_sample)
    speeds = []
    last = 0.0
    for value in raw_speeds:
        try:
            value = float(value)
        except (TypeError, ValueError):
            value = last
        if value < 0 or value > 40:
            value = last
        speeds.append(value)
        last = value
    if len(speeds) < 120:
        return None

    # An 11-second moving average removes brief GPS spikes without erasing a
    # 20-30 second acceleration such as a fast 100 metres.
    radius = max(2, round(5 / rate))
    prefix = [0.0]
    for speed in speeds:
        prefix.append(prefix[-1] + speed)
    smooth = []
    for index in range(len(speeds)):
        start = max(0, index - radius)
        end = min(len(speeds), index + radius + 1)
        smooth.append((prefix[end] - prefix[start]) / max(1, end - start))

    moving = [speed for speed in smooth if speed >= 4]
    if len(moving) < 120:
        return None
    easy_speed = _watch_quantile(moving, 0.3)
    fast_speed = _watch_quantile(moving, 0.9)
    separation = fast_speed - easy_speed
    if separation < max(1.5, easy_speed * 0.12):
        return None
    threshold = easy_speed + separation * 0.58

    runs = []
    run_start = None
    for index, speed in enumerate(smooth + [0.0]):
        is_fast = index < len(smooth) and speed >= threshold
        if is_fast and run_start is None:
            run_start = index
        elif not is_fast and run_start is not None:
            runs.append([run_start, index])
            run_start = None

    # Join very short threshold dips within one acceleration.
    merged = []
    max_gap = max(1, round(10 / rate))
    for start, end in runs:
        if merged and start - merged[-1][1] <= max_gap:
            merged[-1][1] = end
        else:
            merged.append([start, end])
    min_points = max(1, round(12 / rate))
    max_points = max(1, round(8 * 60 / rate))
    fast_runs = [(start, end) for start, end in merged if min_points <= end - start <= max_points]
    if not 3 <= len(fast_runs) <= 30:
        return None

    def block(label, start, end):
        duration_s = max(rate, (end - start) * rate)
        distance_m = sum(max(0.0, speed) * 1000.0 / 3600.0 * rate for speed in speeds[start:end])
        return {
            "label": label,
            "distance_m": round(distance_m),
            "duration": _format_seconds_hms(round(duration_s)),
            "duration_s": duration_s,
            "pace": _format_pace(duration_s, distance_m) if distance_m > 0 else "",
        }

    fast_blocks = [block(f"Fast {index}", start, end) for index, (start, end) in enumerate(fast_runs, 1)]
    recovery_blocks = [
        block(f"Recovery {index}", fast_runs[index - 1][1], fast_runs[index][0])
        for index in range(1, len(fast_runs))
        if fast_runs[index][0] > fast_runs[index - 1][1]
    ]
    fast_distances = [item["distance_m"] for item in fast_blocks]
    fast_durations = [item["duration_s"] for item in fast_blocks]
    recovery_distances = [item["distance_m"] for item in recovery_blocks]
    median_fast_m = _watch_quantile(fast_distances, 0.5)
    median_fast_s = _watch_quantile(fast_durations, 0.5)
    median_recovery_m = _watch_quantile(recovery_distances, 0.5) if recovery_distances else 0
    fast_distance_spread = (
        _watch_quantile(fast_distances, 0.8) - _watch_quantile(fast_distances, 0.2)
    ) / max(1, median_fast_m)
    fast_duration_spread = (
        _watch_quantile(fast_durations, 0.8) - _watch_quantile(fast_durations, 0.2)
    ) / max(1, median_fast_s)
    recovery_spread = 0.0
    if len(recovery_distances) >= 3:
        recovery_spread = (
            _watch_quantile(recovery_distances, 0.8) - _watch_quantile(recovery_distances, 0.2)
        ) / max(1, median_recovery_m)

    # A real repeating fartlek may vary slightly, but a collection ranging
    # from a few seconds to several minutes is ordinary pace variation rather
    # than a reconstructable workout structure.
    if fast_distance_spread > 0.65 or fast_duration_spread > 0.65 or recovery_spread > 1.0:
        return None
    confidence = 0.76 if max(fast_distance_spread, fast_duration_spread) <= 0.35 else 0.62
    summary = f"Detected {len(fast_blocks)} sustained faster sections of about {round(median_fast_m)} m / {_format_seconds_hms(round(median_fast_s))}"
    if median_recovery_m:
        summary += f", with about {round(median_recovery_m)} m recovery between them"
    summary += ". Reconstructed from pace changes; review before use."
    return {
        "mode": "alternative_pace_pattern",
        "activity_id": activity.get("id") or "alternative-watch-pattern",
        "title": "Alternative plan from pace pattern",
        "summary": summary,
        "splits": fast_blocks,
        # Only the faster sections are displayed; totals over just these
        # sections would look like totals for the complete workout.
        "zone_totals": "",
        "confidence": confidence,
        "alternative": True,
        "ai": False,
    }


def _build_alternative_watch_suggestion(activities, v4_sessions=None, athlete=None):
    """Reconstruct a workout concept from watch data, without using the plan."""
    suggestion = _build_polar_v4_lap_suggestion("", v4_sessions or [], athlete=athlete)
    if suggestion:
        suggestion.update({
            "mode": "alternative_reconstruction", "title": "Alternative plan from watch laps",
            "summary": "Reconstructed from Polar manual laps. Review the blocks before using this suggestion.",
            "confidence": 0.85, "alternative": True,
        })
        return suggestion
    patterns = [
        pattern for pattern in (
            _watch_pace_pattern_suggestion(activity, athlete=athlete)
            for activity in activities or []
        ) if pattern
    ]
    if patterns:
        return max(patterns, key=lambda item: (item.get("confidence") or 0, len(item.get("splits") or [])))
    candidates = []
    for activity in activities or []:
        split_info = _polar_exercise_splits(activity.get("raw") or {})
        splits = split_info.get("splits") or []
        # AccessLink distance/speed samples are converted to automatic kilometre
        # splits. Those are useful for analysis, but do not describe workout
        # blocks and must not be presented as a reconstructed plan.
        source = split_info.get("source") or ""
        reliable_splits = splits if source not in {"distance samples", "speed samples", "route"} else []
        candidates.append((len(reliable_splits), float(activity.get("distance_m") or 0), activity, reliable_splits, source))
    if not candidates:
        return None
    _count, _distance, activity, splits, source = max(candidates, key=lambda item: (item[0], item[1]))
    if not splits:
        distance_m = float(activity.get("distance_m") or 0)
        duration_s = float(activity.get("duration_seconds") or 0)
        if distance_m <= 0 or duration_s <= 0:
            return None
        splits = [{"label": "Continuous block", "distance_m": round(distance_m),
                   "duration": _format_seconds_hms(round(duration_s)), "duration_s": duration_s,
                   "pace": _format_pace(duration_s, distance_m)}]
        source, confidence = "activity total (no reliable lap structure found)", 0.35
    else:
        confidence = 0.75 if len(splits) >= 3 else 0.6
    total_m = sum(float(split.get("distance_m") or 0) for split in splits)
    total_s = sum(float(split.get("duration_s") or 0) for split in splits)
    summary = f"Reconstructed {len(splits)} block{'s' if len(splits) != 1 else ''} from {source or 'watch data'}"
    if total_m > 0 and total_s > 0:
        summary += f" | {total_m / 1000.0:.2f} km in {_format_seconds_hms(round(total_s))}"
    summary += ". Review the blocks before using this suggestion."
    return {"mode": "alternative_reconstruction", "activity_id": activity.get("id") or "alternative-watch-reconstruction",
            "title": "Alternative plan from watch data", "summary": summary, "splits": splits,
            "zone_totals": _watch_zone_totals_summary(athlete, splits) if athlete else "",
            "confidence": confidence, "alternative": True, "ai": False}


@login_required
@require_GET
def polar_activity_suggestions_view(request):
    athlete_id = (request.GET.get("athlete") or "").strip()
    day = (request.GET.get("date") or "").strip()
    planned_text = (request.GET.get("planned") or "").strip()
    alternative_requested = request.GET.get("alternative") == "1"
    try:
        target_date = date.fromisoformat(day)
    except Exception:
        return JsonResponse({"ok": False, "message": "Invalid date.", "activities": []}, status=400)

    athlete, connection = _polar_connection_for_athlete_request(request, athlete_id)
    if not athlete:
        return JsonResponse({"ok": False, "message": "Athlete not found.", "activities": []}, status=404)
    if not connection or not connection.access_token:
        return JsonResponse({"ok": False, "message": "No watch is connected for this athlete.", "activities": []})

    url = _polar_exercises_url(include_detail=True)
    headers = {
        "Accept": "application/json",
        "Authorization": f"Bearer {connection.access_token}",
    }
    try:
        status, payload = _polar_json_request(url, method="GET", headers=headers)
    except RuntimeError as exc:
        return JsonResponse({"ok": False, "message": f"Watch sync failed: {exc}", "activities": []})

    if status >= 400:
        polar_message = ""
        if isinstance(payload, dict):
            polar_message = payload.get("error_description") or payload.get("error") or ""
        message = f"Watch sync failed with status {status}."
        if polar_message:
            message = f"{message} {polar_message}"
        return JsonResponse({"ok": False, "message": message, "activities": []})

    activities = []
    if isinstance(payload, list):
        for item in payload:
            if not isinstance(item, dict):
                continue
            start_time = str(item.get("start_time") or "")
            if start_time[:10] != target_date.isoformat():
                continue
            duration_s = _polar_duration_seconds(item.get("duration") or "")
            distance_m = item.get("distance")
            try:
                distance_m = float(distance_m) if distance_m is not None else None
            except (TypeError, ValueError):
                distance_m = None
            heart_rate = item.get("heart_rate") if isinstance(item.get("heart_rate"), dict) else {}
            activities.append({
                "id": item.get("id") or "",
                "start_time": start_time,
                "sport": item.get("sport") or item.get("detailed_sport_info") or "",
                "duration": item.get("duration") or "",
                "duration_seconds": duration_s,
                "duration_label": _format_seconds_hms(duration_s),
                "distance_m": distance_m,
                "distance_km": round(distance_m / 1000.0, 2) if distance_m is not None else None,
                "avg_hr": heart_rate.get("average"),
                "max_hr": heart_rate.get("maximum"),
                "calories": item.get("calories"),
                "running_index": item.get("running_index"),
                "raw": item,
            })

    activities.sort(key=lambda item: item.get("start_time") or "")
    analysis_activities = _watch_activities_for_plan(planned_text, activities)
    v4_sessions, v4_status = _polar_v4_sessions_for_day(connection, target_date)
    analysis_v4_sessions = _watch_v4_sessions_for_plan(planned_text, v4_sessions)
    v4_plan_suggestion = _build_polar_v4_lap_suggestion(planned_text, analysis_v4_sessions, athlete=athlete)
    if alternative_requested:
        alternative_suggestion = _build_alternative_watch_suggestion(
            analysis_activities, v4_sessions=analysis_v4_sessions, athlete=athlete
        )
        return JsonResponse({
            "ok": bool(alternative_suggestion),
            "message": "" if alternative_suggestion else "The watch data was not detailed enough to reconstruct an alternative plan.",
            "alternative_suggestion": alternative_suggestion,
            "activities": [],
        })
    if not activities and not v4_plan_suggestion:
        return JsonResponse({
            "ok": True,
            "message": v4_status or "No watch activities found for this day.",
            "activities": [],
        })
    plan_suggestion = None
    ai_status = ""
    if planned_text:
        if _should_use_direct_distance_splits(planned_text, analysis_activities):
            plan_suggestion = _build_plan_watch_suggestion(planned_text, analysis_activities, athlete=athlete)
            ai_status = "Mila direct distance split analysis created."
        if not plan_suggestion:
            plan_suggestion, ai_status = _build_ai_watch_suggestion(planned_text, analysis_activities, athlete=athlete)
        if not plan_suggestion:
            plan_suggestion = _build_plan_watch_suggestion(planned_text, analysis_activities, athlete=athlete)
    plan_mismatch = _watch_plan_is_clear_mismatch(planned_text, analysis_activities, plan_suggestion)
    if plan_mismatch and plan_suggestion:
        plan_suggestion["plan_mismatch"] = True
        plan_suggestion["title"] = "❌ " + str(plan_suggestion.get("title") or "Plan mismatch")
    response_activities = []
    for activity in activities:
        cleaned = dict(activity)
        cleaned.pop("raw", None)
        response_activities.append(cleaned)
    watch_debug = [_polar_activity_debug_summary(activity.get("raw") or {}) for activity in activities[:3]]
    if v4_status and activities:
        watch_debug.append(f"Polar v4: {v4_status}")
    return JsonResponse({
        "ok": True,
        "message": "",
        "activities": response_activities,
        "v4_plan_suggestion": v4_plan_suggestion,
        "plan_suggestion": plan_suggestion,
        "ai_status": ai_status,
        "plan_mismatch": plan_mismatch,
        "mismatch_message": "❌ Watch data does not match the planned training closely enough.",
        "watch_debug": watch_debug,
    })


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
        TrainingPlan.objects.filter(
            plan_kind=TrainingPlan.PLAN_KIND_TRAINER
        ).select_related("owner"),
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
        "CORE": "Main",
        "CORE2": "Main 2",
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


def _base_planning_athlete_qs_for_user(user):
    if user.is_staff or user.is_superuser:
        return _filter_owned(Athlete.objects.order_by("name"), user)

    athlete = _athlete_for_user(user)
    if not athlete:
        return Athlete.objects.none()
    return Athlete.objects.filter(id=athlete.id)


@login_required
@require_http_methods(["GET", "POST"])
@xframe_options_sameorigin
def athlete_base_planning_view(request):
    embedded = (request.GET.get("embedded") == "1") or (request.POST.get("embedded") == "1")
    read_only = (request.GET.get("readonly") == "1") or (request.POST.get("readonly") == "1")
    redirect_suffix = "&embedded=1" if embedded else ""
    planning_kind = (request.POST.get("kind") or request.GET.get("kind") or AthleteBasePlanningBlock.KIND_BASE).strip()
    if planning_kind not in {AthleteBasePlanningBlock.KIND_BASE, AthleteBasePlanningBlock.KIND_IDEAL}:
        planning_kind = AthleteBasePlanningBlock.KIND_BASE
    redirect_suffix += f"&kind={planning_kind}"
    is_ideal_week = planning_kind == AthleteBasePlanningBlock.KIND_IDEAL
    read_only = bool(
        read_only
        or (
            not (request.user.is_staff or request.user.is_superuser)
            and planning_kind == AthleteBasePlanningBlock.KIND_BASE
        )
    )
    athletes = list(_base_planning_athlete_qs_for_user(request.user))
    selected_athlete = None
    selected_id = (request.POST.get("athlete_id") or request.GET.get("athlete") or "").strip()
    if selected_id.isdigit():
        selected_athlete = _base_planning_athlete_qs_for_user(request.user).filter(id=int(selected_id)).first()
    if not selected_athlete and athletes:
        selected_athlete = athletes[0]

    errors = []
    saved = False

    if request.method == "POST" and read_only:
        return HttpResponse("Forbidden", status=403)

    if request.method == "POST" and selected_athlete:
        action = (request.POST.get("action") or "").strip()

        if action == "add_block":
            sort_order = selected_athlete.base_planning_blocks.filter(planning_kind=planning_kind).count() + 1
            block = AthleteBasePlanningBlock.objects.create(
                athlete=selected_athlete,
                planning_kind=planning_kind,
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
                source_athlete = _base_planning_athlete_qs_for_user(request.user).filter(id=int(source_id)).first()

            if not source_athlete:
                errors.append("Choose a valid athlete to copy from.")
            elif source_athlete.id == selected_athlete.id:
                errors.append("Choose a different athlete to copy from.")
            else:
                source_blocks = (
                    AthleteBasePlanningBlock.objects
                    .filter(athlete=source_athlete, planning_kind=planning_kind)
                    .prefetch_related("slots")
                    .order_by("sort_order", "start_month", "start_day", "id")
                )
                with transaction.atomic():
                    AthleteBasePlanningBlock.objects.filter(athlete=selected_athlete, planning_kind=planning_kind).delete()
                    for source_block in source_blocks:
                        target_block = AthleteBasePlanningBlock.objects.create(
                            athlete=selected_athlete,
                            planning_kind=planning_kind,
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

        if action == "autosave_slot":
            slot_id = (request.POST.get("slot_id") or "").strip()
            if not slot_id.isdigit():
                return JsonResponse({"ok": False, "errors": ["Invalid slot."]}, status=400)

            slot = (
                AthleteBasePlanningSlot.objects
                .select_related("block")
                .filter(id=int(slot_id), block__athlete=selected_athlete, block__planning_kind=planning_kind)
                .first()
            )
            if not slot:
                return JsonResponse({"ok": False, "errors": ["Slot not found."]}, status=404)

            mode = (request.POST.get("mode") or AthleteBasePlanningSlot.MODE_REST).strip()
            if mode not in {
                AthleteBasePlanningSlot.MODE_REST,
                AthleteBasePlanningSlot.MODE_TRAINING,
                AthleteBasePlanningSlot.MODE_TRAINER,
            }:
                mode = AthleteBasePlanningSlot.MODE_REST

            trainer_plan = None
            trainer_plan_id = (request.POST.get("trainer_plan") or "").strip()
            if mode == AthleteBasePlanningSlot.MODE_TRAINER and trainer_plan_id.isdigit():
                trainer_plan = _trainer_planning_qs(request.user).filter(id=int(trainer_plan_id)).first()

            slot.mode = mode
            slot.training_text = (request.POST.get("training_text") or "").strip() if mode == AthleteBasePlanningSlot.MODE_TRAINING else ""
            slot.trainer_plan = trainer_plan
            slot.save(update_fields=["mode", "training_text", "trainer_plan"])
            if request.headers.get("X-Requested-With") != "XMLHttpRequest":
                return redirect(f"{reverse('athlete_base_planning')}?athlete={selected_athlete.id}{redirect_suffix}")
            return JsonResponse({"ok": True})

        if action == "save":
            block_ids = [
                int(value)
                for value in request.POST.getlist("block_id")
                if str(value).isdigit()
            ]
            blocks = {
                block.id: block
                for block in AthleteBasePlanningBlock.objects.filter(athlete=selected_athlete, planning_kind=planning_kind, id__in=block_ids)
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
                    AthleteBasePlanningBlock.objects.filter(athlete=selected_athlete, planning_kind=planning_kind, id__in=delete_ids).delete()
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
                if request.POST.get("autosave") == "1":
                    return JsonResponse({"ok": True})
            elif request.POST.get("autosave") == "1":
                return JsonResponse({"ok": False, "errors": errors}, status=400)

    blocks = []
    if selected_athlete:
        block_qs = (
            AthleteBasePlanningBlock.objects
            .filter(athlete=selected_athlete, planning_kind=planning_kind)
            .prefetch_related("slots", "slots__trainer_plan")
            .order_by("sort_order", "start_month", "start_day", "id")
        )
        for block in block_qs:
            _ensure_base_block_slots(block)
        block_qs = (
            AthleteBasePlanningBlock.objects
            .filter(athlete=selected_athlete, planning_kind=planning_kind)
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
            "planning_kind": planning_kind,
            "is_ideal_week": is_ideal_week,
            "read_only": read_only,
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
    return redirect("race_calendar")


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


def _standard_strength_visible_via_base_planning(program, athlete):
    blocks = list(
        AthleteBasePlanningBlock.objects
        .filter(athlete=athlete, planning_kind=AthleteBasePlanningBlock.KIND_BASE)
        .prefetch_related("slots")
        .order_by("sort_order", "start_month", "start_day", "id")
    )
    if not blocks:
        return False

    def block_covers_day(block, day):
        marker_year = 2024
        start_index = date(marker_year, block.start_month, block.start_day).timetuple().tm_yday
        end_index = date(marker_year, block.end_month, block.end_day).timetuple().tm_yday
        day_index = date(marker_year, day.month, day.day).timetuple().tm_yday
        if start_index <= end_index:
            return start_index <= day_index <= end_index
        return day_index >= start_index or day_index <= end_index

    trainer_segments = (
        program.segments
        .filter(slot__athlete__isnull=True, slot__plan__plan_kind=TrainingPlan.PLAN_KIND_TRAINER)
        .select_related("slot")
    )
    for segment in trainer_segments:
        trainer_slot = segment.slot
        selected_base_slot = None
        for block in blocks:
            if not block_covers_day(block, trainer_slot.date):
                continue
            selected_base_slot = next((
                base_slot
                for base_slot in block.slots.all()
                if base_slot.weekday == trainer_slot.date.weekday()
                and base_slot.slot_index == trainer_slot.slot_index
            ), None)
            if selected_base_slot:
                break
        if (
            selected_base_slot
            and selected_base_slot.mode == AthleteBasePlanningSlot.MODE_TRAINER
            and selected_base_slot.trainer_plan_id == trainer_slot.plan_id
        ):
            return True
    return False


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
        allowed = bool(
            athlete
            and (
                program.segments.filter(
                    Q(slot__athlete=athlete)
                    | Q(slot__athletes=athlete)
                    | Q(slot__groups__athletes=athlete)
                    | Q(slot__plan__athletes=athlete)
                    | Q(slot__plan__groups__athletes=athlete)
                ).exists()
                or _standard_strength_visible_via_base_planning(program, athlete)
            )
        )
        if not allowed:
            return HttpResponse("Not allowed", status=403)
    next_url = (request.GET.get("next") or "").strip()
    if not next_url.startswith("/"):
        next_url = reverse("planning_overview")
    return render(request, "core/standard_strength_detail.html", {
        "program": program,
        "next_url": next_url,
    })


def _race_calendar_redirect_for_year(year, view_mode="calendar", period_mode="full", race_scope="all", show_all_races=True, race_group=None, race_athlete=None):
    view_mode = "calendar" if view_mode == "calendar" else "list"
    allowed_periods = {"full", "outdoor", "indoor", "current_next"}
    period_mode = period_mode if period_mode in allowed_periods else "full"
    if race_group is None or race_athlete is None:
        race_group = race_scope if str(race_scope).startswith("plan:") else "all"
        race_athlete = race_scope if str(race_scope).startswith("athlete:") else "all"
    query = urlencode({
        "year": year,
        "view": view_mode,
        "period": period_mode,
        "race_group": race_group or "all",
        "race_athlete": race_athlete or "all",
        "show_all": "1" if show_all_races else "0",
    })
    return redirect(f"/race-calendar/?{query}")


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


def _race_segment_special(entry):
    if not entry:
        return ""
    confirmed = bool(entry.coach_selected and entry.athlete_selected)
    if entry.target_selected:
        return "IMPORTANT_RACE" if confirmed else "RACE_TARGET_PENDING"
    if entry.coach_selected or entry.athlete_selected:
        return "RACE" if confirmed else "RACE_PENDING"
    return ""


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
    return (seg.special or "") in ("RACE", "IMPORTANT_RACE", "RACE_PENDING", "RACE_TARGET_PENDING")


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
                special=_race_segment_special(entry),
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
    current_athlete = _athlete_for_user(request.user)
    is_athlete_user = bool(current_athlete and not request.user.is_staff and not request.user.is_superuser)

    try:
        year = int(request.GET.get("year") or request.POST.get("year") or today.year)
    except ValueError:
        year = today.year

    if year < 2000 or year > 2100:
        year = today.year

    default_view_mode = "list" if is_athlete_user else "calendar"
    view_mode = (request.GET.get("view") or request.POST.get("view") or default_view_mode).strip().lower()
    if view_mode not in ("list", "calendar"):
        view_mode = "list"

    period_mode = (request.GET.get("period") or request.POST.get("period") or "full").strip().lower()
    allowed_periods = {"full", "outdoor", "indoor", "current_next"}
    if period_mode not in allowed_periods:
        period_mode = "full"

    legacy_scope = (request.GET.get("race_scope") or request.POST.get("race_scope") or "all").strip().lower()
    race_group = (request.GET.get("race_group") or request.POST.get("race_group") or (legacy_scope if legacy_scope.startswith("plan:") else "all")).strip().lower()
    race_athlete = (request.GET.get("race_athlete") or request.POST.get("race_athlete") or (legacy_scope if legacy_scope.startswith("athlete:") else "all")).strip().lower()
    show_all_raw = request.GET.get("show_all") if request.method == "GET" else request.POST.get("show_all")
    filter_was_supplied = any(key in request.GET or key in request.POST for key in ("race_scope", "race_group", "race_athlete"))
    show_all_races = True if not filter_was_supplied else show_all_raw == "1"

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
            race_owner = current_athlete.owner if is_athlete_user else request.user
            if race_owner is None:
                return HttpResponse("Not allowed", status=403)
            RaceEvent.objects.create(
                owner=race_owner,
                name=name,
                date=race_date,
            )
            return _race_calendar_redirect_for_year(year, view_mode, period_mode, show_all_races=show_all_races, race_group=race_group, race_athlete=race_athlete)

    if is_athlete_user:
        race_owner_ids = {current_athlete.owner_id} if current_athlete.owner_id else set()
        race_owner_ids.update(
            Group.objects.filter(athletes=current_athlete).values_list("owner_id", flat=True)
        )
        race_owner_ids.update(
            TrainingPlan.objects.filter(
                Q(athletes=current_athlete) | Q(groups__athletes=current_athlete)
            ).values_list("owner_id", flat=True)
        )
        race_owner_ids.discard(None)
    else:
        race_owner_ids = {request.user.id}

    races = list(
        RaceEvent.objects
        .filter(owner_id__in=race_owner_ids, date__gte=start_date, date__lte=end_date)
        .prefetch_related("distances")
        .order_by("date", "name", "id")
    )

    if is_athlete_user:
        race_athletes = [current_athlete]
        trainer_plans = []
    else:
        race_athletes = list(_filter_owned(Athlete.objects.order_by("name"), request.user))
        trainer_plans = list(
            _filter_owned(
                TrainingPlan.objects.filter(plan_kind=TrainingPlan.PLAN_KIND_TRAINER).prefetch_related("athletes", "groups__athletes"),
                request.user,
            ).order_by("name")
        )

    all_distances = [distance for race in races for distance in _sorted_race_distances(race)]
    entry_map = {
        (entry.race_distance_id, entry.athlete_id): entry
        for entry in RaceEntry.objects.filter(
            race_distance__in=all_distances,
            athlete__in=race_athletes,
        )
    }
    plan_ids_by_athlete = {athlete.id: [] for athlete in race_athletes}
    for plan in trainer_plans:
        plan_athlete_ids = set(plan.targeted_athlete_ids())
        plan_athlete_ids.update(
            Athlete.objects.filter(
                base_planning_blocks__slots__trainer_plan=plan
            ).values_list("id", flat=True)
        )
        for athlete_id in plan_athlete_ids:
            if athlete_id in plan_ids_by_athlete:
                plan_ids_by_athlete[athlete_id].append(str(plan.id))

    all_race_athlete_ids = {athlete.id for athlete in race_athletes}
    group_athlete_ids = set(all_race_athlete_ids)
    if not is_athlete_user and race_group.startswith("plan:"):
        plan_id_raw = race_group.split(":", 1)[1]
        selected_plan = next((plan for plan in trainer_plans if str(plan.id) == plan_id_raw), None)
        if selected_plan:
            group_athlete_ids = {
                athlete_id for athlete_id, plan_ids in plan_ids_by_athlete.items()
                if str(selected_plan.id) in plan_ids
            }
        else:
            race_group = "all"
    elif race_group != "all":
        race_group = "all"

    scoped_athlete_ids = set(group_athlete_ids)
    if not is_athlete_user and race_athlete.startswith("athlete:"):
        athlete_id_raw = race_athlete.split(":", 1)[1]
        selected_athlete_id = int(athlete_id_raw) if athlete_id_raw.isdigit() else None
        if selected_athlete_id in group_athlete_ids:
            scoped_athlete_ids = {selected_athlete_id}
        else:
            race_athlete = "all"
    elif race_athlete != "all":
        race_athlete = "all"

    race_rows = []
    for race in races:
        distances = _sorted_race_distances(race)
        distance_participant_counts = {distance.id: 0 for distance in distances}
        calendar_status_rank = 0
        athlete_rows = []
        for athlete in race_athletes:
            distance_entries = []
            participating = False
            for distance in distances:
                entry = entry_map.get((distance.id, athlete.id))
                participating = participating or bool(
                    entry and (entry.coach_selected or entry.athlete_selected or entry.target_selected)
                )
                if athlete.id in scoped_athlete_ids and entry and (entry.coach_selected or entry.athlete_selected or entry.target_selected):
                    distance_participant_counts[distance.id] += 1
                    if entry.target_selected:
                        entry_rank = 4 if entry.coach_selected and entry.athlete_selected else 2
                    else:
                        entry_rank = 3 if entry.coach_selected and entry.athlete_selected else 1
                    calendar_status_rank = max(calendar_status_rank, entry_rank)
                distance_entries.append({"distance": distance, "entry": entry})
            athlete_rows.append({
                "athlete": athlete,
                "distance_entries": distance_entries,
                "participating": participating,
                "plan_ids": ",".join(plan_ids_by_athlete.get(athlete.id, [])),
            })
        scoped_participant_count = sum(
            1 for athlete_row in athlete_rows
            if athlete_row["athlete"].id in scoped_athlete_ids and athlete_row["participating"]
        )
        distance_rows = []
        for distance in distances:
            scoped_entry = None
            if is_athlete_user:
                scoped_entry = entry_map.get((distance.id, current_athlete.id))
            selection_class = ""
            if scoped_entry and (scoped_entry.coach_selected or scoped_entry.athlete_selected or scoped_entry.target_selected):
                if scoped_entry.target_selected:
                    selection_class = "race-choice-target-confirmed" if scoped_entry.coach_selected and scoped_entry.athlete_selected else "race-choice-target-pending"
                else:
                    selection_class = "race-choice-confirmed" if scoped_entry.coach_selected and scoped_entry.athlete_selected else "race-choice-pending"
            distance_rows.append({
                "distance": distance,
                "participant_count": distance_participant_counts[distance.id],
                "selection_class": selection_class,
            })
        race_rows.append({
            "race": race,
            "distances": distances,
            "distance_rows": distance_rows,
            "participant_count": scoped_participant_count,
            "calendar_status_class": {
                0: "race-calendar-none",
                1: "race-calendar-pending",
                2: "race-calendar-target-pending",
                3: "race-calendar-confirmed",
                4: "race-calendar-target-confirmed",
            }[calendar_status_rank],
            "athlete_rows": athlete_rows,
        })

    if not show_all_races:
        race_rows = [row for row in race_rows if row["participant_count"] > 0]

    race_group_options = [
        {"value": f"plan:{plan.id}", "label": plan.name}
        for plan in trainer_plans
    ]
    race_athlete_options = [
        {"value": f"athlete:{athlete.id}", "label": athlete.name}
        for athlete in race_athletes if athlete.id in group_athlete_ids
    ]
    popup_athlete_options = [
        {"value": f"athlete:{athlete.id}", "label": athlete.name}
        for athlete in race_athletes
    ]
    if race_athlete != "all":
        popup_initial_filter = race_athlete
    elif race_group != "all":
        popup_initial_filter = race_group
    else:
        popup_initial_filter = "all"

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
        "trainer_plans": trainer_plans,
        "race_athletes": race_athletes,
        "race_group_options": race_group_options,
        "race_athlete_options": race_athlete_options,
        "popup_athlete_options": popup_athlete_options,
        "race_group": race_group,
        "race_athlete": race_athlete,
        "popup_initial_filter": popup_initial_filter,
        "show_all_races": show_all_races,
        "is_athlete_user": is_athlete_user,
        "current_athlete": current_athlete,
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
    race_group = (request.POST.get("race_group") or "all").strip().lower()
    race_athlete = (request.POST.get("race_athlete") or "all").strip().lower()
    show_all_races = request.POST.get("show_all") == "1"
    race.delete()
    return _race_calendar_redirect_for_year(year, view_mode, period_mode, show_all_races=show_all_races, race_group=race_group, race_athlete=race_athlete)


@login_required
@require_http_methods(["POST"])
def race_calendar_distance_add_view(request, race_id: int):
    current_athlete = _athlete_for_user(request.user)
    is_athlete_user = bool(current_athlete and not request.user.is_staff and not request.user.is_superuser)
    if is_athlete_user:
        race = get_object_or_404(
            RaceEvent.objects.filter(owner_id=current_athlete.owner_id), id=race_id
        )
    else:
        race = get_object_or_404(RaceEvent.objects.filter(owner=request.user), id=race_id)
    selected_distances = request.POST.getlist("distances")
    remove_distance_ids = request.POST.getlist("remove_distances")
    custom_raw = (request.POST.get("custom_distance_m") or "").strip()
    allowed = {value for value, _ in RaceEventDistance.DISTANCE_CHOICES}

    if remove_distance_ids and not is_athlete_user:
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
    race_group = (request.POST.get("race_group") or "all").strip().lower()
    race_athlete = (request.POST.get("race_athlete") or "all").strip().lower()
    show_all_races = request.POST.get("show_all") == "1"
    return _race_calendar_redirect_for_year(race.date.year, view_mode, period_mode, show_all_races=show_all_races, race_group=race_group, race_athlete=race_athlete)


@login_required
@require_http_methods(["POST"])
def race_calendar_distance_delete_view(request, race_id: int, distance_id: int):
    race = get_object_or_404(RaceEvent.objects.filter(owner=request.user), id=race_id)
    distance = get_object_or_404(RaceEventDistance.objects.filter(race=race), id=distance_id)
    view_mode = (request.POST.get("view") or request.GET.get("view") or "list").strip().lower()
    period_mode = (request.POST.get("period") or request.GET.get("period") or "full").strip().lower()
    race_group = (request.POST.get("race_group") or "all").strip().lower()
    race_athlete = (request.POST.get("race_athlete") or "all").strip().lower()
    show_all_races = request.POST.get("show_all") == "1"
    distance.delete()
    return _race_calendar_redirect_for_year(race.date.year, view_mode, period_mode, show_all_races=show_all_races, race_group=race_group, race_athlete=race_athlete)


@login_required
@require_http_methods(["POST"])
def race_calendar_entries_save_view(request, race_id: int):
    current_athlete = _athlete_for_user(request.user)
    is_athlete_user = bool(current_athlete and not request.user.is_staff and not request.user.is_superuser)
    if is_athlete_user:
        allowed_owner_ids = {current_athlete.owner_id} if current_athlete.owner_id else set()
        allowed_owner_ids.update(
            Group.objects.filter(athletes=current_athlete).values_list("owner_id", flat=True)
        )
        allowed_owner_ids.update(
            TrainingPlan.objects.filter(
                Q(athletes=current_athlete) | Q(groups__athletes=current_athlete)
            ).values_list("owner_id", flat=True)
        )
        allowed_owner_ids.discard(None)
        race = get_object_or_404(RaceEvent.objects.filter(owner_id__in=allowed_owner_ids), id=race_id)
        athletes = [current_athlete]
    else:
        race = get_object_or_404(RaceEvent.objects.filter(owner=request.user), id=race_id)
        posted_athlete_ids = {
            int(value) for value in request.POST.getlist("athletes") if value.isdigit()
        }
        athletes = list(
            _filter_owned(Athlete.objects.filter(id__in=posted_athlete_ids), request.user)
        )

    distances = _sorted_race_distances(race)
    changed_athletes = []
    with transaction.atomic():
        for athlete in athletes:
            states = []
            for distance in distances:
                entry = RaceEntry.objects.filter(race_distance=distance, athlete=athlete).first()
                coach_selected = bool(entry and entry.coach_selected)
                athlete_selected = bool(entry and entry.athlete_selected)
                target_selected = bool(entry and entry.target_selected)
                if is_athlete_user:
                    athlete_selected = request.POST.get(f"athlete_{athlete.id}_{distance.id}") == "1"
                else:
                    coach_selected = request.POST.get(f"coach_{athlete.id}_{distance.id}") == "1"
                target_selected = request.POST.get(f"target_{athlete.id}_{distance.id}") == "1"
                states.append((distance, entry, coach_selected, athlete_selected, target_selected))

            selected_states = [state for state in states if any(state[2:])]
            if len(selected_states) > 3:
                return HttpResponse("Select at most three distances per athlete.", status=400)

            athlete_changed = False
            for distance, entry, coach_selected, athlete_selected, target_selected in states:
                old_state = (
                    bool(entry and entry.coach_selected),
                    bool(entry and entry.athlete_selected),
                    bool(entry and entry.target_selected),
                )
                new_state = (coach_selected, athlete_selected, target_selected)
                if old_state == new_state:
                    continue
                athlete_changed = True
                if not any(new_state):
                    if entry:
                        entry.delete()
                else:
                    RaceEntry.objects.update_or_create(
                        race_distance=distance,
                        athlete=athlete,
                        defaults={
                            "coach_selected": coach_selected,
                            "athlete_selected": athlete_selected,
                            "target_selected": target_selected,
                        },
                    )
            if athlete_changed:
                changed_athletes.append(athlete)

    for athlete in changed_athletes:
        _sync_race_training_override(athlete, race)

    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return JsonResponse({"ok": True})

    view_mode = (request.POST.get("view") or "list").strip()
    period_mode = (request.POST.get("period") or "full").strip()
    race_group = (request.POST.get("race_group") or "all").strip().lower()
    race_athlete = (request.POST.get("race_athlete") or "all").strip().lower()
    show_all_races = request.POST.get("show_all") == "1"
    return _race_calendar_redirect_for_year(race.date.year, view_mode, period_mode, show_all_races=show_all_races, race_group=race_group, race_athlete=race_athlete)


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
    unit = "pace"
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
def coach_athlete_edit_view(request, athlete_id: int, self_view: bool = False):
    if self_view:
        athlete = _athlete_for_user(request.user)
        if not athlete:
            return HttpResponse("No athlete profile is linked to this account.", status=404)
        if athlete.id != athlete_id:
            return HttpResponse("Forbidden", status=403)
    else:
        athlete = get_object_or_404(_filter_owned(Athlete.objects.all(), request.user), id=athlete_id)
    unit = "pace"
    unit_label = zone_unit_label(unit)

    speeds = athlete.get_zone_speed_mps()
    zones_form = zones_form_from_speeds(unit, speeds)

    errors = []
    saved_notice = "Opgeslagen." if request.GET.get("saved") == "1" else None
    active_tab = (request.GET.get("tab") or "general").strip()
    allowed_tabs = {"general", "zones", "base-planning", "ideal-week", "wu-settings"}
    if active_tab not in allowed_tabs:
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
        if self_view:
            form["view_weeks_ahead"] = str(getattr(athlete, "view_weeks_ahead", 2))
            form["training_reports_enabled"] = getattr(athlete, "training_reports_enabled", True)
            form["week_report_enabled"] = getattr(athlete, "week_report_enabled", False)
            form["daily_vitals_enabled"] = getattr(athlete, "daily_vitals_enabled", False)
        else:
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

            target_url = reverse("athlete_settings") if self_view else reverse("coach_athlete_edit", args=[athlete.id])
            return redirect(f"{target_url}?tab=zones&saved=1")

    return render(
        request,
        "core/coach_athlete_form.html",
        {
            "mode": "edit",
            "athlete": athlete,
            "form": form,
            "errors": errors,
            "saved_notice": saved_notice,
            "active_tab": active_tab,
            "self_view": self_view,
        },
    )


@login_required
@require_http_methods(["GET", "POST"])
def athlete_settings_view(request):
    athlete = _athlete_for_user(request.user)
    if not athlete:
        return HttpResponse("No athlete profile is linked to this account.", status=404)
    return coach_athlete_edit_view(request, athlete.id, self_view=True)


@login_required
@require_http_methods(["POST"])
def coach_athlete_target_prs_view(request, athlete_id: int):
    if request.user.is_staff or request.user.is_superuser:
        athlete = get_object_or_404(_filter_owned(Athlete.objects.all(), request.user), id=athlete_id)
    else:
        athlete = _athlete_for_user(request.user)
        if not athlete or athlete.id != athlete_id:
            return HttpResponse("Forbidden", status=403)
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
    _athlete_plan_for_day,
    _ayc_slot_loads_for_totals,
    _annotate_slot_segment_display_times,
    _base_planning_slot_for_day,
    _clone_slot_for_display,
    _get_athlete_year_flex_plan,
    _is_flex_planner_plan,
    _slot_has_race,
    _slot_is_visually_empty,
    _virtual_race_slot_from_entries,
    _virtual_slot_from_base_training,
)


def _effective_week_distance_m(athlete, plans, week_start):
    end = week_start + timedelta(days=14)
    days = [week_start + timedelta(days=offset) for offset in range(14)]
    non_trainer_plans = [
        plan for plan in plans
        if plan.plan_kind != TrainingPlan.PLAN_KIND_TRAINER and not _is_flex_planner_plan(plan)
    ]
    flex_plan = next((
        plan for plan in plans
        if _is_flex_planner_plan(plan) and plan.owner_id == athlete.owner_id
    ), None)

    athlete_plans = []
    for plan in non_trainer_plans:
        try:
            targeted = athlete.id in plan.targeted_athlete_ids()
        except Exception:
            targeted = False
        has_override = TrainingSlot.objects.filter(
            plan=plan,
            athlete=athlete,
            date__gte=week_start,
            date__lt=end,
        ).exists()
        if targeted or has_override:
            athlete_plans.append(plan)

    direct_plan_ids = [plan.id for plan in athlete_plans]
    if flex_plan:
        direct_plan_ids.append(flex_plan.id)
    direct_slots = (
        TrainingSlot.objects
        .filter(plan_id__in=direct_plan_ids, date__gte=week_start, date__lt=end)
        .filter(Q(athlete__isnull=True) | Q(athlete=athlete))
        .prefetch_related("segments")
    )
    slot_lookup = {
        (slot.plan_id, slot.athlete_id, slot.date, slot.slot_index): slot
        for slot in direct_slots
    }

    base_slot_qs = AthleteBasePlanningSlot.objects.select_related("trainer_plan").order_by("weekday", "slot_index")
    blocks = list(
        AthleteBasePlanningBlock.objects
        .filter(athlete=athlete, planning_kind=AthleteBasePlanningBlock.KIND_BASE)
        .prefetch_related(Prefetch("slots", queryset=base_slot_qs, to_attr="_prefetched_base_slots"))
        .order_by("sort_order", "start_month", "start_day", "id")
    )
    base_blocks_by_athlete = {athlete.id: blocks}
    trainer_plan_ids = {
        base_slot.trainer_plan_id
        for block in blocks
        for base_slot in getattr(block, "_prefetched_base_slots", [])
        if base_slot.mode == AthleteBasePlanningSlot.MODE_TRAINER and base_slot.trainer_plan_id
    }
    trainer_slot_lookup = {
        (slot.plan_id, slot.date, slot.slot_index): slot
        for slot in TrainingSlot.objects.filter(
            plan_id__in=trainer_plan_ids,
            athlete__isnull=True,
            date__gte=week_start,
            date__lt=end,
        ).prefetch_related("segments")
    }

    totals = {week_start: 0.0, week_start + timedelta(days=7): 0.0}
    for day in days:
        matching_plan = _athlete_plan_for_day(athlete_plans, day)
        for slot_index in (1, 2):
            slot = None
            if matching_plan:
                slot = (
                    slot_lookup.get((matching_plan.id, athlete.id, day, slot_index))
                    or slot_lookup.get((matching_plan.id, None, day, slot_index))
                )

            if flex_plan:
                flex_override = slot_lookup.get((flex_plan.id, athlete.id, day, slot_index))
                flex_blocks_fallback = False
                if flex_override is not None:
                    flex_blocks_fallback = _slot_is_visually_empty(flex_override)
                    slot = None if flex_blocks_fallback else flex_override
            else:
                flex_blocks_fallback = False

            if not slot and not flex_blocks_fallback:
                base_planning_slot = _base_planning_slot_for_day(
                    base_blocks_by_athlete, athlete.id, day, slot_index
                )
                if base_planning_slot:
                    if base_planning_slot.mode == AthleteBasePlanningSlot.MODE_TRAINING:
                        slot = _virtual_slot_from_base_training(base_planning_slot.training_text)
                    elif base_planning_slot.mode == AthleteBasePlanningSlot.MODE_TRAINER and base_planning_slot.trainer_plan_id:
                        slot = trainer_slot_lookup.get((base_planning_slot.trainer_plan_id, day, slot_index))

            target_week = week_start if day < week_start + timedelta(days=7) else week_start + timedelta(days=7)
            for load in _ayc_slot_loads_for_totals(slot, athlete):
                if load.get("kind") != "alt":
                    totals[target_week] += float(load.get("meters") or 0)
    return totals


@login_required
@require_http_methods(["GET", "POST"])
def trainer_stats_view(request):
    if not (request.user.is_staff or request.user.is_superuser):
        return HttpResponse("Not allowed", status=403)

    all_athletes = list(_filter_owned(Athlete.objects.order_by("name"), request.user))
    all_athlete_ids = {athlete.id for athlete in all_athletes}
    coach_settings, _ = CoachSettings.objects.get_or_create(user=request.user)
    dco_saved_selections = []
    for item in coach_settings.dco_saved_selections or []:
        if not isinstance(item, dict):
            continue
        selection_id = str(item.get("id") or "").strip()
        name = str(item.get("name") or "").strip()
        athlete_ids = [
            int(value) for value in (item.get("athlete_ids") or [])
            if str(value).isdigit() and int(value) in all_athlete_ids
        ]
        if selection_id and name:
            dco_saved_selections.append({
                "id": selection_id,
                "name": name,
                "athlete_ids": athlete_ids,
                "athlete_ids_csv": ",".join(str(value) for value in athlete_ids),
                "is_standard": selection_id == (coach_settings.dco_standard_selection_id or ""),
            })
    standard_selection = next((item for item in dco_saved_selections if item["is_standard"]), None)
    requested_selection_mode = (request.GET.get("selection") or "").strip().lower()
    selection_mode = requested_selection_mode or ("selection" if standard_selection else "all")
    if selection_mode not in {"all", "selection", "trains", "planned_training"}:
        selection_mode = "all"
    selected_saved_selection_id = (request.GET.get("saved_selection") or "").strip()
    if not selected_saved_selection_id and not requested_selection_mode and standard_selection:
        selected_saved_selection_id = standard_selection["id"]

    if request.method == "POST" and request.POST.get("action") == "save_dco_selection":
        selected_ids = sorted({
            int(value) for value in request.POST.getlist("athletes")
            if str(value).isdigit() and int(value) in all_athlete_ids
        })
        selection_id = (request.POST.get("saved_selection") or "").strip()
        selection_name = (request.POST.get("selection_name") or "").strip()
        make_standard = request.POST.get("standard_selection") == "on"
        saved_rows = []
        updated = False
        for item in dco_saved_selections:
            row = {"id": item["id"], "name": item["name"], "athlete_ids": item["athlete_ids"]}
            if selection_id and item["id"] == selection_id:
                row.update({"name": selection_name or item["name"], "athlete_ids": selected_ids})
                updated = True
            saved_rows.append(row)
        if not updated and selection_name:
            selection_id = secrets.token_hex(8)
            saved_rows.append({"id": selection_id, "name": selection_name, "athlete_ids": selected_ids})
        if make_standard and selection_id:
            coach_settings.dco_standard_selection_id = selection_id
        elif selection_id == coach_settings.dco_standard_selection_id and not make_standard:
            coach_settings.dco_standard_selection_id = ""
        coach_settings.dco_saved_selections = saved_rows
        coach_settings.save(update_fields=["dco_saved_selections", "dco_standard_selection_id", "updated_at"])
        query = {"selection": "selection", "saved_selection": selection_id, "athletes": [str(value) for value in selected_ids]}
        return redirect(f"{reverse('trainer_stats')}?{urlencode(query, doseq=True)}")

    selected_saved_selection = next(
        (item for item in dco_saved_selections if item["id"] == selected_saved_selection_id), None
    )
    if selection_mode == "selection" and selected_saved_selection:
        selected_athlete_ids = set(selected_saved_selection["athlete_ids"])
    elif selection_mode == "selection":
        selected_athlete_ids = {
            int(value) for value in request.GET.getlist("athletes")
            if str(value).isdigit() and int(value) in all_athlete_ids
        }
    elif selection_mode == "trains":
        selected_athlete_ids = {
            int(value) for value in (coach_settings.dco_train_athlete_ids or [])
            if str(value).isdigit() and int(value) in all_athlete_ids
        }
    else:
        selected_athlete_ids = set(all_athlete_ids)

    plans = list(_filter_owned(TrainingPlan.objects.order_by("name"), request.user))
    this_week_start = date.today() - timedelta(days=date.today().weekday())
    previous_week_start = this_week_start - timedelta(days=7)
    rows = []
    for athlete in all_athletes:
        totals = _effective_week_distance_m(athlete, plans, previous_week_start)
        rows.append({
            "athlete": athlete,
            "has_planned_training": bool(totals[previous_week_start] or totals[this_week_start]),
            "previous_week_km": f"{totals[previous_week_start] / 1000.0:.1f}",
            "this_week_km": f"{totals[this_week_start] / 1000.0:.1f}",
        })
    if selection_mode == "planned_training":
        rows = [row for row in rows if row["has_planned_training"]]
        selected_athlete_ids = {row["athlete"].id for row in rows}
    elif selection_mode != "all":
        rows = [row for row in rows if row["athlete"].id in selected_athlete_ids]

    return render(request, "core/trainer_stats.html", {
        "rows": rows,
        "all_athletes": all_athletes,
        "selection_mode": selection_mode,
        "selected_athlete_ids": selected_athlete_ids,
        "dco_saved_selections": dco_saved_selections,
        "selected_saved_selection_id": selected_saved_selection_id,
        "previous_week_start": previous_week_start,
        "this_week_start": this_week_start,
    })


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
    dco_saved_selections = []
    for item in coach_settings.dco_saved_selections or []:
        if not isinstance(item, dict):
            continue
        selection_id = str(item.get("id") or "").strip()
        name = str(item.get("name") or "").strip()
        athlete_ids_for_selection = [
            int(value)
            for value in (item.get("athlete_ids") or [])
            if str(value).isdigit() and int(value) in all_athlete_ids
        ]
        if selection_id and name:
            dco_saved_selections.append({
                "id": selection_id,
                "name": name,
                "athlete_ids": athlete_ids_for_selection,
                "athlete_ids_csv": ",".join(str(value) for value in athlete_ids_for_selection),
                "is_standard": selection_id == (coach_settings.dco_standard_selection_id or ""),
            })
    standard_selection = next((item for item in dco_saved_selections if item["is_standard"]), None)

    requested_selection_mode = (request.GET.get("selection") or "").strip().lower()
    selection_mode = requested_selection_mode or ("selection" if standard_selection else "all")
    if selection_mode not in {"all", "selection", "trains", "planned_training"}:
        selection_mode = "all"
    selected_saved_selection_id = (request.GET.get("saved_selection") or "").strip()
    if not selected_saved_selection_id and not requested_selection_mode and standard_selection:
        selected_saved_selection_id = standard_selection["id"]

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

    if request.method == "POST" and request.POST.get("action") == "save_dco_selection":
        selected_ids = [
            int(value)
            for value in request.POST.getlist("athletes")
            if str(value).isdigit() and int(value) in all_athlete_ids
        ]
        selected_ids = sorted(set(selected_ids))
        selection_id = (request.POST.get("saved_selection") or "").strip()
        selection_name = (request.POST.get("selection_name") or "").strip()
        make_standard = request.POST.get("standard_selection") == "on"

        updated = False
        saved_rows = []
        for item in dco_saved_selections:
            row = {
                "id": item["id"],
                "name": item["name"],
                "athlete_ids": item["athlete_ids"],
            }
            if selection_id and item["id"] == selection_id:
                row["name"] = selection_name or item["name"]
                row["athlete_ids"] = selected_ids
                updated = True
            saved_rows.append(row)
        if not updated and selection_name:
            selection_id = secrets.token_hex(8)
            saved_rows.append({
                "id": selection_id,
                "name": selection_name,
                "athlete_ids": selected_ids,
            })

        if make_standard and selection_id:
            coach_settings.dco_standard_selection_id = selection_id
        elif selection_id and selection_id == coach_settings.dco_standard_selection_id:
            coach_settings.dco_standard_selection_id = ""
        elif coach_settings.dco_standard_selection_id and not any(row["id"] == coach_settings.dco_standard_selection_id for row in saved_rows):
            coach_settings.dco_standard_selection_id = ""
        coach_settings.dco_saved_selections = saved_rows
        coach_settings.save(update_fields=["dco_saved_selections", "dco_standard_selection_id", "updated_at"])

        redirect_query = {
            "date": request.POST.get("date") or date_value,
            "slots": request.POST.get("slots") or slot_filter,
            "selection": "selection",
            "saved_selection": selection_id,
            "athletes": [str(value) for value in selected_ids],
        }
        return redirect(f"{reverse('daily_overview')}?{urlencode(redirect_query, doseq=True)}")

    selected_athlete_ids = set()
    selected_saved_selection = next((item for item in dco_saved_selections if item["id"] == selected_saved_selection_id), None)
    if selection_mode == "selection" and selected_saved_selection:
        selected_athlete_ids = set(selected_saved_selection["athlete_ids"])
    else:
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
    elif selection_mode == "planned_training":
        athletes = all_athletes
        selected_athlete_ids = {athlete.id for athlete in athletes}
    else:
        athletes = all_athletes
        selected_athlete_ids = {athlete.id for athlete in athletes}

    show_results = request.GET.get("ok") == "1"
    athlete_ids = [a.id for a in athletes]

    check_map = {}
    for check in AthleteDayCheck.objects.filter(date=d, athlete_id__in=athlete_ids):
        check_map[(check.athlete_id, int(check.slot_index or 1))] = check

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
            .filter(athlete_id__in=athlete_ids, planning_kind=AthleteBasePlanningBlock.KIND_BASE)
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

        slot = _clone_slot_for_display(slot)
        _annotate_slot_segment_display_times(slot, athlete)
        return None if _slot_is_visually_empty(slot) else slot

    rows = []

    for athlete in athletes:

        check1 = check_map.get((athlete.id, 1))
        check2 = check_map.get((athlete.id, 2))
        status1 = check1.effective_status if check1 else ""
        status2 = check2.effective_status if check2 else ""
        slot1 = effective_daily_slot(athlete, 1)
        slot2 = effective_daily_slot(athlete, 2)

        rows.append({
            "athlete": athlete,
            "slot1": slot1,
            "slot2": slot2,
            "check1": check1,
            "check2": check2,
            "check1_badge": _daily_status_badge(status1),
            "check2_badge": _daily_status_badge(status2),
            "comment": comment_map.get(athlete.id),
        })

    if selection_mode == "planned_training":
        rows = [
            row for row in rows
            if ((slot_filter in {"am", "both"} and row["slot1"]) or (slot_filter in {"pm", "both"} and row["slot2"]))
        ]

    selection_query = {
        "date": date_value,
        "slots": slot_filter,
        "selection": selection_mode,
    }
    if selection_mode == "selection":
        if selected_saved_selection_id:
            selection_query["saved_selection"] = selected_saved_selection_id
        selection_query["athletes"] = [str(athlete_id) for athlete_id in sorted(selected_athlete_ids)]
    selection_url = f"{reverse('daily_overview')}?{urlencode(selection_query, doseq=True)}"
    day_nav_query = dict(selection_query)
    if show_results:
        day_nav_query["ok"] = "1"
    previous_day_query = dict(day_nav_query)
    previous_day_query["date"] = (d - timedelta(days=1)).isoformat()
    next_day_query = dict(day_nav_query)
    next_day_query["date"] = (d + timedelta(days=1)).isoformat()

    return render(request, "core/daily_overview.html", {
        "rows": rows,
        "date": d,
        "date_value": date_value,
        "slot_filter": slot_filter,
        "selection_mode": selection_mode,
        "all_athletes": all_athletes,
        "selected_athlete_ids": selected_athlete_ids,
        "dco_train_athlete_ids": dco_train_athlete_ids,
        "dco_saved_selections": dco_saved_selections,
        "selected_saved_selection_id": selected_saved_selection_id,
        "show_results": show_results,
        "show_am": slot_filter in {"am", "both"},
        "show_pm": slot_filter in {"pm", "both"},
        "selection_url": selection_url,
        "previous_day_url": f"{reverse('daily_overview')}?{urlencode(previous_day_query, doseq=True)}",
        "next_day_url": f"{reverse('daily_overview')}?{urlencode(next_day_query, doseq=True)}",
    })
