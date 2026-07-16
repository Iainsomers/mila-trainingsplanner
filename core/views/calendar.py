from datetime import date, timedelta
import re

from django.http import HttpResponse, HttpResponseBadRequest
from django.shortcuts import render, redirect
from django.utils.html import escape
from django.utils import timezone
from django.db.models import Q, Prefetch
from django.core.cache import cache
from django.contrib.auth.decorators import login_required

from core.models import (
    CoachSettings,
    AthleteDayCheck,
    AthleteDayComment,
    TrainingSlot,
    TrainingSegment,
    TrainingPlan,
    Athlete,
    Group,
    AthleteBasePlanningBlock,
    AthleteBasePlanningSlot,
    PlanWeekPhase,
    AthleteWeekPhaseOverride,
    AthleteWeekReport,
    AthleteDailyVital,
    CoachAccess,
    RaceEntry,
)
from core.stats import base_week_stats, athlete_week_stats, group_week_stats, STATS_VERSION_KEY
from core.parser import parse_segment_text
from core.wucd import apply_auto_wucd_texts
from .common import (
    _calendar_display_mode,
    _get_selected_plan,
    _get_selected_athlete_from_request,
    _format_km,
    _pct,
    _apply_parse_to_segment,
    _compute_norm_distance_m,
)

from core.views.slots import (
    _expand_repeated_core_set_parts,
    _core_zone_range_parts,
    _core_t_range_parts,
    _parse_core_segment_text,
)


def _athlete_plan_for_day(athlete_plans, day):
    for plan in athlete_plans or []:
        if plan.start_date and plan.start_date > day:
            continue
        if plan.end_date and plan.end_date < day:
            continue
        return plan
    return None


def _shared_owner_ids(user):
    if not user.is_authenticated:
        return []
    return list(CoachAccess.objects.filter(grantee=user).values_list("owner_id", flat=True))


def _filter_owned(qs, user):
    if user.is_superuser:
        return qs
    return qs.filter(owner=user)


def _filter_accessible(qs, user):
    if user.is_superuser:
        return qs

    model = getattr(qs, "model", None)
    shared_owner_ids = _shared_owner_ids(user)

    if model is TrainingPlan:
        return qs.filter(
            Q(owner=user) |
            Q(owner_id__in=shared_owner_ids, is_private=False)
        ).distinct()

    if model is Athlete:
        return qs.filter(
            Q(owner=user) |
            Q(owner_id__in=shared_owner_ids, is_private=False)
        ).distinct()

    return _filter_owned(qs, user)


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


@login_required
def calendar_test(request):
    slots = TrainingSlot.objects.order_by("date", "slot_index", "athlete_id")
    lines = []
    for s in slots:
        who = f" athlete={s.athlete_id}" if s.athlete_id else ""
        lines.append(f"{s.date} slot {s.slot_index}{who}: {escape(s.core_text())}")
    return HttpResponse("<br>".join(lines) or "no slots")


def _build_effective_slot_maps(slot_qs):
    base_map = {}
    override_map = {}

    for s in slot_qs:
        key = (s.date, s.slot_index)
        if s.athlete_id:
            override_map[key] = s
        else:
            base_map[key] = s

    slot_map = dict(base_map)
    slot_map.update(override_map)
    has_fix_keys = set(override_map.keys())
    return slot_map, has_fix_keys



def _slot_is_visually_empty(slot) -> bool:
    if not slot:
        return True
    try:
        return not slot.segments.exists()
    except Exception:
        return False


def _visible_year_slot(slot_map, has_fix_keys, key):
    slot = slot_map.get(key)
    if key in has_fix_keys and _slot_is_visually_empty(slot):
        return None
    return slot


def _slot_has_race(slot) -> bool:
    if not slot:
        return False
    try:
        for seg in slot.segments.all():
            special = (getattr(seg, "special", "") or "").upper()
            text = (getattr(seg, "text", "") or "").lower()
            if special in {"RACE", "IMPORTANT_RACE"} or "race" in text:
                return True
    except Exception:
        return False
    return False

def _km_str_with_small(meters) -> str:
    try:
        m = float(meters or 0)
    except Exception:
        m = 0.0
    if 0 < m < 50:
        return "<0.1"
    return _format_km(m)


def _to_week_start(d: date) -> date:
    return d - timedelta(days=d.weekday())


# -----------------------------
# BASE week phase (plan)
# -----------------------------
@login_required
def week_phase_set(request, y: int, m: int, d: int):
    if request.method != "POST":
        return HttpResponseBadRequest("POST required")

    plan_id = request.GET.get("plan")
    if not plan_id:
        return HttpResponseBadRequest("Missing plan")

    try:
        plan = _filter_accessible(TrainingPlan.objects.all(), request.user).get(id=int(plan_id))
    except Exception:
        return HttpResponseBadRequest("Invalid plan")

    try:
        raw_date = date(int(y), int(m), int(d))
    except Exception:
        return HttpResponseBadRequest("Invalid date")

    if hasattr(plan, "week_phases_enabled") and not bool(plan.week_phases_enabled):
        return HttpResponseBadRequest("Week phases disabled for this plan")

    week_start = _to_week_start(raw_date)

    phase = (request.POST.get("phase") or "").strip()
    allowed = {"", "recovery", "aerobe", "specific", "intense", "taper"}
    if phase not in allowed:
        return HttpResponseBadRequest("Invalid phase")

    if phase == "":
        PlanWeekPhase.objects.filter(plan=plan, week_start=week_start).delete()
    else:
        PlanWeekPhase.objects.update_or_create(
            plan=plan,
            week_start=week_start,
            defaults={"phase": phase},
        )

    return HttpResponse("", status=204)


# -----------------------------
# OVERRIDE week phase (athlete)
# -----------------------------
@login_required
def athlete_week_phase_set(request, y: int, m: int, d: int):
    """
    POST /athlete-week-phase/YYYY/MM/DD/?plan=<id>&athlete=<id>
    body: phase = "" | recovery | aerobe | specific | intense | taper

    phase=="" => delete override => fallback to plan phase
    """
    if request.method != "POST":
        return HttpResponseBadRequest("POST required")

    plan_id = request.GET.get("plan")
    athlete_id = request.GET.get("athlete")
    if not plan_id or not athlete_id:
        return HttpResponseBadRequest("Missing plan/athlete")

    try:
        plan = _filter_accessible(TrainingPlan.objects.all(), request.user).get(id=int(plan_id))
    except Exception:
        return HttpResponseBadRequest("Invalid plan")

    try:
        athlete = Athlete.objects.get(id=int(athlete_id))
    except Exception:
        return HttpResponseBadRequest("Invalid athlete")

    try:
        raw_date = date(int(y), int(m), int(d))
    except Exception:
        return HttpResponseBadRequest("Invalid date")

    if hasattr(plan, "week_phases_enabled") and not bool(plan.week_phases_enabled):
        return HttpResponseBadRequest("Week phases disabled for this plan")

    week_start = _to_week_start(raw_date)

    ids = plan.targeted_athlete_ids() if plan else set()
    if athlete.id not in ids and not _is_flex_planner_plan(plan):
        return HttpResponseBadRequest("Athlete not targeted by this plan")

    phase = (request.POST.get("phase") or "").strip()
    allowed = {"", "recovery", "aerobe", "specific", "intense", "taper"}
    if phase not in allowed:
        return HttpResponseBadRequest("Invalid phase")

    if phase == "":
        AthleteWeekPhaseOverride.objects.filter(plan=plan, athlete=athlete, week_start=week_start).delete()
    else:
        AthleteWeekPhaseOverride.objects.update_or_create(
            plan=plan,
            athlete=athlete,
            week_start=week_start,
            defaults={"phase": phase},
        )

    return HttpResponse("", status=204)


