from datetime import date, timedelta

from django.http import HttpResponse, HttpResponseBadRequest
from django.shortcuts import render, redirect
from django.utils.html import escape
from django.db.models import Q

from core.models import (
    TrainingSlot,
    TrainingPlan,
    Athlete,
    PlanWeekPhase,
    AthleteWeekPhaseOverride,
)
from core.stats import base_week_stats, athlete_week_stats, group_week_stats
from .common import (
    _calendar_display_mode,
    _get_selected_plan,
    _get_selected_athlete_from_request,
    _format_km,
    _pct,
)


def _filter_owned(qs, user):
    if user.is_superuser:
        return qs
    return qs.filter(owner=user)


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
def week_phase_set(request, y: int, m: int, d: int):
    if request.method != "POST":
        return HttpResponseBadRequest("POST required")

    plan_id = request.GET.get("plan")
    if not plan_id:
        return HttpResponseBadRequest("Missing plan")

    try:
        plan = _filter_owned(TrainingPlan.objects.all(), request.user).get(id=int(plan_id))
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
        plan = _filter_owned(TrainingPlan.objects.all(), request.user).get(id=int(plan_id))
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
    if athlete.id not in ids:
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


def calendar_view(request):
    plans = _filter_owned(TrainingPlan.objects.order_by("name"), request.user)
    selected_plan = _get_selected_plan(request)
    if selected_plan and not _filter_owned(TrainingPlan.objects.filter(id=selected_plan.id), request.user).exists():
        selected_plan = None
    selected_athlete = _get_selected_athlete_from_request(request)

    plan_athletes = []
    if selected_plan:
        ids = selected_plan.targeted_athlete_ids()
        plan_athletes = list(Athlete.objects.filter(id__in=ids).order_by("name"))
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

            for t in ("10000", "5000", "3000", "1500", "800"):
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
        has_t = {t: (t_m[t] > 0) for t in ("10000", "5000", "3000", "1500", "800")}

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
            "alt_z1_min": alt_z1_min,
            "alt_z2_min": alt_z2_min,
            "alt_z3_min": alt_z3_min,
            "has_alt": has_alt,
            "sum_pct_tooltip": sum_pct_tooltip,
        })

        d += timedelta(days=7)

    week_phases_enabled = bool(getattr(selected_plan, "week_phases_enabled", False)) if selected_plan else False
    weekcolors_enabled = bool(request.session.get("weekcolors_enabled", True))
    show_all_zones = bool(request.session.get("show_all_zones", True))
    show_t_totals = bool(request.session.get("show_t_totals", True))
    show_all_t_totals = bool(request.session.get("show_all_t_totals", True))

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
            "show_all_zones": show_all_zones,
            "show_t_totals": show_t_totals,
            "show_all_t_totals": show_all_t_totals,
            "has_week_clipboard": bool(request.session.get("week_clipboard")),
            "week_phases_enabled": week_phases_enabled,
            "weekcolors_enabled": weekcolors_enabled,
        },
    )
