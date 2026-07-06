from datetime import date, timedelta
import calendar as py_calendar

from django.http import HttpResponse
from django.shortcuts import render, get_object_or_404, redirect
from django.urls import reverse
from django.views.decorators.http import require_GET, require_http_methods
from django.contrib.auth.decorators import login_required
from django.db.models.functions import Lower
from django.core.cache import cache

from core.models import TrainingPlan, Athlete, Group, PlanMembership, CoachSettings, TrainingSlot, PlanWeekPhase, SavedTrainingTemplate, RaceEvent, RaceEventDistance, RaceEntry
from core.parser import parse_segment_text
from core.stats import STATS_VERSION_KEY
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
    s = (value or "").strip()
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


@login_required
@require_GET
def dashboard_view(request):
    from datetime import date

    athlete = _athlete_for_user(request.user)
    is_athlete_user = bool(athlete and not request.user.is_staff and not request.user.is_superuser)
    groups = Group.objects.none() if is_athlete_user else _filter_owned(Group.objects.all(), request.user)

    return render(request, "core/dashboard.html", {
        "groups": groups,
        "today": date.today(),
        "is_athlete_user": is_athlete_user,
        "current_athlete": athlete,
    })


@login_required
@require_GET
def coach_console_view(request):
    return render(request, "core/coach_console.html")


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

    if coach_selected and athlete_selected and target_selected:
        return 3
    if coach_selected and athlete_selected:
        return 2
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

    return plans