@login_required
def calendar_view(request):
    plans = (
        _filter_accessible(TrainingPlan.objects.order_by("name"), request.user)
        .exclude(name__startswith="Flex Planner")
        .exclude(plan_kind=TrainingPlan.PLAN_KIND_TRAINER)
    )

    selected_plan = None
    plan_id = request.GET.get("plan")
    if plan_id:
        try:
            selected_plan = _filter_accessible(TrainingPlan.objects.all(), request.user).get(id=int(plan_id))
        except Exception:
            selected_plan = None
    else:
        fallback_plan = _get_selected_plan(request)
        if fallback_plan and _filter_accessible(TrainingPlan.objects.filter(id=fallback_plan.id), request.user).exists():
            selected_plan = fallback_plan
        else:
            selected_plan = plans.first()

    if selected_plan and getattr(selected_plan, "plan_kind", "") == TrainingPlan.PLAN_KIND_TRAINER:
        return redirect("trainer_planning_detail", plan_id=selected_plan.id)

    selected_athlete = _get_selected_athlete_from_request(request)
    if selected_athlete and not _filter_accessible(Athlete.objects.filter(id=selected_athlete.id), request.user).exists():
        selected_athlete = None

    plan_athletes = []
    if selected_plan:
        ids = set(selected_plan.targeted_athlete_ids())
        ids |= set(
            TrainingSlot.objects
            .filter(plan=selected_plan, athlete__isnull=False)
            .values_list("athlete_id", flat=True)
        )
        ids.discard(None)
        plan_athletes = list(_filter_accessible(Athlete.objects.filter(id__in=ids).order_by("name"), request.user))
        if selected_athlete and selected_athlete.id not in ids:
            return redirect(f"/calendar/?plan={selected_plan.id}")

    # window
    if selected_plan and selected_plan.start_date:
        start = selected_plan.start_date - timedelta(days=selected_plan.start_date.weekday())
    else:
        today = date.today()
        start = today - timedelta(days=today.weekday())

    if selected_plan and selected_plan.end_date:
        end_inclusive = selected_plan.end_date + timedelta(days=(6 - selected_plan.end_date.weekday()))
        end = end_inclusive + timedelta(days=1)
        weeks = ((end - start).days // 7)
        if weeks < 1:
            weeks = 1
    else:
        weeks = 8
        end = start + timedelta(days=7 * weeks)

    if selected_plan:
        slot_q = TrainingSlot.objects.filter(date__gte=start, date__lt=end, plan=selected_plan)
        if selected_athlete:
            slot_q = slot_q.filter(Q(athlete__isnull=True) | Q(athlete=selected_athlete))
        else:
            slot_q = slot_q.filter(athlete__isnull=True)
    else:
        slot_q = TrainingSlot.objects.none()

    slot_q = slot_q.prefetch_related("segments")
    slot_map, has_fix_keys = _build_effective_slot_maps(slot_q)

    week_starts = [start + timedelta(days=7 * i) for i in range(weeks)]

    base_phase_by_week = {}
    if selected_plan:
        for obj in PlanWeekPhase.objects.filter(plan=selected_plan, week_start__in=week_starts):
            base_phase_by_week[obj.week_start] = (obj.phase or "")

    athlete_phase_by_week = {}
    if selected_plan and selected_athlete:
        for obj in AthleteWeekPhaseOverride.objects.filter(plan=selected_plan, athlete=selected_athlete, week_start__in=week_starts):
            athlete_phase_by_week[obj.week_start] = (obj.phase or "")

    phase_label = {
        "": "",
        "recovery": "Recovery",
        "aerobe": "Aerobe",
        "specific": "Specific",
        "intense": "Intense",
        "taper": "Taper",
    }

    week_rows = []
    d = start
    for _ in range(weeks):
        week_start = d
        week_end = d + timedelta(days=6)
        days = [week_start + timedelta(days=i) for i in range(7)]

        cells1, cells2 = [], []
        for day in days:
            k1 = (day, 1)
            k2 = (day, 2)
            cells1.append({"day": day, "slot": slot_map.get(k1), "is_override": (k1 in has_fix_keys)})
            cells2.append({"day": day, "slot": slot_map.get(k2), "is_override": (k2 in has_fix_keys)})

        z_m = {str(i): 0.0 for i in range(1, 7)}
        z_time_s = {str(i): 0.0 for i in range(1, 7)}
        race_m = 0.0
        race_time_s = 0.0
        t_m = {
            "10000": 0.0,
            "5000": 0.0,
            "3000": 0.0,
            "1500": 0.0,
            "800": 0.0,
            "TM": 0.0,
            "THM": 0.0,
            "T4": 0.0,
        }

        alt_z1_min = 0
        alt_z2_min = 0
        alt_z3_min = 0

        if selected_plan:
            if selected_athlete:
                st = athlete_week_stats(selected_plan, selected_athlete, week_start)
            elif plan_athletes:
                st = group_week_stats(selected_plan, plan_athletes, week_start)
            else:
                st = base_week_stats(selected_plan, week_start)

            zones = st.get("zones") or {}
            race = st.get("race") or {"distance_m": 0, "duration_s": 0}
            t_totals = st.get("t_totals") or {}

            alt = st.get("alt_zones") or {}
            alt_z1_min = int(round(float(alt.get("1", {}).get("duration_s", 0) or 0) / 60.0))
            alt_z2_min = int(round(float(alt.get("2", {}).get("duration_s", 0) or 0) / 60.0))
            alt_z3_min = int(round(float(alt.get("3", {}).get("duration_s", 0) or 0) / 60.0))

            for z in ("1", "2", "3", "4", "5", "6"):
                vals = zones.get(z) or {"distance_m": 0, "duration_s": 0}
                z_m[z] = float(vals.get("distance_m") or 0)
                z_time_s[z] = float(vals.get("duration_s") or 0)

            race_m = float(race.get("distance_m") or 0)
            race_time_s = float(race.get("duration_s") or 0)

            for t in ("10000", "5000", "3000", "1500", "800", "TM", "THM", "T4"):
                vals = t_totals.get(t) or {"distance_m": 0, "duration_s": 0}
                t_m[t] = float(vals.get("distance_m") or 0)

        tot_m = sum(z_m.values()) + race_m
        total_time_s = sum(z_time_s.values()) + race_time_s

        def _fmt_min(t_s: float) -> str:
            return f"{int(round(float(t_s) / 60.0))}'"

        sum_pct_tooltip = (
            f"Z1: {_fmt_min(z_time_s['1'])}/{_pct(z_time_s['1'], total_time_s)}\n"
            f"Z2: {_fmt_min(z_time_s['2'])}/{_pct(z_time_s['2'], total_time_s)}\n"
            f"Z3: {_fmt_min(z_time_s['3'])}/{_pct(z_time_s['3'], total_time_s)}\n"
            f"Z4: {_fmt_min(z_time_s['4'])}/{_pct(z_time_s['4'], total_time_s)}\n"
            f"Z5: {_fmt_min(z_time_s['5'])}/{_pct(z_time_s['5'], total_time_s)}\n"
            f"Z6: {_fmt_min(z_time_s['6'])}/{_pct(z_time_s['6'], total_time_s)}\n"
            f"Race: {_fmt_min(race_time_s)}/{_pct(race_time_s, total_time_s)}"
        )

        has_z = {z: (z_m[z] > 0) for z in ("1", "2", "3", "4", "5", "6")}
        has_race = (race_m > 0)
        has_t = {t: (t_m[t] > 0) for t in ("10000", "5000", "3000", "1500", "800", "TM", "THM", "T4")}

        base_phase = base_phase_by_week.get(week_start, "")
        athlete_phase = athlete_phase_by_week.get(week_start, "")

        effective_phase = athlete_phase if (selected_athlete and athlete_phase) else base_phase
        is_phase_override = bool(selected_athlete and athlete_phase)

        has_alt = (alt_z1_min > 0 or alt_z2_min > 0 or alt_z3_min > 0)

        week_rows.append({
            "week_start": week_start,
            "week_end": week_end,
            "cells1": cells1,
            "cells2": cells2,
            "week_phase_base": base_phase,
            "week_phase_athlete": athlete_phase,
            "week_phase": effective_phase,
            "week_phase_is_override": is_phase_override,
            "week_phase_label": phase_label.get(effective_phase, ""),
            "sum_tot_km": _format_km(tot_m),
            "sum_z1_km": _km_str_with_small(z_m["1"]),
            "sum_z2_km": _km_str_with_small(z_m["2"]),
            "sum_z3_km": _km_str_with_small(z_m["3"]),
            "sum_z4_km": _km_str_with_small(z_m["4"]),
            "sum_z5_km": _km_str_with_small(z_m["5"]),
            "sum_z6_km": _km_str_with_small(z_m["6"]),
            "sum_race_km": _km_str_with_small(race_m),
            "sum_t10000_km": _km_str_with_small(t_m["10000"]),
            "sum_t5000_km": _km_str_with_small(t_m["5000"]),
            "sum_t3000_km": _km_str_with_small(t_m["3000"]),
            "sum_t1500_km": _km_str_with_small(t_m["1500"]),
            "sum_t800_km": _km_str_with_small(t_m["800"]),
            "sum_tm_km": _km_str_with_small(t_m["TM"]),
            "sum_thm_km": _km_str_with_small(t_m["THM"]),
            "sum_t4_km": _km_str_with_small(t_m["T4"]),
            "has_z1": has_z["1"],
            "has_z2": has_z["2"],
            "has_z3": has_z["3"],
            "has_z4": has_z["4"],
            "has_z5": has_z["5"],
            "has_z6": has_z["6"],
            "has_race": has_race,
            "has_t10000": has_t["10000"],
            "has_t5000": has_t["5000"],
            "has_t3000": has_t["3000"],
            "has_t1500": has_t["1500"],
            "has_t800": has_t["800"],
            "has_tm": has_t["TM"],
            "has_thm": has_t["THM"],
            "has_t4": has_t["T4"],
            "alt_z1_min": alt_z1_min,
            "alt_z2_min": alt_z2_min,
            "alt_z3_min": alt_z3_min,
            "has_alt": has_alt,
            "sum_pct_tooltip": sum_pct_tooltip,
        })

        d += timedelta(days=7)

    week_phases_enabled = bool(getattr(selected_plan, "week_phases_enabled", False)) if selected_plan else False
    settings = CoachSettings.objects.filter(user=request.user).first()
    weekcolors_enabled = bool(request.session.get("weekcolors_enabled", getattr(settings, "weekcolors_enabled", True)))
    show_all_zones = bool(request.session.get("show_all_zones", getattr(settings, "show_all_zones", True)))
    show_t_totals = bool(request.session.get("show_t_totals", getattr(settings, "show_t_totals", True)))
    show_all_t_totals = bool(request.session.get("show_all_t_totals", getattr(settings, "show_all_t_totals", True)))

    return render(
        request,
        "core/calendar.html",
        {
            "week_rows": week_rows,
            "display_mode": _calendar_display_mode(request),
            "plans": plans,
            "selected_plan": selected_plan,
            "plan_athletes": plan_athletes,
            "selected_athlete": selected_athlete,
            "zones_times_rows": _build_zones_times_rows(selected_athlete),
            "show_all_zones": show_all_zones,
            "show_t_totals": show_t_totals,
            "show_all_t_totals": show_all_t_totals,
            "has_week_clipboard": bool(request.session.get("week_clipboard")),
            "week_phases_enabled": week_phases_enabled,
            "weekcolors_enabled": weekcolors_enabled,
        },
    )




def _is_flex_planner_plan(plan) -> bool:
    name = (getattr(plan, "name", "") or "").strip()
    return bool(plan and name.startswith("Flex Planner"))


def _flex_planner_plan_name(user) -> str:
    user_id = getattr(user, "id", None) or getattr(user, "pk", None) or "unknown"
    return f"Flex Planner {user_id}"


def _get_or_create_flex_planner_plan(user, start: date, end: date):
    if not user or not getattr(user, "is_authenticated", False):
        return None

    fields = {field.name for field in TrainingPlan._meta.get_fields()}
    qs = TrainingPlan.objects.filter(name__startswith="Flex Planner")
    if "owner" in fields:
        qs = qs.filter(owner=user)

    plan = qs.order_by("id").first()
    if not plan:
        kwargs = {"name": _flex_planner_plan_name(user)}
        if "owner" in fields:
            kwargs["owner"] = user
        if "description" in fields:
            kwargs["description"] = "Automatically created fallback plan for Flex Planner cells without a regular plan."
        if "start_date" in fields:
            kwargs["start_date"] = start
        if "end_date" in fields:
            kwargs["end_date"] = end - timedelta(days=1)
        if "is_active" in fields:
            kwargs["is_active"] = True
        if "is_private" in fields:
            kwargs["is_private"] = True
        if "week_phases_enabled" in fields:
            kwargs["week_phases_enabled"] = True
        plan = TrainingPlan.objects.create(**kwargs)
    else:
        changed = []
        if "start_date" in fields and (not plan.start_date or plan.start_date > start):
            plan.start_date = start
            changed.append("start_date")
        if "end_date" in fields:
            target_end = end - timedelta(days=1)
            if not plan.end_date or plan.end_date < target_end:
                plan.end_date = target_end
                changed.append("end_date")
        if "is_active" in fields and not getattr(plan, "is_active", True):
            plan.is_active = True
            changed.append("is_active")
        if "is_private" in fields and not getattr(plan, "is_private", False):
            plan.is_private = True
            changed.append("is_private")
        if "week_phases_enabled" in fields and not getattr(plan, "week_phases_enabled", False):
            plan.week_phases_enabled = True
            changed.append("week_phases_enabled")
        if changed:
            plan.save(update_fields=changed)

    return plan


def _flex_check_payload(check):
    if not check:
        return None

    status = (getattr(check, "effective_status", None) or getattr(check, "status", "") or "").strip()
    rpe = getattr(check, "rpe", None)
    comment = (getattr(check, "comment", "") or "").strip()

    status_none = getattr(AthleteDayCheck, "STATUS_NONE", "")
    if (not status or status == status_none) and rpe is None and not comment:
        return None

    status_done = getattr(AthleteDayCheck, "STATUS_DONE_AS_PLANNED", "done_as_planned")
    status_too_hard = getattr(AthleteDayCheck, "STATUS_TOO_HARD_FAST", "too_hard_fast")
    status_adjusted = getattr(AthleteDayCheck, "STATUS_ADJUSTED_OK", "adjusted_ok")
    status_lighter = getattr(AthleteDayCheck, "STATUS_LIGHTER_SLOWER", "lighter_slower")
    status_not_done = getattr(AthleteDayCheck, "STATUS_NOT_DONE", "not_done")

    visuals = {
        status_done: {"icon": "✓", "label": "Done as planned"},
        status_too_hard: {"icon": "↑", "label": "Too hard/fast"},
        status_adjusted: {"icon": "✓", "label": "Adjusted"},
        status_lighter: {"icon": "↓", "label": "Lighter/slower"},
        status_not_done: {"icon": "✕", "label": "Not done"},
        "done": {"icon": "✓", "label": "Done as planned"},
        "done_as_planned": {"icon": "✓", "label": "Done as planned"},
        "too_hard_fast": {"icon": "↑", "label": "Too hard/fast"},
        "adjusted_ok": {"icon": "✓", "label": "Adjusted"},
        "lighter_slower": {"icon": "↓", "label": "Lighter/slower"},
        "not_done": {"icon": "✕", "label": "Not done"},
    }

    visual = visuals.get(status, {"icon": "✓", "label": status.replace("_", " ").strip().title() if status else "Report"})
    try:
        display = check.get_status_display()
        if display:
            visual = {**visual, "label": display}
    except Exception:
        pass

    return {
        "status": status,
        "icon": visual["icon"],
        "label": visual["label"],
        "rpe": rpe,
        "comment": comment,
    }


class _VirtualSegmentList:
    def __init__(self, segments):
        self._segments = segments

    def all(self):
        return self._segments


class _VirtualSegment:
    def __init__(self, text, type="CORE", zone="", special="", t_type="", reps=1, distance_m=None, duration_s=None, norm_distance_m=None):
        self.text = text or ""
        self.type = type
        self.zone = str(zone or "")
        self.special = special or ""
        self.t_type = t_type or ""
        self.reps = reps or 1
        self.distance_m = distance_m
        self.duration_s = duration_s
        self.norm_distance_m = norm_distance_m


class _VirtualSlot:
    def __init__(self, segments, plan_id=None):
        self.segments = _VirtualSegmentList(segments)
        self.plan_id = plan_id

    def core_text(self):
        return " // ".join(seg.text for seg in self.segments.all() if seg.type == "CORE" and seg.text)


def _parse_base_training_text(text):
    values = {"WU": "", "MOB": "", "SPR": "", "CORE": "", "CORE2": "", "ALT": "", "CD": ""}
    raw = (text or "").strip()
    if not raw:
        return values

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

    return values


def _virtual_segment_from_text(seg_type, text):
    parsed = _parse_core_segment_text(text) if seg_type in {"CORE", "CORE2"} else parse_segment_text(text, zone_required=False)
    if parsed and getattr(parsed, "ok", False):
        return _VirtualSegment(
            text=text,
            type=seg_type,
            zone=str(parsed.zone or ""),
            special=getattr(parsed, "special", "") or "",
            t_type=getattr(parsed, "t_type", "") or "",
            reps=getattr(parsed, "reps", 1) or 1,
            distance_m=getattr(parsed, "rep_distance_m", None) or getattr(parsed, "distance_m", None),
            duration_s=getattr(parsed, "duration_s", None),
            norm_distance_m=getattr(parsed, "distance_m", None),
        )
    return _VirtualSegment(text=text, type=seg_type)


def _virtual_slot_from_base_training(text):
    values = _parse_base_training_text(text)
    order = ("WU", "MOB", "SPR", "CORE", "CORE2", "ALT", "CD")
    segments = [
        _virtual_segment_from_text(seg_type, values[seg_type])
        for seg_type in order
        if values.get(seg_type)
    ]
    return _VirtualSlot(segments) if segments else None


def _race_entry_count(entry):
    return int(bool(entry.coach_selected)) + int(bool(entry.athlete_selected)) + int(bool(entry.target_selected))


def _race_distance_m_from_entry(entry):
    distance = entry.race_distance
    if distance.custom_distance_m:
        return distance.custom_distance_m
    match = re.search(r"\d+", distance.distance or "")
    return int(match.group(0)) if match else None


def _virtual_race_slot_from_entries(entries):
    segments = []
    for entry in entries:
        count = _race_entry_count(entry)
        if count <= 0:
            continue
        distance = entry.race_distance
        race = distance.race
        distance_m = _race_distance_m_from_entry(entry)
        special = "IMPORTANT_RACE" if count >= 3 else "RACE"
        label = "Race!" if count >= 3 else "Race"
        text = f'"{race.name}" {distance.display_distance} {label}'
        segments.append(_VirtualSegment(
            text=text,
            type="CORE",
            zone="5",
            special=special,
            distance_m=distance_m,
            norm_distance_m=distance_m,
        ))
    return _VirtualSlot(segments) if segments else None


def _month_day_index_for_flex(day):
    return date(2024, day.month, day.day).timetuple().tm_yday


def _base_block_covers_day(block, day):
    start_idx = date(2024, block.start_month, block.start_day).timetuple().tm_yday
    end_idx = date(2024, block.end_month, block.end_day).timetuple().tm_yday
    day_idx = _month_day_index_for_flex(day)
    if start_idx <= end_idx:
        return start_idx <= day_idx <= end_idx
    return day_idx >= start_idx or day_idx <= end_idx


def _base_planning_slot_for_day(base_blocks_by_athlete, athlete_id, day, slot_index):
    for block in base_blocks_by_athlete.get(athlete_id, []):
        if not _base_block_covers_day(block, day):
            continue
        for base_slot in getattr(block, "_prefetched_base_slots", []):
            if base_slot.weekday == day.weekday() and base_slot.slot_index == slot_index:
                return base_slot
    return None


def _get_athlete_year_flex_plan(user, athlete, start, end):
    if not athlete:
        return None
    if user.is_staff:
        return _get_or_create_flex_planner_plan(user, start, end)
    return (
        TrainingPlan.objects
        .filter(owner=getattr(athlete, "owner", None), name__startswith="Flex Planner")
        .order_by("id")
        .first()
    )


@login_required
def flex_planner_view(request):
    """
    Experimental multi-athlete planner.

    V1:
    - no new models
    - no migrations
    - reads existing TrainingPlan / TrainingSlot data
    - opens the existing slot modal with plan + athlete
    """
    accessible_athletes = list(_filter_accessible(Athlete.objects.order_by("name"), request.user))
    accessible_groups = list(_filter_accessible(Group.objects.prefetch_related("athletes").order_by("name"), request.user))
    accessible_plans = list(_filter_accessible(TrainingPlan.objects.order_by("name"), request.user).exclude(name__startswith="Flex Planner"))

    today = date.today()
    default_start = today - timedelta(days=today.weekday())

    start_raw = (request.GET.get("start") or "").strip()
    try:
        start = date.fromisoformat(start_raw) if start_raw else default_start
    except Exception:
        start = default_start
    start = start - timedelta(days=start.weekday())

    weeks_raw = (request.GET.get("weeks") or "2").strip()
    try:
        weeks = int(weeks_raw)
    except Exception:
        weeks = 2
    weeks = max(1, min(5, weeks))

    selected_group_value = (request.GET.get("group") or "all").strip()
    selected_group = None
    selected_group_athlete_ids = []
    if selected_group_value and selected_group_value != "all":
        try:
            selected_group = next((g for g in accessible_groups if g.id == int(selected_group_value)), None)
        except Exception:
            selected_group = None
    if selected_group:
        selected_group_athlete_ids = list(selected_group.athletes.values_list("id", flat=True))

    if selected_group:
        visible_athlete_ids = set(selected_group_athlete_ids)
        visible_athletes = [a for a in accessible_athletes if a.id in visible_athlete_ids]
    else:
        selected_group_value = "all"
        visible_athletes = accessible_athletes
        visible_athlete_ids = {a.id for a in visible_athletes}

    selected_athlete_ids_raw = request.GET.getlist("athletes")
    selected_athlete_ids = []
    for raw_id in selected_athlete_ids_raw:
        try:
            athlete_id = int(raw_id)
        except Exception:
            continue
        if athlete_id in visible_athlete_ids:
            selected_athlete_ids.append(athlete_id)

    selected_athlete_ids = selected_athlete_ids[:20]
    selected_athlete_ids_set = set(selected_athlete_ids)

    selected_athletes = [a for a in visible_athletes if a.id in selected_athlete_ids_set]

    end = start + timedelta(days=7 * weeks)
    week_starts = [start + timedelta(days=7 * i) for i in range(weeks)]
    flex_plan = _get_or_create_flex_planner_plan(request.user, start, end) if selected_athletes else None

    # Determine which plans are relevant per athlete/date.
    # Current project rule: an athlete should not be in overlapping plans for the same dates.
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
    plan_for_athlete_day = {}
    if flex_plan:
        relevant_plan_ids.add(flex_plan.id)

    for athlete in selected_athletes:
        for day_offset in range((end - start).days):
            day = start + timedelta(days=day_offset)
            matching_plan = None

            for plan in accessible_plans:
                target_ids = plan_targets.get(plan.id, set())
                if athlete.id not in target_ids:
                    continue
                if plan.start_date and plan.start_date > day:
                    continue
                if plan.end_date and plan.end_date < day:
                    continue

                matching_plan = plan
                break

            if matching_plan:
                plan_for_athlete_day[(athlete.id, day)] = matching_plan
                relevant_plan_ids.add(matching_plan.id)
            elif flex_plan:
                plan_for_athlete_day[(athlete.id, day)] = flex_plan
                relevant_plan_ids.add(flex_plan.id)

    slot_lookup = {}
    has_fix_keys = set()

    if relevant_plan_ids and selected_athlete_ids:
        slot_qs = (
            TrainingSlot.objects
            .filter(
                plan_id__in=relevant_plan_ids,
                date__gte=start,
                date__lt=end,
            )
            .filter(Q(athlete__isnull=True) | Q(athlete_id__in=selected_athlete_ids))
            .prefetch_related("segments")
            .select_related("plan", "athlete")
        )

        for slot in slot_qs:
            athlete_key = slot.athlete_id or None
            slot_lookup[(slot.plan_id, athlete_key, slot.date, slot.slot_index)] = slot
            if slot.athlete_id:
                has_fix_keys.add((slot.plan_id, slot.athlete_id, slot.date, slot.slot_index))

    check_lookup = {}
    if selected_athlete_ids:
        for check in AthleteDayCheck.objects.filter(
            athlete_id__in=selected_athlete_ids,
            date__gte=start,
            date__lt=end,
        ):
            check_lookup[(check.athlete_id, check.date, check.slot_index)] = check

    base_phase_by_plan_week = {}
    athlete_phase_by_plan_week = {}

    if relevant_plan_ids:
        for obj in PlanWeekPhase.objects.filter(plan_id__in=relevant_plan_ids, week_start__in=week_starts):
            base_phase_by_plan_week[(obj.plan_id, obj.week_start)] = (obj.phase or "")

    if relevant_plan_ids and selected_athlete_ids:
        for obj in AthleteWeekPhaseOverride.objects.filter(
            plan_id__in=relevant_plan_ids,
            athlete_id__in=selected_athlete_ids,
            week_start__in=week_starts,
        ):
            athlete_phase_by_plan_week[(obj.plan_id, obj.athlete_id, obj.week_start)] = (obj.phase or "")

    base_blocks_by_athlete = {}
    trainer_plan_ids = set()
    if selected_athlete_ids:
        base_slot_qs = AthleteBasePlanningSlot.objects.select_related("trainer_plan").order_by("weekday", "slot_index")
        base_blocks = (
            AthleteBasePlanningBlock.objects
            .filter(athlete_id__in=selected_athlete_ids)
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
            .filter(
                plan_id__in=trainer_plan_ids,
                athlete__isnull=True,
                date__gte=start,
                date__lt=end,
            )
            .prefetch_related("segments")
            .select_related("plan")
        )
        for trainer_slot in trainer_slot_qs:
            trainer_slot_lookup[(trainer_slot.plan_id, trainer_slot.date, trainer_slot.slot_index)] = trainer_slot

    race_entries_by_athlete_day = {}
    if selected_athlete_ids:
        race_entry_qs = (
            RaceEntry.objects
            .filter(
                athlete_id__in=selected_athlete_ids,
                race_distance__race__date__gte=start,
                race_distance__race__date__lt=end,
            )
            .filter(Q(coach_selected=True) | Q(athlete_selected=True) | Q(target_selected=True))
            .select_related("race_distance", "race_distance__race")
            .order_by("race_distance__race__date", "race_distance__race__name", "race_distance__id")
        )
        for entry in race_entry_qs:
            race_entries_by_athlete_day.setdefault(
                (entry.athlete_id, entry.race_distance.race.date),
                [],
            ).append(entry)

    week_rows = []
    for week_start in week_starts:
        days = [week_start + timedelta(days=i) for i in range(7)]
        athlete_rows = []

        for athlete in selected_athletes:
            am_cells = []
            pm_cells = []

            for day in days:
                plan = plan_for_athlete_day.get((athlete.id, day))

                for slot_index, target_cells in ((1, am_cells), (2, pm_cells)):
                    slot = None
                    is_override = False
                    flex_blocks_base = False
                    no_plan = bool(flex_plan and plan and plan.id == flex_plan.id)

                    if plan:
                        override_slot = slot_lookup.get((plan.id, athlete.id, day, slot_index))
                        base_slot = slot_lookup.get((plan.id, None, day, slot_index))
                        slot = override_slot or base_slot
                        is_override = override_slot is not None

                    if flex_plan:
                        flex_override_slot = slot_lookup.get((flex_plan.id, athlete.id, day, slot_index))
                        if flex_override_slot is not None:
                            if _slot_is_visually_empty(flex_override_slot):
                                if not _slot_has_race(slot):
                                    slot = None
                                    plan = flex_plan
                                    flex_blocks_base = True
                                    no_plan = False
                            else:
                                slot = flex_override_slot
                                plan = flex_plan
                                is_override = True
                                no_plan = False

                    if slot_index == 2 and not is_override:
                        race_slot = _virtual_race_slot_from_entries(race_entries_by_athlete_day.get((athlete.id, day), []))
                        if race_slot:
                            slot = race_slot
                            if flex_plan:
                                plan = flex_plan
                                no_plan = False

                    if not slot and not flex_blocks_base:
                        base_planning_slot = _base_planning_slot_for_day(base_blocks_by_athlete, athlete.id, day, slot_index)
                        if base_planning_slot:
                            if base_planning_slot.mode == AthleteBasePlanningSlot.MODE_TRAINING:
                                slot = _virtual_slot_from_base_training(base_planning_slot.training_text)
                            elif base_planning_slot.mode == AthleteBasePlanningSlot.MODE_TRAINER and base_planning_slot.trainer_plan_id:
                                slot = trainer_slot_lookup.get((base_planning_slot.trainer_plan_id, day, slot_index))
                                if _slot_is_visually_empty(slot) and base_planning_slot.trainer_plan:
                                    slot = _VirtualSlot([_VirtualSegment(text=base_planning_slot.trainer_plan.name, type="GROUP")])
                            if slot and flex_plan:
                                plan = flex_plan
                                no_plan = False

                    target_cells.append({
                        "day": day,
                        "slot_index": slot_index,
                        "plan": plan,
                        "plan_id": plan.id if plan else "",
                        "slot": None if _slot_is_visually_empty(slot) else slot,
                        "has_race": _slot_has_race(slot),
                        "is_override": is_override,
                        "no_plan": no_plan,
                        "check": _flex_check_payload(check_lookup.get((athlete.id, day, slot_index))),
                    })

            week_phase = ""
            week_phase_plan_id = ""

            for day in days:
                plan = plan_for_athlete_day.get((athlete.id, day))
                if not plan:
                    continue

                athlete_phase = athlete_phase_by_plan_week.get((plan.id, athlete.id, week_start), "")
                base_phase = base_phase_by_plan_week.get((plan.id, week_start), "")
                week_phase = athlete_phase or base_phase
                week_phase_plan_id = plan.id
                break

            athlete_rows.append({
                "athlete": athlete,
                "am_cells": am_cells,
                "pm_cells": pm_cells,
                "week_phase": week_phase,
                "week_phase_plan_id": week_phase_plan_id,
            })

        week_rows.append({
            "week_start": week_start,
            "week_end": week_start + timedelta(days=6),
            "days": days,
            "athlete_rows": athlete_rows,
        })

    prev_start = start - timedelta(days=7)
    next_start = start + timedelta(days=7)

    selected_query = "&".join(f"athletes={athlete_id}" for athlete_id in selected_athlete_ids)
    prev_url = f"?start={prev_start.isoformat()}&weeks={weeks}"
    next_url = f"?start={next_start.isoformat()}&weeks={weeks}"
    prev_url += f"&group={selected_group_value}"
    next_url += f"&group={selected_group_value}"
    if selected_query:
        prev_url += f"&{selected_query}"
        next_url += f"&{selected_query}"

    return render(
        request,
        "core/flex_planner.html",
        {
            "athletes": visible_athletes,
            "groups": accessible_groups,
            "selected_group": selected_group,
            "selected_group_value": selected_group_value,
            "selected_athletes": selected_athletes,
            "selected_athlete_ids": selected_athlete_ids_set,
            "week_rows": week_rows,
            "start": start,
            "weeks": weeks,
            "prev_url": prev_url,
            "next_url": next_url,
            "max_athletes": 20,
            "max_weeks": 5,
        },
    )


def _invalidate_stats_cache():
    try:
        cache.incr(STATS_VERSION_KEY)
    except Exception:
        cache.set(STATS_VERSION_KEY, 1, None)

def _t_type_from_text(text: str) -> str:
    match = re.search(
        r"\b(T\s*(?:800|1500|3000|5000|10000|8|15|3|5|10|4)|TM|THM)\b",
        text or "",
        re.IGNORECASE,
    )
    if not match:
        return ""

    raw = match.group(1).upper().replace(" ", "")
    mapping = {
        "T8": "800",
        "T800": "800",
        "T15": "1500",
        "T1500": "1500",
        "T3": "3000",
        "T3000": "3000",
        "T5": "5000",
        "T5000": "5000",
        "T10": "10000",
        "T10000": "10000",
        "T4": "T4",
        "TM": "TM",
        "THM": "THM",
    }
    return mapping.get(raw, "")


def _zone_from_text(text: str, default: str = "1") -> str:
    match = re.search(r"\bz\s*([1-6])\b", text or "", re.IGNORECASE)
    if match:
        return match.group(1)

    t_type = _t_type_from_text(text)
    if t_type == "TM":
        return "2"
    if t_type == "THM":
        return "3"
    if t_type in ("10000", "5000", "3000"):
        return "4"
    if t_type in ("1500", "800", "T4"):
        return "5"

    return default


def _format_time_seconds(total_seconds):
    if total_seconds is None:
        return ""

    try:
        seconds = int(round(float(total_seconds)))
    except Exception:
        return ""

    if seconds <= 0:
        return ""

    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60

    if hours:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


def _seconds_from_time_value(value):
    if value in (None, ""):
        return None

    if isinstance(value, str):
        raw = value.strip()
        if not raw:
            return None

        if ":" in raw:
            try:
                parts = [int(p) for p in raw.split(":")]
            except Exception:
                return None

            if len(parts) == 2:
                return parts[0] * 60 + parts[1]
            if len(parts) == 3:
                return parts[0] * 3600 + parts[1] * 60 + parts[2]
            return None

        raw = raw.replace(",", ".")
        try:
            return float(raw)
        except Exception:
            return None

    try:
        return float(value)
    except Exception:
        return None


def _format_pace_from_speed(speed_mps, distance_m):
    try:
        speed = float(speed_mps or 0)
    except Exception:
        return ""

    if speed <= 0:
        return ""

    return _format_time_seconds(float(distance_m) / speed)


def _format_pace_from_seconds_per_km(seconds_per_km, distance_m):
    try:
        seconds = float(seconds_per_km or 0) * (float(distance_m) / 1000.0)
    except Exception:
        return ""

    if seconds <= 0:
        return ""

    return _format_time_seconds(seconds)


def _first_athlete_attr(athlete, names):
    for name in names:
        if hasattr(athlete, name):
            value = getattr(athlete, name, None)
            if value not in (None, ""):
                return name, value
    return None, None


def _athlete_t_pr_seconds(athlete, key):
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
    _, value = _first_athlete_attr(athlete, attr_names.get(key, []))
    return _seconds_from_time_value(value)


def _pace_seconds_per_km_from_value(value):
    if value in (None, ""):
        return None

    if isinstance(value, str):
        raw = value.strip()
        if not raw:
            return None

        if ":" in raw:
            seconds = _seconds_from_time_value(raw)
            return seconds if seconds and seconds > 0 else None

        raw = raw.replace(",", ".")
        try:
            numeric = float(raw)
        except Exception:
            return None

        if numeric <= 0:
            return None

        if numeric < 20:
            return numeric * 60.0

        return numeric

    try:
        numeric = float(value)
    except Exception:
        return None

    if numeric <= 0:
        return None

    if numeric < 20:
        return numeric * 60.0

    return numeric


def _zone_speed_mps(athlete, label):
    z = label.lower()
    zone_num = z.replace("z", "")

    try:
        speeds = athlete.get_zone_speed_mps()
    except Exception:
        speeds = getattr(athlete, "zone_speed_mps", {}) or {}

    if isinstance(speeds, dict):
        speed_value = speeds.get(zone_num) or speeds.get(str(zone_num))
        try:
            speed = float(speed_value or 0)
        except Exception:
            speed = 0
        if speed > 0:
            return speed

    pace_attr_names = [
        f"zone_pace_{z}",
        f"pace_{z}",
        f"{z}_pace",
        f"zone_{z}_pace",
        f"zone_{z}",
        f"{z}",
        f"zone_{z}_min_per_km",
        f"{z}_min_per_km",
        f"zone_{z}_pace_min_km",
        f"{z}_pace_min_km",
        f"zone_time_{z}",
        f"time_{z}",
        f"{z}_time",
    ]
    _, pace_value = _first_athlete_attr(athlete, pace_attr_names)
    pace_seconds = _pace_seconds_per_km_from_value(pace_value)
    if pace_seconds and pace_seconds > 0:
        return 1000.0 / pace_seconds

    speed_attr_names = [
        f"zone_speed_{z}",
        f"speed_{z}",
    ]
    _, speed_value = _first_athlete_attr(athlete, speed_attr_names)

    try:
        speed = float(speed_value or 0)
    except Exception:
        return None

    if speed <= 0:
        return None

    return speed


def _build_zones_times_rows(athlete):
    labels = ["Z1", "Z2", "Z3", "Z4", "Z5", "TM", "THM", "T10", "T5", "T3", "T15", "T8", "T4"]
    t_distances = {
        "TM": 42195,
        "THM": 21097.5,
        "T10": 10000,
        "T5": 5000,
        "T3": 3000,
        "T15": 1500,
        "T8": 800,
        "T4": 400,
    }

    rows = []
    if not athlete:
        for label in labels:
            rows.append({"pr": "-" if label.startswith("Z") else "", "label": label, "per_km": "", "per_400m": "", "per_100m": ""})
        return rows

    for label in labels:
        pr_display = "-" if label.startswith("Z") else ""
        per_km = ""
        per_400m = ""
        per_100m = ""

        if label.startswith("Z"):
            speed = _zone_speed_mps(athlete, label)
            per_km = _format_pace_from_speed(speed, 1000)
            per_400m = _format_pace_from_speed(speed, 400)
            per_100m = _format_pace_from_speed(speed, 100)
        else:
            pr_seconds = _athlete_t_pr_seconds(athlete, label)
            distance = t_distances.get(label)
            if pr_seconds and distance:
                seconds_per_km = float(pr_seconds) / (float(distance) / 1000.0)
                pr_display = _format_time_seconds(pr_seconds)
                per_km = _format_pace_from_seconds_per_km(seconds_per_km, 1000)
                per_400m = _format_pace_from_seconds_per_km(seconds_per_km, 400)
                per_100m = _format_pace_from_seconds_per_km(seconds_per_km, 100)

        rows.append({
            "pr": pr_display,
            "label": label,
            "per_km": per_km,
            "per_400m": per_400m,
            "per_100m": per_100m,
        })

    return rows


def _save_athlete_slot_override(request, athlete, d, slot_index, slot_text):
    if request.user.is_staff:
        owned_plans = list(_filter_owned(TrainingPlan.objects.order_by("name"), request.user))
    else:
        owned_plans = list(TrainingPlan.objects.order_by("name"))

    base_slot = None
    existing_override = None
    selected_plan = None
    requested_plan_id = (request.POST.get("plan") or request.GET.get("plan") or "").strip()

    if requested_plan_id.isdigit():
        for plan in owned_plans:
            if plan.id != int(requested_plan_id):
                continue
            try:
                if athlete.id not in plan.targeted_athlete_ids() and not _is_flex_planner_plan(plan):
                    continue
            except Exception:
                if not _is_flex_planner_plan(plan):
                    continue
            if plan.start_date and plan.start_date > d:
                continue
            if plan.end_date and plan.end_date < d:
                continue
            selected_plan = plan
            break

    if not selected_plan:
        for plan in owned_plans:
            if athlete.id not in plan.targeted_athlete_ids():
                continue

            existing_override = TrainingSlot.objects.filter(
                plan=plan,
                date=d,
                slot_index=slot_index,
                athlete=athlete,
            ).first()

            base_slot = TrainingSlot.objects.filter(
                plan=plan,
                date=d,
                slot_index=slot_index,
                athlete__isnull=True,
            ).first()

            if existing_override or base_slot:
                selected_plan = plan
                break

    source_slot = existing_override or base_slot
    if not source_slot and not selected_plan:
        return

    override_slot, _ = TrainingSlot.objects.update_or_create(
        plan=source_slot.plan if source_slot else selected_plan,
        date=d,
        slot_index=slot_index,
        athlete=athlete,
        defaults={},
    )

    override_slot.segments.all().delete()

    fields = [
        ("WU", request.POST.get("wu_text", ""), "1"),
        ("MOB", request.POST.get("mob_text", ""), "1"),
        ("SPR", request.POST.get("sprint_text", ""), "6"),
        ("CORE", request.POST.get("core_text", ""), "1"),
        ("CORE2", request.POST.get("core2_text", ""), "1"),
        ("ALT", request.POST.get("alt_text", ""), "1"),
        ("CD", request.POST.get("cd_text", ""), "1"),
    ]

    has_field_text = any((value or "").strip() for _, value, _ in fields)

    if not has_field_text and (slot_text or "").strip():
        fields = [("CORE", slot_text, "1")]
    elif has_field_text:
        core_text = (request.POST.get("core_text") or "").strip()
        wu_text = request.POST.get("wu_text") or ""
        cd_text = request.POST.get("cd_text") or ""
        if core_text:
            wu_text, cd_text = apply_auto_wucd_texts(athlete, source_slot.plan if source_slot else selected_plan, core_text, wu_text.strip(), cd_text.strip())
            fields = [
                ("WU", wu_text, "1"),
                ("MOB", request.POST.get("mob_text", ""), "1"),
                ("SPR", request.POST.get("sprint_text", ""), "6"),
                ("CORE", core_text, "1"),
                ("CORE2", request.POST.get("core2_text", ""), "1"),
                ("ALT", request.POST.get("alt_text", ""), "1"),
                ("CD", cd_text, "1"),
            ]

    now = timezone.now()
    order = 1

    for segment_type, value, default_zone in fields:
        raw_text = (value or "").strip()
        if not raw_text:
            continue

        if segment_type == "CORE":
            parts = []
            for core_part in [p.strip() for p in raw_text.split("//") if p.strip()]:
                parts.extend(_expand_repeated_core_set_parts(core_part))

            for part in parts:
                zone_range_parts = _core_zone_range_parts(part)
                t_range_parts = None if zone_range_parts else _core_t_range_parts(part)
                range_parts = zone_range_parts or t_range_parts

                if range_parts:
                    source_parse = range_parts["source_parse"]
                    seg = TrainingSegment.objects.create(
                        slot=override_slot,
                        order=order,
                        type="CORE",
                        text=range_parts["source_text"],
                    )
                    seg.parse_ok = True
                    seg.parse_message = source_parse.message
                    if hasattr(seg, "t_type"):
                        seg.t_type = source_parse.t_type or ""
                    seg.zone = str(source_parse.zone or "")
                    seg.reps = int(source_parse.reps or 1)
                    seg.distance_m = source_parse.rep_distance_m if source_parse.rep_distance_m is not None else source_parse.distance_m
                    seg.duration_s = source_parse.duration_s
                    seg.norm_distance_m = _compute_norm_distance_m(seg)
                    seg.parsed_at = now
                    seg.save()
                    order += 1
                    continue

                seg = TrainingSegment.objects.create(
                    slot=override_slot,
                    order=order,
                    type="CORE",
                    text=part,
                )
                parsed = _parse_core_segment_text(part)
                if parsed and parsed.ok:
                    _apply_parse_to_segment(seg, parsed)
                    seg.parsed_at = now
                    seg.save()
                else:
                    seg.zone = _zone_from_text(part, default_zone)
                    seg.t_type = _t_type_from_text(part)
                    seg.parse_ok = False
                    seg.parsed_at = now
                    seg.save()
                order += 1

            continue

        parse_text = raw_text
        if segment_type == "SPR":
            parse_text = f"{raw_text} Z6" if not re.search(r"\bz\s*[1-6]\b", raw_text, re.IGNORECASE) else raw_text

        if segment_type == "ALT":
            parsed = parse_segment_text(parse_text, zone_required=False)
        else:
            parsed = parse_segment_text(parse_text)

        seg = TrainingSegment.objects.create(
            slot=override_slot,
            order=order,
            type=segment_type,
            text=raw_text,
        )

        if parsed and parsed.ok:
            _apply_parse_to_segment(seg, parsed)
            if segment_type == "SPR":
                seg.zone = "6"
                seg.norm_distance_m = _compute_norm_distance_m(seg)
            seg.parsed_at = now
            seg.save()
        else:
            seg.zone = _zone_from_text(raw_text, default_zone)
            seg.t_type = _t_type_from_text(raw_text)
            seg.parse_ok = False
            seg.parsed_at = now
            seg.save()

        order += 1


@login_required
def athlete_year_calendar_view(request):
    if request.method == "POST":
        date_str = request.POST.get("date")
        text = request.POST.get("comment", "")
        check_status = request.POST.get("check_status")
        toggle_check = request.POST.get("toggle_check")
        report_submit = request.POST.get("report_submit")
        week_report_submit = request.POST.get("week_report_submit")
        daily_vitals_submit = request.POST.get("daily_vitals_submit")
        week_start_raw = request.POST.get("week_start")
        slot_index_raw = request.POST.get("slot_index")
        athlete = None

        if request.user.is_staff:
            athlete_id = request.POST.get("athlete") or request.GET.get("athlete")
            if athlete_id:
                try:
                    athlete = _filter_owned(Athlete.objects.all(), request.user).get(id=int(athlete_id))
                except Exception:
                    athlete = None
        else:
            athlete = _athlete_for_user(request.user)

        if athlete and date_str:
            try:
                d = date.fromisoformat(date_str)
                today = date.today()

                slot_text = request.POST.get("slot_text")

                if slot_text is not None:
                    if d > today:
                        return HttpResponse("", status=204)

                    try:
                        slot_index = int(slot_index_raw)
                    except Exception:
                        slot_index = 1

                    _save_athlete_slot_override(request, athlete, d, slot_index, slot_text)
                    _invalidate_stats_cache()

                elif week_report_submit is not None:
                    try:
                        week_start = date.fromisoformat(week_start_raw or "")
                    except Exception:
                        week_start = d - timedelta(days=d.weekday())

                    field = (request.POST.get("field") or "").strip()
                    value = request.POST.get("value") or ""
                    is_coach_user = bool(request.user.is_staff or request.user.is_superuser)
                    allowed_fields = {"match_report", "injuries"}
                    if is_coach_user:
                        allowed_fields.add("comm_trainer")
                    else:
                        allowed_fields.add("comm_athlete")

                    if field in allowed_fields:
                        report, _ = AthleteWeekReport.objects.get_or_create(
                            athlete=athlete,
                            week_start=week_start,
                            defaults={"updated_by": request.user},
                        )
                        setattr(report, field, value)
                        report.updated_by = request.user
                        report.save()

                elif daily_vitals_submit is not None:
                    if d > today:
                        return HttpResponse("", status=204)

                    field = (request.POST.get("field") or "").strip()
                    raw_value = (request.POST.get("value") or "").strip()
                    allowed_fields = {"sleep_hours", "sleep_quality", "morning_hr", "hrv"}

                    if field in allowed_fields:
                        vital, _ = AthleteDailyVital.objects.get_or_create(
                            athlete=athlete,
                            date=d,
                            defaults={"updated_by": request.user},
                        )

                        if raw_value == "":
                            value = None
                        elif field == "sleep_hours":
                            try:
                                value = round(float(raw_value.replace(",", ".")), 2)
                            except Exception:
                                value = None
                        else:
                            try:
                                value = int(raw_value)
                            except Exception:
                                value = None

                        if field == "sleep_quality" and value is not None:
                            if value < 1 or value > 10:
                                value = None

                        setattr(vital, field, value)
                        vital.updated_by = request.user
                        vital.save()

                elif check_status is not None or toggle_check is not None or report_submit is not None:
                    if d > today:
                        return HttpResponse("", status=204)
                    try:
                        slot_index = int(slot_index_raw)
                    except Exception:
                        slot_index = 1

                    allowed_statuses = {
                        AthleteDayCheck.STATUS_NONE,
                        AthleteDayCheck.STATUS_DONE_AS_PLANNED,
                        AthleteDayCheck.STATUS_TOO_HARD_FAST,
                        AthleteDayCheck.STATUS_ADJUSTED_OK,
                        AthleteDayCheck.STATUS_LIGHTER_SLOWER,
                        AthleteDayCheck.STATUS_NOT_DONE,
                    }

                    status = (check_status or "").strip()

                    if toggle_check is not None and check_status is None:
                        existing = AthleteDayCheck.objects.filter(
                            date=d,
                            athlete=athlete,
                            slot_index=slot_index,
                        ).first()
                        current_status = existing.effective_status if existing else AthleteDayCheck.STATUS_NONE
                        status = (
                            AthleteDayCheck.STATUS_NONE
                            if current_status == AthleteDayCheck.STATUS_DONE_AS_PLANNED
                            else AthleteDayCheck.STATUS_DONE_AS_PLANNED
                        )

                    if status not in allowed_statuses:
                        status = AthleteDayCheck.STATUS_NONE

                    obj, _ = AthleteDayCheck.objects.get_or_create(
                        date=d,
                        athlete=athlete,
                        slot_index=slot_index,
                        defaults={"updated_by": request.user},
                    )
                    obj.status = status
                    obj.checked = bool(status)

                    if report_submit is not None:
                        rpe_raw = (request.POST.get("rpe") or "").strip()
                        comment_raw = (request.POST.get("report_comment") or "").strip()
                        obj.rpe = int(rpe_raw) if rpe_raw.isdigit() and 0 <= int(rpe_raw) <= 10 else None
                        obj.comment = comment_raw

                    obj.updated_by = request.user
                    obj.save()
                    _invalidate_stats_cache()

                else:
                    AthleteDayComment.objects.update_or_create(
                        date=d,
                        athlete=athlete,
                        defaults={"text": text, "created_by": request.user},
                    )

            except Exception:
                pass

        response = HttpResponse("", status=200)
        response["HX-Refresh"] = "true"
        return response

    year = request.GET.get("year")
    try:
        year = int(year) if year else date.today().year
    except Exception:
        year = date.today().year

    selected_athlete_id = request.GET.get("athlete", "")
    selected_athlete = None

    if request.user.is_staff:
        athletes = list(_filter_accessible(Athlete.objects.order_by("name"), request.user))
        if selected_athlete_id:
            try:
                selected_athlete = _filter_accessible(Athlete.objects.all(), request.user).get(id=int(selected_athlete_id))
            except Exception:
                selected_athlete = None
                selected_athlete_id = ""
        elif athletes:
            selected_athlete = athletes[0]
            selected_athlete_id = str(selected_athlete.id)
    else:
        selected_athlete = _athlete_for_user(request.user)

        if selected_athlete:
            athletes = [selected_athlete]
            selected_athlete_id = str(selected_athlete.id)
        else:
            athletes = []
            selected_athlete_id = ""

    athlete_self_view = bool(selected_athlete and not request.user.is_staff)
    show_training_reports = bool(selected_athlete and getattr(selected_athlete, "training_reports_enabled", True))
    show_week_reports = bool(selected_athlete and getattr(selected_athlete, "week_report_enabled", False))
    show_daily_vitals = bool(selected_athlete and getattr(selected_athlete, "daily_vitals_enabled", False))
    ayc_rowspan = 2 + (1 if show_training_reports else 0) + (1 if show_daily_vitals else 0)
    is_coach_user = bool(request.user.is_staff or request.user.is_superuser)
    visible_until_date = None
    if athlete_self_view:
        try:
            weeks_ahead = int(getattr(selected_athlete, "view_weeks_ahead", 2) or 0)
        except Exception:
            weeks_ahead = 2
        if weeks_ahead < 0:
            weeks_ahead = 0

        today = date.today()
        if weeks_ahead == 0:
            visible_until_date = today
        else:
            current_week_start = today - timedelta(days=today.weekday())
            visible_until_date = current_week_start + timedelta(days=(7 * weeks_ahead) - 1)

    jan1 = date(year, 1, 1)
    start = jan1 - timedelta(days=jan1.weekday())

    dec31 = date(year, 12, 31)
    end = dec31 + timedelta(days=(6 - dec31.weekday()))

    weeks = ((end - start).days // 7) + 1

    slot_map = {}
    has_fix_keys = set()
    flex_plan = None
    flex_override_map = {}
    base_blocks_by_athlete = {}
    trainer_slot_lookup = {}

    if selected_athlete:
        if request.user.is_staff:
            owned_plans = list(_filter_accessible(TrainingPlan.objects.order_by("name"), request.user))
        else:
            owned_plans = list(TrainingPlan.objects.order_by("name"))

        flex_plan = _get_athlete_year_flex_plan(request.user, selected_athlete, start, end)
        if flex_plan and flex_plan not in owned_plans:
            owned_plans.append(flex_plan)

        athlete_plans = []
        override_plan_ids = set(
            TrainingSlot.objects
            .filter(athlete=selected_athlete, date__gte=start, date__lte=end)
            .values_list("plan_id", flat=True)
        )

        for plan in owned_plans:
            try:
                plan_targets_athlete = selected_athlete.id in plan.targeted_athlete_ids()
            except Exception:
                plan_targets_athlete = False
            if _is_flex_planner_plan(plan):
                plan_targets_athlete = True

            if not plan_targets_athlete and plan.id not in override_plan_ids:
                continue

            if plan.start_date and plan.start_date > end:
                continue

            if plan.end_date and plan.end_date < start:
                continue

            athlete_plans.append(plan)

        if athlete_plans:
            slot_q = (
                TrainingSlot.objects
                .filter(
                    plan__in=athlete_plans,
                    date__gte=start,
                    date__lte=end,
                )
                .filter(Q(athlete__isnull=True) | Q(athlete=selected_athlete))
                .prefetch_related("segments")
                .select_related("plan", "athlete")
            )

            slot_map, has_fix_keys = _build_effective_slot_maps(slot_q)

        if flex_plan:
            flex_override_qs = (
                TrainingSlot.objects
                .filter(
                    plan=flex_plan,
                    athlete=selected_athlete,
                    date__gte=start,
                    date__lte=end,
                )
                .prefetch_related("segments")
                .select_related("plan", "athlete")
            )
            for flex_override in flex_override_qs:
                flex_override_map[(flex_override.date, flex_override.slot_index)] = flex_override

        base_slot_qs = AthleteBasePlanningSlot.objects.select_related("trainer_plan").order_by("weekday", "slot_index")
        base_blocks = (
            AthleteBasePlanningBlock.objects
            .filter(athlete=selected_athlete)
            .prefetch_related(Prefetch("slots", queryset=base_slot_qs, to_attr="_prefetched_base_slots"))
            .order_by("sort_order", "start_month", "start_day", "id")
        )
        trainer_plan_ids = set()
        for block in base_blocks:
            base_blocks_by_athlete.setdefault(block.athlete_id, []).append(block)
            for base_slot in getattr(block, "_prefetched_base_slots", []):
                if base_slot.mode == AthleteBasePlanningSlot.MODE_TRAINER and base_slot.trainer_plan_id:
                    trainer_plan_ids.add(base_slot.trainer_plan_id)

        if trainer_plan_ids:
            trainer_slot_qs = (
                TrainingSlot.objects
                .filter(
                    plan_id__in=trainer_plan_ids,
                    athlete__isnull=True,
                    date__gte=start,
                    date__lte=end,
                )
                .prefetch_related("segments")
                .select_related("plan")
            )
            for trainer_slot in trainer_slot_qs:
                trainer_slot_lookup[(trainer_slot.plan_id, trainer_slot.date, trainer_slot.slot_index)] = trainer_slot

    phase_label = {
        "": "",
        "recovery": "Recovery",
        "aerobe": "Aerobe",
        "specific": "Specific",
        "intense": "Intense",
        "taper": "Taper",
    }

    week_starts = [start + timedelta(days=7 * i) for i in range(weeks)]
    base_phase_by_plan_week = {}
    athlete_phase_by_plan_week = {}

    if selected_athlete and athlete_plans:
        for obj in PlanWeekPhase.objects.filter(plan__in=athlete_plans, week_start__in=week_starts):
            base_phase_by_plan_week[(obj.plan_id, obj.week_start)] = (obj.phase or "")

        for obj in AthleteWeekPhaseOverride.objects.filter(
            plan__in=athlete_plans,
            athlete=selected_athlete,
            week_start__in=week_starts,
        ):
            athlete_phase_by_plan_week[(obj.plan_id, obj.week_start)] = (obj.phase or "")

    # BULK FETCH checks & comments (performance)
    check_map = {}
    comment_map = {}
    if selected_athlete:
        checks = AthleteDayCheck.objects.filter(
            athlete=selected_athlete,
            date__gte=start,
            date__lte=end,
        )
        for c in checks:
            check_map[(c.date, c.slot_index)] = c

        comments = AthleteDayComment.objects.filter(
            athlete=selected_athlete,
            date__gte=start,
            date__lte=end,
        )
        for c in comments:
            comment_map[c.date] = c

    week_report_map = {}
    if selected_athlete:
        reports = AthleteWeekReport.objects.filter(
            athlete=selected_athlete,
            week_start__in=week_starts,
        )
        for r in reports:
            week_report_map[r.week_start] = r

    daily_vitals_map = {}
    if selected_athlete:
        vitals = AthleteDailyVital.objects.filter(
            athlete=selected_athlete,
            date__gte=start,
            date__lte=end,
        )
        for v in vitals:
            daily_vitals_map[v.date] = v

    week_rows = []
    d = start

    for _ in range(weeks):
        week_start = d
        week_end = d + timedelta(days=6)

        days = [week_start + timedelta(days=i) for i in range(7)]

        cells1 = []
        cells2 = []
        cells3 = []
        cells4 = []

        for day in days:
            k1 = (day, 1)
            k2 = (day, 2)

            check1 = None
            check2 = None
            if selected_athlete and day <= date.today():
                check1 = check_map.get((day, 1))
                check2 = check_map.get((day, 2))

            slot1 = _visible_year_slot(slot_map, has_fix_keys, k1)
            slot2 = _visible_year_slot(slot_map, has_fix_keys, k2)
            day_plan = _athlete_plan_for_day(athlete_plans, day) if selected_athlete else None
            plan1 = slot1.plan if slot1 else day_plan
            plan2 = slot2.plan if slot2 else day_plan
            flex_blocks_slot1 = False
            flex_blocks_slot2 = False

            flex_override1 = flex_override_map.get(k1)
            if flex_override1 is not None:
                plan1 = flex_plan
                if _slot_is_visually_empty(flex_override1):
                    if not _slot_has_race(slot1):
                        slot1 = None
                        flex_blocks_slot1 = True
                else:
                    slot1 = flex_override1

            flex_override2 = flex_override_map.get(k2)
            if flex_override2 is not None:
                plan2 = flex_plan
                if _slot_is_visually_empty(flex_override2):
                    if not _slot_has_race(slot2):
                        slot2 = None
                        flex_blocks_slot2 = True
                else:
                    slot2 = flex_override2

            if selected_athlete and not slot1 and not flex_blocks_slot1:
                base_planning_slot = _base_planning_slot_for_day(base_blocks_by_athlete, selected_athlete.id, day, 1)
                if base_planning_slot:
                    if base_planning_slot.mode == AthleteBasePlanningSlot.MODE_TRAINING:
                        slot1 = _virtual_slot_from_base_training(base_planning_slot.training_text)
                    elif base_planning_slot.mode == AthleteBasePlanningSlot.MODE_TRAINER and base_planning_slot.trainer_plan_id:
                        slot1 = trainer_slot_lookup.get((base_planning_slot.trainer_plan_id, day, 1))
                        if _slot_is_visually_empty(slot1) and base_planning_slot.trainer_plan:
                            slot1 = _VirtualSlot([_VirtualSegment(text=base_planning_slot.trainer_plan.name, type="GROUP")])
                    if slot1 and flex_plan:
                        plan1 = flex_plan
                        try:
                            slot1.plan_id = flex_plan.id
                        except Exception:
                            pass

            if selected_athlete and not slot2 and not flex_blocks_slot2:
                base_planning_slot = _base_planning_slot_for_day(base_blocks_by_athlete, selected_athlete.id, day, 2)
                if base_planning_slot:
                    if base_planning_slot.mode == AthleteBasePlanningSlot.MODE_TRAINING:
                        slot2 = _virtual_slot_from_base_training(base_planning_slot.training_text)
                    elif base_planning_slot.mode == AthleteBasePlanningSlot.MODE_TRAINER and base_planning_slot.trainer_plan_id:
                        slot2 = trainer_slot_lookup.get((base_planning_slot.trainer_plan_id, day, 2))
                        if _slot_is_visually_empty(slot2) and base_planning_slot.trainer_plan:
                            slot2 = _VirtualSlot([_VirtualSegment(text=base_planning_slot.trainer_plan.name, type="GROUP")])
                    if slot2 and flex_plan:
                        plan2 = flex_plan
                        try:
                            slot2.plan_id = flex_plan.id
                        except Exception:
                            pass

            if athlete_self_view and visible_until_date and day > visible_until_date:
                if not _slot_has_race(slot1):
                    slot1 = None
                    check1 = None
                if not _slot_has_race(slot2):
                    slot2 = None
                    check2 = None

            cells1.append({
                "day": day,
                "slot": slot1,
                "is_override": k1 in has_fix_keys,
                "check": check1,
                "slot_index": 1,
                "plan_id": slot1.plan_id if slot1 and getattr(slot1, "plan_id", None) else (plan1.id if plan1 else ""),
            })
            cells2.append({
                "day": day,
                "slot": slot2,
                "is_override": k2 in has_fix_keys,
                "check": check2,
                "slot_index": 2,
                "plan_id": slot2.plan_id if slot2 and getattr(slot2, "plan_id", None) else (plan2.id if plan2 else ""),
            })
            comment = None
            if selected_athlete:
                comment = comment_map.get(day)

            cells3.append({
                "day": day,
                "comment": comment,
                "check1": check1,
                "check2": check2,
                "has_slot1": bool(slot1),
                "has_slot2": bool(slot2),
            })
            cells4.append({
                "day": day,
                "vitals": daily_vitals_map.get(day),
            })

        week_phase = ""
        if selected_athlete and athlete_plans:
            for plan in athlete_plans:
                if plan.start_date and plan.start_date > week_end:
                    continue
                if plan.end_date and plan.end_date < week_start:
                    continue

                athlete_phase = ""
                base_phase = ""

                for (pid, ws), phase in athlete_phase_by_plan_week.items():
                    if pid == plan.id and week_start <= ws <= week_end:
                        athlete_phase = phase
                        break

                for (pid, ws), phase in base_phase_by_plan_week.items():
                    if pid == plan.id and week_start <= ws <= week_end:
                        base_phase = phase
                        break

                week_phase = athlete_phase or base_phase
                if week_phase:
                    break

        z_m = {str(i): 0.0 for i in range(1, 7)}
        z_time_s = {str(i): 0.0 for i in range(1, 7)}
        race_m = 0.0
        race_time_s = 0.0
        t_m = {
            "10000": 0.0,
            "5000": 0.0,
            "3000": 0.0,
            "1500": 0.0,
            "800": 0.0,
            "TM": 0.0,
            "THM": 0.0,
            "T4": 0.0,
        }

        alt_z1_min = 0
        alt_z2_min = 0
        alt_z3_min = 0

        if selected_athlete and athlete_plans:
            for plan in athlete_plans:
                if plan.start_date and plan.start_date > week_end:
                    continue
                if plan.end_date and plan.end_date < week_start:
                    continue

                st = athlete_week_stats(plan, selected_athlete, week_start)

                zones = st.get("zones") or {}
                race = st.get("race") or {"distance_m": 0, "duration_s": 0}
                t_totals = st.get("t_totals") or {}
                alt = st.get("alt_zones") or {}

                alt_z1_min += int(round(float(alt.get("1", {}).get("duration_s", 0) or 0) / 60.0))
                alt_z2_min += int(round(float(alt.get("2", {}).get("duration_s", 0) or 0) / 60.0))
                alt_z3_min += int(round(float(alt.get("3", {}).get("duration_s", 0) or 0) / 60.0))

                for z in ("1", "2", "3", "4", "5", "6"):
                    vals = zones.get(z) or {"distance_m": 0, "duration_s": 0}
                    z_m[z] += float(vals.get("distance_m") or 0)
                    z_time_s[z] += float(vals.get("duration_s") or 0)

                race_m += float(race.get("distance_m") or 0)
                race_time_s += float(race.get("duration_s") or 0)

                for t in ("10000", "5000", "3000", "1500", "800", "TM", "THM", "T4"):
                    vals = t_totals.get(t) or {"distance_m": 0, "duration_s": 0}
                    t_m[t] += float(vals.get("distance_m") or 0)

        tot_m = sum(z_m.values()) + race_m
        total_time_s = sum(z_time_s.values()) + race_time_s

        def _fmt_min(t_s: float) -> str:
            return f"{int(round(float(t_s) / 60.0))}'"

        sum_pct_tooltip = (
            f"Z1: {_fmt_min(z_time_s['1'])}/{_pct(z_time_s['1'], total_time_s)}\n"
            f"Z2: {_fmt_min(z_time_s['2'])}/{_pct(z_time_s['2'], total_time_s)}\n"
            f"Z3: {_fmt_min(z_time_s['3'])}/{_pct(z_time_s['3'], total_time_s)}\n"
            f"Z4: {_fmt_min(z_time_s['4'])}/{_pct(z_time_s['4'], total_time_s)}\n"
            f"Z5: {_fmt_min(z_time_s['5'])}/{_pct(z_time_s['5'], total_time_s)}\n"
            f"Z6: {_fmt_min(z_time_s['6'])}/{_pct(z_time_s['6'], total_time_s)}\n"
            f"Race: {_fmt_min(race_time_s)}/{_pct(race_time_s, total_time_s)}"
        )

        has_z = {z: (z_m[z] > 0) for z in ("1", "2", "3", "4", "5", "6")}
        has_race = (race_m > 0)
        has_t = {t: (t_m[t] > 0) for t in ("10000", "5000", "3000", "1500", "800", "TM", "THM", "T4")}
        has_alt = (alt_z1_min > 0 or alt_z2_min > 0 or alt_z3_min > 0)

        def _vitals_week_avg(field_name, decimals=0):
            values = []
            for cell in cells4:
                vital = cell.get("vitals")
                if not vital:
                    continue
                value = getattr(vital, field_name, None)
                if value is None:
                    continue
                try:
                    values.append(float(value))
                except (TypeError, ValueError):
                    continue

            if len(values) < 3:
                return "NA"

            avg = sum(values) / len(values)
            if decimals == 2:
                return f"{avg:.1f}"
            return f"{avg:.1f}"

        daily_vitals_avg = {
            "sleep_hours": _vitals_week_avg("sleep_hours", decimals=2),
            "sleep_quality": _vitals_week_avg("sleep_quality"),
            "morning_hr": _vitals_week_avg("morning_hr"),
            "hrv": _vitals_week_avg("hrv"),
        }

        week_rows.append({
            "week_start": week_start,
            "week_end": week_end,
            "week_report": week_report_map.get(week_start),
            "cells1": cells1,
            "cells2": cells2,
            "cells3": cells3,
            "cells4": cells4,
            "daily_vitals_avg": daily_vitals_avg,
            "week_phase": week_phase,
            "week_phase_label": phase_label.get(week_phase, ""),
            "sum_tot_km": _format_km(tot_m),
            "sum_z1_km": _km_str_with_small(z_m["1"]),
            "sum_z2_km": _km_str_with_small(z_m["2"]),
            "sum_z3_km": _km_str_with_small(z_m["3"]),
            "sum_z4_km": _km_str_with_small(z_m["4"]),
            "sum_z5_km": _km_str_with_small(z_m["5"]),
            "sum_z6_km": _km_str_with_small(z_m["6"]),
            "sum_race_km": _km_str_with_small(race_m),
            "sum_t10000_km": _km_str_with_small(t_m["10000"]),
            "sum_t5000_km": _km_str_with_small(t_m["5000"]),
            "sum_t3000_km": _km_str_with_small(t_m["3000"]),
            "sum_t1500_km": _km_str_with_small(t_m["1500"]),
            "sum_t800_km": _km_str_with_small(t_m["800"]),
            "sum_tm_km": _km_str_with_small(t_m["TM"]),
            "sum_thm_km": _km_str_with_small(t_m["THM"]),
            "sum_t4_km": _km_str_with_small(t_m["T4"]),
            "has_z1": has_z["1"],
            "has_z2": has_z["2"],
            "has_z3": has_z["3"],
            "has_z4": has_z["4"],
            "has_z5": has_z["5"],
            "has_z6": has_z["6"],
            "has_race": has_race,
            "has_t10000": has_t["10000"],
            "has_t5000": has_t["5000"],
            "has_t3000": has_t["3000"],
            "has_t1500": has_t["1500"],
            "has_t800": has_t["800"],
            "has_tm": has_t["TM"],
            "has_thm": has_t["THM"],
            "has_t4": has_t["T4"],
            "alt_z1_min": alt_z1_min,
            "alt_z2_min": alt_z2_min,
            "alt_z3_min": alt_z3_min,
            "has_alt": has_alt,
            "sum_pct_tooltip": sum_pct_tooltip,
        })

        d += timedelta(days=7)

    # --- hiding logic ---
    hide_mode = request.GET.get("hide", "t1")

    today = date.today()
    current_week_start = today - timedelta(days=today.weekday())

    if hide_mode == "t1":
        cutoff = current_week_start - timedelta(days=7)
    elif hide_mode == "t4":
        cutoff = current_week_start - timedelta(days=28)
    else:
        cutoff = None

    if cutoff:
        week_rows = [w for w in week_rows if w["week_end"] >= cutoff]

    if athlete_self_view and visible_until_date:
        week_rows = [
            w for w in week_rows
            if w["week_start"] <= visible_until_date or w.get("has_race")
        ]

    return render(
        request,
        "core/athlete_year_calendar.html",
        {
            "year": year,
            "week_rows": week_rows,
            "today": date.today(),
            "hide_mode": hide_mode,
            "athletes": athletes,
            "selected_athlete_id": str(selected_athlete_id or ""),
            "selected_athlete": selected_athlete,
            "show_training_reports": show_training_reports,
            "show_week_reports": show_week_reports,
            "show_daily_vitals": show_daily_vitals,
            "ayc_rowspan": ayc_rowspan,
            "is_coach_user": is_coach_user,
            "zones_times_rows": _build_zones_times_rows(selected_athlete),
        },
    )
