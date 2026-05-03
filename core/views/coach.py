from datetime import timedelta

from django.http import HttpResponse
from django.shortcuts import render, get_object_or_404, redirect
from django.views.decorators.http import require_GET, require_http_methods
from django.contrib.auth.decorators import login_required
from django.db.models.functions import Lower

from core.models import TrainingPlan, Athlete, Group, PlanMembership, CoachSettings, TrainingSlot, PlanWeekPhase
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


@login_required
@require_GET
def dashboard_view(request):
    return render(request, "core/dashboard.html")


@login_required
@require_GET
def coach_console_view(request):
    return render(request, "core/coach_console.html")


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

    plans = _filter_owned(qs, request.user)
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
    if sort == "start":
        qs = TrainingPlan.objects.order_by("start_date")
    elif sort == "end":
        qs = TrainingPlan.objects.order_by("end_date")
    else:
        qs = TrainingPlan.objects.order_by("name")

    plans = _filter_owned(qs, request.user)

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
                source_plan = _filter_owned(TrainingPlan.objects.all(), request.user).filter(id=source_plan_id).first()
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
        {"mode": "create", "plan": None, "form": form, "errors": errors, "source_plans": source_plans},
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