def _invalidate_race_training_stats_cache():
    try:
        cache.incr(STATS_VERSION_KEY)
    except Exception:
        cache.set(STATS_VERSION_KEY, 1, None)


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
                if existing_segments and all((seg.special or "") in ("RACE", "IMPORTANT_RACE") for seg in existing_segments):
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

        for athlete in athletes:
            for race in races:
                affected_race_athletes.add((athlete.id, race.id))
                allowed_distance_ids = {str(distance.id) for distance in distances_by_race_id.get(race.id, [])}
                athlete_selected_ids = {
                    value for value in request.POST.getlist(f"athlete_distances_{race.id}_{athlete.id}")
                    if value in allowed_distance_ids
                }

                if not is_athlete_user:
                    coach_selected_ids = {
                        value for value in request.POST.getlist(f"coach_distances_{race.id}_{athlete.id}")
                        if value in allowed_distance_ids
                    }
                    target_selected_ids = {
                        value for value in request.POST.getlist(f"target_distances_{race.id}_{athlete.id}")
                        if value in allowed_distance_ids
                    }
                    posted_selected_ids = list(coach_selected_ids | target_selected_ids)[:3]
                    posted_selected_id_set = set(posted_selected_ids)
                else:
                    coach_selected_ids = set()
                    target_selected_ids = set()
                    posted_selected_ids = list(athlete_selected_ids)[:3]
                    posted_selected_id_set = set(posted_selected_ids)

                for distance in distances_by_race_id.get(race.id, []):
                    distance_id = str(distance.id)
                    existing_entry = RaceEntry.objects.filter(race_distance=distance, athlete=athlete).first()

                    if is_athlete_user:
                        coach_selected = bool(existing_entry and existing_entry.coach_selected)
                        target_selected = bool(existing_entry and existing_entry.target_selected)
                        athlete_selected = distance_id in athlete_selected_ids and distance_id in posted_selected_id_set
                    else:
                        coach_selected = distance_id in coach_selected_ids and distance_id in posted_selected_id_set
                        target_selected = distance_id in target_selected_ids and distance_id in posted_selected_id_set
                        athlete_selected = bool(getattr(existing_entry, "athlete_selected", False))

                    if not coach_selected and not athlete_selected and not target_selected:
                        if existing_entry:
                            existing_entry.delete()
                        continue

                    RaceEntry.objects.update_or_create(
                        race_distance=distance,
                        athlete=athlete,
                        defaults={
                            "coach_selected": coach_selected,
                            "athlete_selected": athlete_selected,
                            "target_selected": target_selected,
                        },
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
                    "coach_selected": bool(entry and entry.coach_selected),
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

        # Sync naar session
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

    # Sync naar session
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

    plans = _exclude_flex_planner_plans(_filter_owned(qs, request.user))
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

    plans = _exclude_flex_planner_plans(_filter_owned(qs, request.user))

    if request.method == "POST":
        form["name"] = (request.POST.get("name") or "").strip()
        form["start_date"] = (request.POST.get("start_date") or "").strip()
        form["end_date"] = (request.POST.get("end_date") or "").strip()
        form["copy_source_plan_id"] = (request.POST.get("copy_source_plan_id") or "").strip()

        # ✅ NEW: plan setting
        form["week_phases_enabled"] = (request.POST.get("week_phases_enabled") == "on")
        form["is_private"] = (request.POST.get("is_private") == "on")

        if not form["name"]:
            errors.append("Naam is verplicht.")

        try:
            start_d = _parse_iso_date(form["start_date"])
        except ValueError:
            start_d = None
            errors.append("Startdatum is ongeldig (gebruik YYYY-MM-DD).")

        try:
            end_d = _parse_iso_date(form["end_date"])
        except ValueError:
            end_d = None
            errors.append("Einddatum is ongeldig (gebruik YYYY-MM-DD).")

        if (start_d and not end_d) or (end_d and not start_d):
            errors.append("Vul óf beide datums in, óf geen (start + eind).")

        if start_d and end_d and start_d > end_d:
            errors.append("Startdatum mag niet na einddatum liggen.")

        source_plan = None
        if form["copy_source_plan_id"]:
            try:
                source_plan_id = int(form["copy_source_plan_id"])
            except ValueError:
                source_plan_id = None
                errors.append("Bronplan is ongeldig.")
            if source_plan_id is not None:
                source_plan = _exclude_flex_planner_plans(_filter_owned(TrainingPlan.objects.all(), request.user)).filter(id=source_plan_id).first()
                if not source_plan:
                    errors.append("Bronplan is niet gevonden.")
                elif not start_d or not end_d or not source_plan.start_date or not source_plan.end_date:
                    errors.append("Plan kopiëren kan alleen als zowel nieuw plan als bronplan een start- en einddatum hebben.")

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
    plan = get_object_or_404(_filter_owned(TrainingPlan.objects.all(), request.user), id=plan_id)

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
            errors.append("Naam is verplicht.")

        try:
            start_d = _parse_iso_date(form["start_date"])
        except ValueError:
            start_d = None
            errors.append("Startdatum is ongeldig (gebruik YYYY-MM-DD).")

        try:
            end_d = _parse_iso_date(form["end_date"])
        except ValueError:
            end_d = None
            errors.append("Einddatum is ongeldig (gebruik YYYY-MM-DD).")

        if (start_d and not end_d) or (end_d and not start_d):
            errors.append("Vul óf beide datums in, óf geen (start + eind).")

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
    plan = get_object_or_404(_filter_owned(TrainingPlan.objects.all(), request.user), id=plan_id)

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
    athletes = _filter_owned(Athlete.objects.order_by("name"), request.user)
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
        "is_private": False,
        "view_weeks_ahead": 2,
        "training_reports_enabled": True,
        "week_report_enabled": False,
        "daily_vitals_enabled": False,
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
        form["is_private"] = (request.POST.get("is_private") == "on")
        form["view_weeks_ahead"] = (request.POST.get("view_weeks_ahead") or "2").strip()
        form["training_reports_enabled"] = (request.POST.get("training_reports_enabled") == "on")
        form["week_report_enabled"] = (request.POST.get("week_report_enabled") == "on")
        form["daily_vitals_enabled"] = (request.POST.get("daily_vitals_enabled") == "on")

        for z in ("1", "2", "3", "4", "5"):
            form[f"z{z}_pace"] = (request.POST.get(f"z{z}_pace") or "").strip()

        if not form["name"]:
            errors.append("Naam is verplicht.")

        try:
            birth_year = _parse_int(form["birth_year"])
        except ValueError:
            birth_year = None
            errors.append("Geboortejaar is ongeldig (gebruik een getal).")
        if birth_year is None:
            errors.append("Geboortejaar is verplicht.")
        elif birth_year < 1900 or birth_year > 2100:
            errors.append("Geboortejaar lijkt niet geldig.")

        gender = (form["gender"] or "").strip().upper()
        if gender not in ("M", "V", "X"):
            errors.append("Geslacht is verplicht en moet M, V of X zijn.")

        try:
            vdot = _parse_float(form["vdot"])
            if vdot is not None and vdot < 0:
                errors.append("VDOT kan niet negatief zijn.")
        except ValueError:
            vdot = None
            errors.append("VDOT is ongeldig (gebruik een getal).")

        try:
            view_weeks_ahead = int(form["view_weeks_ahead"])
            if view_weeks_ahead < 0:
                errors.append("Weken vooruit mag niet negatief zijn.")
        except ValueError:
            view_weeks_ahead = 2
            errors.append("Weken vooruit is ongeldig (gebruik een getal).")

        try:
            pr_800_s = _parse_pr_time_to_seconds(form["pr_800"])
        except ValueError:
            pr_800_s = None
            errors.append("T800 is verplicht en moet in formaat m:ss(.ms), h:mm:ss(.ms) of mm.ss.ms zijn.")

        try:
            pr_1500_s = _parse_pr_time_to_seconds(form["pr_1500"])
        except ValueError:
            pr_1500_s = None
            errors.append("T1500 is verplicht en moet in formaat m:ss(.ms), h:mm:ss(.ms) of mm.ss.ms zijn.")

        try:
            pr_3000_s = _parse_pr_time_to_seconds(form["pr_3000"])
        except ValueError:
            pr_3000_s = None
            errors.append("T3000 is verplicht en moet in formaat m:ss(.ms), h:mm:ss(.ms) of mm.ss.ms zijn.")

        try:
            pr_5000_s = _parse_pr_time_to_seconds(form["pr_5000"])
        except ValueError:
            pr_5000_s = None
            errors.append("T5000 is verplicht en moet in formaat m:ss(.ms), h:mm:ss(.ms) of mm.ss.ms zijn.")

        try:
            pr_10000_s = _parse_pr_time_to_seconds(form["pr_10000"])
        except ValueError:
            pr_10000_s = None
            errors.append("T10000 is verplicht en moet in formaat m:ss(.ms), h:mm:ss(.ms) of mm.ss.ms zijn.")

        try:
            tm_s = _parse_pr_time_to_seconds(form["tm"]) if form["tm"] else None
        except ValueError:
            tm_s = None
            errors.append("TM ongeldig formaat.")

        try:
            thm_s = _parse_pr_time_to_seconds(form["thm"]) if form["thm"] else None
        except ValueError:
            thm_s = None
            errors.append("THM ongeldig formaat.")

        try:
            t4_s = _parse_pr_time_to_seconds(form["t4"]) if form["t4"] else None
        except ValueError:
            t4_s = None
            errors.append("T4 ongeldig formaat.")

        if form["zone_method"] != "manual":
            errors.append("Zone-methode is nog niet ondersteund. Kies voorlopig 'manual'.")

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
                pr_800_s=pr_800_s,
                pr_1500_s=pr_1500_s,
                pr_3000_s=pr_3000_s,
                pr_5000_s=pr_5000_s,
                pr_10000_s=pr_10000_s,
                pr_tm_s=tm_s,
                pr_thm_s=thm_s,
                pr_400_s=t4_s,
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
    saved_notice = None

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
        "is_private": getattr(athlete, "is_private", False),
        "view_weeks_ahead": getattr(athlete, "view_weeks_ahead", 2),
        "training_reports_enabled": getattr(athlete, "training_reports_enabled", True),
        "week_report_enabled": getattr(athlete, "week_report_enabled", False),
        "daily_vitals_enabled": getattr(athlete, "daily_vitals_enabled", False),
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
        form["is_private"] = (request.POST.get("is_private") == "on")
        form["view_weeks_ahead"] = (request.POST.get("view_weeks_ahead") or "2").strip()
        form["training_reports_enabled"] = (request.POST.get("training_reports_enabled") == "on")
        form["week_report_enabled"] = (request.POST.get("week_report_enabled") == "on")
        form["daily_vitals_enabled"] = (request.POST.get("daily_vitals_enabled") == "on")

        athlete.training_reports_enabled = form["training_reports_enabled"]
        athlete.week_report_enabled = form["week_report_enabled"]
        athlete.daily_vitals_enabled = form["daily_vitals_enabled"]
        athlete.save(update_fields=[
            "training_reports_enabled",
            "week_report_enabled",
            "daily_vitals_enabled",
        ])

        for z in ("1", "2", "3", "4", "5"):
            form[f"z{z}_pace"] = (request.POST.get(f"z{z}_pace") or "").strip()

        if not form["name"]:
            errors.append("Naam is verplicht.")

        try:
            birth_year = _parse_int(form["birth_year"])
        except ValueError:
            birth_year = None
            errors.append("Geboortejaar is ongeldig (gebruik een getal).")
        if birth_year is None:
            errors.append("Geboortejaar is verplicht.")
        elif birth_year < 1900 or birth_year > 2100:
            errors.append("Geboortejaar lijkt niet geldig.")

        gender = (form["gender"] or "").strip().upper()
        if gender not in ("M", "V", "X"):
            errors.append("Geslacht is verplicht en moet M, V of X zijn.")

        try:
            vdot = _parse_float(form["vdot"])
            if vdot is not None and vdot < 0:
                errors.append("VDOT kan niet negatief zijn.")
        except ValueError:
            vdot = None
            errors.append("VDOT is ongeldig (gebruik een getal).")

        try:
            view_weeks_ahead = int(form["view_weeks_ahead"])
            if view_weeks_ahead < 0:
                errors.append("Weken vooruit mag niet negatief zijn.")
        except ValueError:
            view_weeks_ahead = 2
            errors.append("Weken vooruit is ongeldig (gebruik een getal).")

        try:
            pr_800_s = _parse_pr_time_to_seconds(form["pr_800"])
        except ValueError:
            pr_800_s = None
            errors.append("T800 is verplicht en moet in formaat m:ss(.ms), h:mm:ss(.ms) of mm.ss.ms zijn.")

        try:
            pr_1500_s = _parse_pr_time_to_seconds(form["pr_1500"])
        except ValueError:
            pr_1500_s = None
            errors.append("T1500 is verplicht en moet in formaat m:ss(.ms), h:mm:ss(.ms) of mm.ss.ms zijn.")

        try:
            pr_3000_s = _parse_pr_time_to_seconds(form["pr_3000"])
        except ValueError:
            pr_3000_s = None
            errors.append("T3000 is verplicht en moet in formaat m:ss(.ms), h:mm:ss(.ms) of mm.ss.ms zijn.")

        try:
            pr_5000_s = _parse_pr_time_to_seconds(form["pr_5000"])
        except ValueError:
            pr_5000_s = None
            errors.append("T5000 is verplicht en moet in formaat m:ss(.ms), h:mm:ss(.ms) of mm.ss.ms zijn.")

        try:
            pr_10000_s = _parse_pr_time_to_seconds(form["pr_10000"])
        except ValueError:
            pr_10000_s = None
            errors.append("T10000 is verplicht en moet in formaat m:ss(.ms), h:mm:ss(.ms) of mm.ss.ms zijn.")

        try:
            tm_s = _parse_pr_time_to_seconds(form["tm"]) if form["tm"] else None
        except ValueError:
            tm_s = None
            errors.append("TM ongeldig formaat.")

        try:
            thm_s = _parse_pr_time_to_seconds(form["thm"]) if form["thm"] else None
        except ValueError:
            thm_s = None
            errors.append("THM ongeldig formaat.")

        try:
            t4_s = _parse_pr_time_to_seconds(form["t4"]) if form["t4"] else None
        except ValueError:
            t4_s = None
            errors.append("T4 ongeldig formaat.")

        if form["zone_method"] != "manual":
            errors.append("Zone-methode is nog niet ondersteund. Kies voorlopig 'manual'.")

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
            athlete.pr_800_s = pr_800_s
            athlete.pr_1500_s = pr_1500_s
            athlete.pr_3000_s = pr_3000_s
            athlete.pr_5000_s = pr_5000_s
            athlete.pr_10000_s = pr_10000_s
            athlete.pr_tm_s = tm_s
            athlete.pr_thm_s = thm_s
            athlete.pr_400_s = t4_s
            athlete.is_private = form["is_private"]
            athlete.save()

            saved_notice = "Opgeslagen."

            speeds = athlete.get_zone_speed_mps()
            zones_form = zones_form_from_speeds(unit, speeds)
            for k, v in zones_form.items():
                form[k] = v

    return render(
        request,
        "core/coach_athlete_form.html",
        {"mode": "edit", "athlete": athlete, "form": form, "errors": errors, "saved_notice": saved_notice},
    )


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
            errors.append("Groepsnaam is verplicht.")

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
            errors.append("Groepsnaam is verplicht.")

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
            errors.append("Vul eerst start_date en end_date in bij dit plan voordat je targets koppelt.")

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
                            f"Overlap/conflict: {a_name} zit al in plan '{op.name}', maar dat plan heeft geen start/einddatum."
                        )
                        continue
                    if _ranges_overlap(plan.start_date, plan.end_date, op.start_date, op.end_date):
                        a = Athlete.objects.filter(id=aid).first()
                        a_name = a.name if a else f"athlete_id={aid}"
                        errors.append(
                            f"Overlap/conflict: {a_name} zit al in plan '{op.name}' ({op.start_date} t/m {op.end_date})."
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
from core.views.calendar import _build_effective_slot_maps


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

    group_id = request.GET.get("group_id")
    d = request.GET.get("date")

    if not group_id or not d:
        return redirect("/")

    try:
        d = date.fromisoformat(d)
    except Exception:
        return redirect("/")

    group = get_object_or_404(_filter_owned(Group.objects.all(), request.user), id=group_id)
    athletes = list(group.athletes.all().order_by("name"))
    athlete_ids = [a.id for a in athletes]

    check_map = {}
    for check in AthleteDayCheck.objects.filter(date=d, athlete_id__in=athlete_ids):
        check_map[(check.athlete_id, int(check.slot_index or 1))] = check.effective_status

    comment_map = {}
    for comment in AthleteDayComment.objects.filter(date=d, athlete_id__in=athlete_ids):
        comment_map[comment.athlete_id] = comment

    rows = []

    for athlete in athletes:
        athlete_plans = []

        for plan in _filter_owned(TrainingPlan.objects.order_by("name"), request.user):
            if athlete.id not in plan.targeted_athlete_ids():
                continue
            if plan.start_date and plan.start_date > d:
                continue
            if plan.end_date and plan.end_date < d:
                continue
            athlete_plans.append(plan)

        if athlete_plans:
            slot_qs = (
                TrainingSlot.objects
                .filter(date=d, plan__in=athlete_plans)
                .filter(Q(athlete__isnull=True) | Q(athlete=athlete))
                .prefetch_related("segments")
                .select_related("plan", "athlete")
            )
            slot_map, _ = _build_effective_slot_maps(slot_qs)
        else:
            slot_map = {}

        status1 = check_map.get((athlete.id, 1), "")
        status2 = check_map.get((athlete.id, 2), "")

        rows.append({
            "athlete": athlete,
            "slot1": slot_map.get((d, 1)),
            "slot2": slot_map.get((d, 2)),
            "check1_badge": _daily_status_badge(status1),
            "check2_badge": _daily_status_badge(status2),
            "comment": comment_map.get(athlete.id),
        })

    return render(request, "core/daily_overview.html", {
        "rows": rows,
        "date": d,
        "group": group,
    })
