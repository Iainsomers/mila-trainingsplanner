from datetime import date, date as date_cls
import re

from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.utils import timezone
from django.utils.html import escape
from django.views.decorators.http import require_GET, require_http_methods
from django.core.cache import cache

from core.models import TrainingSlot
from core.parser import parse_segment_text

from .common import (
    _get_selected_plan,
    _get_selected_athlete_from_request,
    _forbid_if_athlete_not_in_plan,
    _week_start,
    _week_days,
    _ensure_zone_in_text,
    _apply_parse_to_segment,
    _apply_mob_only,
    _compute_norm_distance_m,
    _get_effective_slot,
)

STATS_VERSION_KEY = "mila:stats:version"


_CORE_ZONE_RANGE_RE = re.compile(r"^(.*?)(?:\s+|\b)z\s*([1-6])\s*(?:-|>)\s*z\s*([1-6])\s*$", re.IGNORECASE)
_CORE_T_RANGE_RE = re.compile(r"^(.*?)(?:\s+|\b)T\s*(800|1500|3000|5000|10000)\s*(?:-|>)\s*T\s*(800|1500|3000|5000|10000)\s*$", re.IGNORECASE)


def _format_distance_text(distance_m: int) -> str:
    if int(distance_m) % 1000 == 0:
        return f"{int(distance_m) // 1000}km"
    return f"{int(distance_m)}m"


def _format_duration_text(duration_s: int) -> str:
    if int(duration_s) % 60 == 0:
        return f"{int(duration_s) // 60}'"
    minutes = int(duration_s) // 60
    seconds = int(duration_s) % 60
    return f"{minutes}:{seconds:02d}"


def _build_progressive_split_parse(parsed, zone: int, index: int):
    half_distance = _split_value_evenly(parsed.distance_m, 2, index)
    half_duration = _split_value_evenly(parsed.duration_s, 2, index)

    if parsed.rep_distance_m is not None and parsed.reps is not None:
        total_distance = int(parsed.reps) * int(parsed.rep_distance_m)
        split_distance = _split_value_evenly(total_distance, 2, index)
        return {
            "zone": zone,
            "distance_m": int(split_distance or 0),
            "reps": None,
            "rep_distance_m": None,
            "duration_s": None,
            "t_type": (parsed.t_type or ""),
            "message": f"Herkannt: progressive split naar Z{zone} → {int(split_distance or 0)}m",
        }

    if half_distance is not None:
        return {
            "zone": zone,
            "distance_m": int(half_distance),
            "reps": None,
            "rep_distance_m": None,
            "duration_s": None,
            "t_type": (parsed.t_type or ""),
            "message": f"Herkannt: progressive split naar Z{zone} → {int(half_distance)}m",
        }

    if half_duration is not None:
        return {
            "zone": zone,
            "distance_m": None,
            "reps": None,
            "rep_distance_m": None,
            "duration_s": int(half_duration),
            "t_type": (parsed.t_type or ""),
            "message": f"Herkannt: progressive split naar Z{zone} → {int(half_duration)}s",
        }

    return None



def _build_progressive_split_text(parse_data: dict) -> str:
    reps = parse_data.get("reps")
    rep_distance_m = parse_data.get("rep_distance_m")
    distance_m = parse_data.get("distance_m")
    duration_s = parse_data.get("duration_s")
    zone = parse_data.get("zone")
    t_type = parse_data.get("t_type") or ""

    parts = []

    if reps is not None and rep_distance_m is not None:
        parts.append(f"{int(reps)}*{_format_distance_text(int(rep_distance_m))}")
    elif distance_m is not None:
        parts.append(_format_distance_text(int(distance_m)))
    elif duration_s is not None:
        parts.append(_format_duration_text(int(duration_s)))

    if t_type:
        parts.append(f"T{t_type}")
    if zone:
        parts.append(f"Z{int(zone)}")

    return " ".join(parts).strip()


def _t_type_progressive_zone(t_type: str) -> int:
    t = str(t_type or "").strip()
    if t in ("800", "1500"):
        return 5
    return 4


def _parse_progressive_t_source(prefix: str, t_type: str):
    zone = _t_type_progressive_zone(t_type)
    return _parse_core_segment_text(f"{prefix} T{t_type} Z{zone}")


def _build_progressive_t_split_parse(parsed, t_type: str, index: int):
    zone = _t_type_progressive_zone(t_type)
    split_parse = _build_progressive_split_parse(parsed, zone, index)
    if not split_parse:
        return None

    split_parse["t_type"] = str(t_type or "")
    if split_parse.get("distance_m") is not None:
        split_parse["message"] = f"Herkannt: progressive split naar T{t_type} / Z{zone} → {int(split_parse['distance_m'])}m"
    elif split_parse.get("duration_s") is not None:
        split_parse["message"] = f"Herkannt: progressive split naar T{t_type} / Z{zone} → {int(split_parse['duration_s'])}s"
    else:
        split_parse["message"] = f"Herkannt: progressive split naar T{t_type} / Z{zone}"
    return split_parse


def _core_t_range_parts(part: str):
    s = (part or "").strip()
    m = _CORE_T_RANGE_RE.match(s)
    if not m:
        return None

    prefix = (m.group(1) or "").strip()
    t_from = str(m.group(2))
    t_to = str(m.group(3))

    if not prefix:
        return None

    source_parse = _parse_progressive_t_source(prefix, t_from)
    if not source_parse or not source_parse.ok:
        return None

    first_parse = _build_progressive_t_split_parse(source_parse, t_from, 0)
    second_parse = _build_progressive_t_split_parse(source_parse, t_to, 1)

    if not first_parse or not second_parse:
        return None

    return {
        "source_text": s,
        "source_parse": source_parse,
        "first_parse": first_parse,
        "second_parse": second_parse,
    }


def _core_zone_range_parts(part: str):
    s = (part or "").strip()
    m = _CORE_ZONE_RANGE_RE.match(s)
    if not m:
        return None

    prefix = (m.group(1) or "").strip()
    zone_from = int(m.group(2))
    zone_to = int(m.group(3))

    if not prefix:
        return None

    source_parse = _parse_core_segment_text(f"{prefix} z{zone_from}")
    if not source_parse.ok:
        return None

    first_parse = _build_progressive_split_parse(source_parse, zone_from, 0)
    second_parse = _build_progressive_split_parse(source_parse, zone_to, 1)

    if not first_parse or not second_parse:
        return None

    return {
        "source_text": s,
        "source_parse": source_parse,
        "first_parse": first_parse,
        "second_parse": second_parse,
    }


def _split_value_evenly(total, pieces, index):
    if total is None:
        return None
    base = int(total) // pieces
    remainder = int(total) % pieces
    return base + (1 if index >= (pieces - remainder) else 0)




_T_TYPE_RE = re.compile(r"\bT\s*(800|1500|3000|5000|10000)\b", re.IGNORECASE)


def _parse_core_segment_text(text: str):
    s = (text or "").strip()
    if not s:
        return None
    zone_required = _T_TYPE_RE.search(s) is None
    return parse_segment_text(s, zone_required=zone_required)


def _bump_stats_version():
    try:
        cache.incr(STATS_VERSION_KEY)
    except Exception:
        # fallback for caches that don't support incr
        try:
            v = cache.get(STATS_VERSION_KEY) or 0
            cache.set(STATS_VERSION_KEY, int(v) + 1, None)
        except Exception:
            pass


def _tb_flag(request, key: str, default: bool = True) -> bool:
    """
    Trainingsbuilder toggle uit session.
    Default True als key niet bestaat.
    """
    v = request.session.get(key, None)
    if v is None:
        return bool(default)
    return bool(v)


# -----------------------------
# Week copy/paste (BASE only)
# -----------------------------
@require_http_methods(["POST"])
def week_copy(request, yyyy, mm, dd):
    selected_plan = _get_selected_plan(request)
    if not selected_plan:
        return HttpResponse("No plan", status=400)

    week_start = _week_start(date_cls(int(yyyy), int(mm), int(dd)))

    payload = {
        "source_plan_id": selected_plan.id,
        "source_week_start": week_start.isoformat(),
        "days": {},
    }

    for offset, day in enumerate(_week_days(week_start)):
        offset_key = str(offset)
        payload["days"][offset_key] = {}

        for slot_index in (1, 2):
            base_slot = (
                TrainingSlot.objects.filter(
                    plan=selected_plan,
                    athlete__isnull=True,
                    date=day,
                    slot_index=slot_index,
                )
                .prefetch_related("segments")
                .first()
            )

            if not base_slot:
                payload["days"][offset_key][str(slot_index)] = []
                continue

            segs = []
            for seg in base_slot.segments.order_by("order", "id"):
                segs.append({
                    "type": seg.type,
                    "order": int(seg.order or 0),
                    "text": seg.text or "",
                    "zone": (seg.zone or ""),
                    "reps": int(seg.reps or 1),
                    "distance_m": int(seg.distance_m) if seg.distance_m is not None else None,
                    "duration_s": int(seg.duration_s) if seg.duration_s is not None else None,
                    "norm_distance_m": int(seg.norm_distance_m) if seg.norm_distance_m is not None else None,
                    "parse_ok": bool(seg.parse_ok),
                    "parse_message": seg.parse_message or "",
                    "special": (getattr(seg, "special", "") or ""),
                    "t_type": (getattr(seg, "t_type", "") or ""),
                })

            payload["days"][offset_key][str(slot_index)] = segs

    request.session["week_clipboard"] = payload
    request.session.modified = True

    resp = HttpResponse("")
    resp["HX-Refresh"] = "true"
    return resp


@require_http_methods(["POST"])
def week_paste(request, yyyy, mm, dd):
    selected_plan = _get_selected_plan(request)
    if not selected_plan:
        return HttpResponse("No plan", status=400)

    clipboard = request.session.get("week_clipboard")
    if not clipboard or not isinstance(clipboard, dict):
        return HttpResponse("No week clipboard", status=400)

    week_start = _week_start(date_cls(int(yyyy), int(mm), int(dd)))
    days_payload = clipboard.get("days") or {}
    if not isinstance(days_payload, dict):
        return HttpResponse("Invalid week clipboard", status=400)

    for offset, day in enumerate(_week_days(week_start)):
        offset_key = str(offset)
        day_slots = days_payload.get(offset_key) or {}
        if not isinstance(day_slots, dict):
            day_slots = {}

        for slot_index in (1, 2):
            segs = day_slots.get(str(slot_index), [])
            if not isinstance(segs, list):
                segs = []

            base_slot, _ = TrainingSlot.objects.get_or_create(
                plan=selected_plan,
                athlete=None,
                date=day,
                slot_index=slot_index,
            )

            base_slot.segments.all().delete()
            now = timezone.now()

            for item in segs:
                if not isinstance(item, dict):
                    continue

                seg = base_slot.segments.create(
                    type=item.get("type") or "CORE",
                    text=item.get("text") or "",
                    order=int(item.get("order") or 0),
                )
                seg.zone = (item.get("zone") or "")
                seg.reps = int(item.get("reps") or 1)
                seg.distance_m = item.get("distance_m", None)
                seg.duration_s = item.get("duration_s", None)
                seg.norm_distance_m = item.get("norm_distance_m", None)
                seg.parse_ok = bool(item.get("parse_ok"))
                seg.parse_message = item.get("parse_message") or ""
                seg.special = item.get("special") or ""
                if hasattr(seg, "t_type"):
                    seg.t_type = item.get("t_type") or ""
                seg.parsed_at = now
                seg.save()

    _bump_stats_version()

    resp = HttpResponse("")
    resp["HX-Refresh"] = "true"
    return resp


@require_http_methods(["POST"])
def week_clipboard_clear(request):
    request.session.pop("week_clipboard", None)
    request.session.modified = True
    resp = HttpResponse("")
    resp["HX-Refresh"] = "true"
    return resp


# -----------------------------
# Slot endpoints
# -----------------------------
def slot_detail(request, slot_id):
    slot = get_object_or_404(TrainingSlot, id=slot_id)
    segments = slot.segments.order_by("order", "id")

    return HttpResponse(
        "<h3>Training detail</h3>"
        f"<p>{slot.date} – slot {slot.slot_index}</p>"
        f"<p><b>Core:</b> {escape(slot.core_text())}</p>"
        "<hr>"
        + "<br>".join(escape(f"{s.get_type_display()}: {s.text}") for s in segments)
    )


@require_GET
def slot_open(request, y, m, d, slot_index):
    selected_plan = _get_selected_plan(request)

    day = date(int(y), int(m), int(d))
    slot, _ = TrainingSlot.objects.get_or_create(
        date=day,
        slot_index=int(slot_index),
        plan=selected_plan,
        athlete=None,
    )
    return redirect("slot_detail", slot_id=slot.id)


@require_http_methods(["POST"])
def slot_copy(request, yyyy, mm, dd, slot_index):
    selected_plan = _get_selected_plan(request)

    d = date_cls(int(yyyy), int(mm), int(dd))
    slot_index = int(slot_index)

    athlete = _get_selected_athlete_from_request(request)
    forbid = _forbid_if_athlete_not_in_plan(selected_plan, athlete)
    if forbid:
        return forbid

    eff = _get_effective_slot(selected_plan, athlete, d, slot_index, prefetch_segments=True)
    visible_slot = eff["visible_slot"]
    has_fix = eff["has_fix"]

    segments_payload = []
    if visible_slot:
        for seg in visible_slot.segments.order_by("order", "id"):
            segments_payload.append({
                "type": seg.type,
                "order": int(seg.order or 0),
                "text": seg.text or "",
                "zone": (seg.zone or ""),
                "reps": int(seg.reps or 1),
                "distance_m": int(seg.distance_m) if seg.distance_m is not None else None,
                "duration_s": int(seg.duration_s) if seg.duration_s is not None else None,
                "norm_distance_m": int(seg.norm_distance_m) if seg.norm_distance_m is not None else None,
                "parse_ok": bool(seg.parse_ok),
                "parse_message": seg.parse_message or "",
                "special": (getattr(seg, "special", "") or ""),
            })

    request.session["training_clipboard"] = {
        "source_date": d.isoformat(),
        "source_slot_index": slot_index,
        "plan_id": selected_plan.id if selected_plan else None,
        "athlete_id": athlete.id if athlete else None,
        "copied_from_has_fix": bool(has_fix),
        "segments": segments_payload,
    }
    request.session.modified = True

    resp = HttpResponse("")
    resp["HX-Trigger"] = "closeModal"
    resp["HX-Refresh"] = "true"
    return resp


@require_http_methods(["POST"])
def slot_paste(request, yyyy, mm, dd, slot_index):
    selected_plan = _get_selected_plan(request)

    clipboard = request.session.get("training_clipboard")
    if not clipboard or not isinstance(clipboard, dict):
        return HttpResponse("No clipboard", status=400)

    segments_payload = clipboard.get("segments") or []
    if not isinstance(segments_payload, list):
        return HttpResponse("Invalid clipboard", status=400)

    d = date_cls(int(yyyy), int(mm), int(dd))
    slot_index = int(slot_index)

    athlete = _get_selected_athlete_from_request(request)
    forbid = _forbid_if_athlete_not_in_plan(selected_plan, athlete)
    if forbid:
        return forbid

    if athlete:
        slot, _ = TrainingSlot.objects.get_or_create(date=d, slot_index=slot_index, plan=selected_plan, athlete=athlete)
        is_override = True
    else:
        slot, _ = TrainingSlot.objects.get_or_create(date=d, slot_index=slot_index, plan=selected_plan, athlete=None)
        is_override = False

    slot.segments.all().delete()
    now = timezone.now()

    for item in segments_payload:
        if not isinstance(item, dict):
            continue

        seg = slot.segments.create(
            type=item.get("type") or "CORE",
            text=item.get("text") or "",
            order=int(item.get("order") or 0),
        )
        seg.zone = (item.get("zone") or "")
        seg.reps = int(item.get("reps") or 1)
        seg.distance_m = item.get("distance_m", None)
        seg.duration_s = item.get("duration_s", None)
        seg.norm_distance_m = item.get("norm_distance_m", None)
        seg.parse_ok = bool(item.get("parse_ok"))
        seg.parse_message = item.get("parse_message") or ""
        seg.special = item.get("special") or ""
        seg.parsed_at = now
        seg.save()

    _bump_stats_version()

    cell_html = render_to_string(
        "core/partials/calendar_cell.html",
        {"day": d, "slot": slot, "slot_index": slot_index, "oob": True, "selected_athlete": athlete, "is_override": is_override},
        request=request,
    )
    resp = HttpResponse(cell_html)
    resp["HX-Refresh"] = "true"
    return resp


@require_http_methods(["POST"])
def slot_clipboard_clear(request):
    request.session.pop("training_clipboard", None)
    request.session.modified = True
    resp = HttpResponse("")
    resp["HX-Trigger"] = "closeModal"
    resp["HX-Refresh"] = "true"
    return resp


@require_http_methods(["POST"])
def slot_reset_override(request, yyyy, mm, dd, slot_index):
    selected_plan = _get_selected_plan(request)

    athlete = _get_selected_athlete_from_request(request)
    if not athlete:
        return HttpResponse("No athlete", status=400)

    forbid = _forbid_if_athlete_not_in_plan(selected_plan, athlete)
    if forbid:
        return forbid

    d = date_cls(int(yyyy), int(mm), int(dd))
    slot_index = int(slot_index)

    TrainingSlot.objects.filter(plan=selected_plan, athlete=athlete, date=d, slot_index=slot_index).delete()
    _bump_stats_version()

    base_slot = TrainingSlot.objects.filter(
        plan=selected_plan, athlete__isnull=True, date=d, slot_index=slot_index
    ).prefetch_related("segments").first()

    cell_html = render_to_string(
        "core/partials/calendar_cell.html",
        {"day": d, "slot": base_slot, "slot_index": slot_index, "oob": True, "selected_athlete": athlete, "is_override": False},
        request=request,
    )
    resp = HttpResponse(cell_html)
    resp["HX-Trigger"] = "closeModal"
    resp["HX-Refresh"] = "true"
    return resp


# -----------------------------
# Slot modal (training builder)
# -----------------------------
@require_http_methods(["GET", "POST"])
def slot_modal(request, yyyy, mm, dd, slot_index):
    selected_plan = _get_selected_plan(request)

    athlete = _get_selected_athlete_from_request(request)
    forbid = _forbid_if_athlete_not_in_plan(selected_plan, athlete)
    if forbid:
        return forbid

    d = date_cls(int(yyyy), int(mm), int(dd))
    slot_index = int(slot_index)

    # Trainingsbuilder toggles (uit session)
    tb_show_wu = _tb_flag(request, "tb_show_wu", True)
    tb_show_mob = _tb_flag(request, "tb_show_mob", True)
    tb_show_sprint = _tb_flag(request, "tb_show_sprint", True)
    tb_show_core2 = _tb_flag(request, "tb_show_core2", True)
    tb_show_cd = _tb_flag(request, "tb_show_cd", True)

    eff = _get_effective_slot(selected_plan, athlete, d, slot_index, prefetch_segments=True)
    visible_slot = eff["visible_slot"]
    has_fix = eff["has_fix"]

    if request.method == "GET":
        wu_seg = visible_slot.segments.filter(type="WU").order_by("order", "id").first() if visible_slot else None
        mob_seg = visible_slot.segments.filter(type="MOB").order_by("order", "id").first() if visible_slot else None
        sprint_seg = visible_slot.segments.filter(type="SPR").order_by("order", "id").first() if visible_slot else None
        core_segs = list(visible_slot.segments.filter(type="CORE").order_by("order", "id")) if visible_slot else []
        core2_seg = visible_slot.segments.filter(type="CORE2").order_by("order", "id").first() if visible_slot else None
        alt_seg = visible_slot.segments.filter(type="ALT").order_by("order", "id").first() if visible_slot else None
        cd_seg = visible_slot.segments.filter(type="CD").order_by("order", "id").first() if visible_slot else None

        return render(
            request,
            "core/partials/slot_modal.html",
            {
                "day": d,
                "slot_index": slot_index,

                "tb_show_wu": tb_show_wu,
                "tb_show_mob": tb_show_mob,
                "tb_show_sprint": tb_show_sprint,
                "tb_show_core2": tb_show_core2,
                "tb_show_cd": tb_show_cd,

                "wu_text": (wu_seg.text if (wu_seg and tb_show_wu) else ""),
                "mob_text": (mob_seg.text if (mob_seg and tb_show_mob) else ""),
                "sprint_text": (sprint_seg.text if (sprint_seg and tb_show_sprint) else ""),
                "core_text": (" // ".join(seg.text for seg in core_segs if seg.text) if core_segs else ""),
                "core2_text": (core2_seg.text if (core2_seg and tb_show_core2) else ""),
                "alt_text": (alt_seg.text if alt_seg else ""),
                "cd_text": (cd_seg.text if (cd_seg and tb_show_cd) else ""),

                "wu_feedback": "", "wu_ok": None,
                "sprint_feedback": "", "sprint_ok": None,
                "core_feedback": "", "core_ok": None,
                "core2_feedback": "", "core2_ok": None,
                "alt_feedback": "", "alt_ok": None,
                "cd_feedback": "", "cd_ok": None,

                "selected_plan": selected_plan,
                "selected_athlete": athlete,
                "is_override": bool(has_fix),
            },
        )

    # POST: maak slot (base/override)
    if athlete:
        slot, _ = TrainingSlot.objects.get_or_create(date=d, slot_index=slot_index, plan=selected_plan, athlete=athlete)
        is_override = True
    else:
        slot, _ = TrainingSlot.objects.get_or_create(date=d, slot_index=slot_index, plan=selected_plan, athlete=None)
        is_override = False

    action = (request.POST.get("action") or "").strip().lower()

    # Delete action
    if action == "delete" and athlete:
        slot.segments.all().delete()
        _bump_stats_version()
        cell_html = render_to_string(
            "core/partials/calendar_cell.html",
            {"day": d, "slot": slot, "slot_index": slot_index, "oob": True, "selected_athlete": athlete, "is_override": True},
            request=request,
        )
        resp = HttpResponse(cell_html)
        resp["HX-Trigger"] = "closeModal"
        resp["HX-Refresh"] = "true"
        return resp

    if action == "delete" and not athlete:
        slot.delete()
        _bump_stats_version()
        cell_html = render_to_string(
            "core/partials/calendar_cell.html",
            {"day": d, "slot": None, "slot_index": slot_index, "oob": True, "selected_athlete": None, "is_override": False},
            request=request,
        )
        resp = HttpResponse(cell_html)
        resp["HX-Trigger"] = "closeModal"
        resp["HX-Refresh"] = "true"
        return resp

    # bestaande segmenten
    wu_seg = slot.segments.filter(type="WU").order_by("order", "id").first()
    mob_seg = slot.segments.filter(type="MOB").order_by("order", "id").first()
    sprint_seg = slot.segments.filter(type="SPR").order_by("order", "id").first()
    core_seg = slot.segments.filter(type="CORE").order_by("order", "id").first()
    core2_seg = slot.segments.filter(type="CORE2").order_by("order", "id").first()
    alt_seg = slot.segments.filter(type="ALT").order_by("order", "id").first()
    cd_seg = slot.segments.filter(type="CD").order_by("order", "id").first()

    # input teksten (respecteer toggles)
    wu_text = (request.POST.get("wu_text") or "").strip() if tb_show_wu else ""
    mob_text = (request.POST.get("mob_text") or "").strip() if tb_show_mob else ""
    sprint_text = (request.POST.get("sprint_text") or "").strip() if tb_show_sprint else ""
    core_text = (request.POST.get("core_text") or "").strip()
    core2_text = (request.POST.get("core2_text") or "").strip() if tb_show_core2 else ""
    alt_text = (request.POST.get("alt_text") or "").strip()
    cd_text = (request.POST.get("cd_text") or "").strip() if tb_show_cd else ""

    # validatie: Core of Alt moet gevuld zijn
    if not core_text and not alt_text:
        return render(
            request,
            "core/partials/slot_modal.html",
            {
                "day": d,
                "slot_index": slot_index,

                "tb_show_wu": tb_show_wu,
                "tb_show_mob": tb_show_mob,
                "tb_show_sprint": tb_show_sprint,
                "tb_show_core2": tb_show_core2,
                "tb_show_cd": tb_show_cd,

                "wu_text": wu_text,
                "mob_text": mob_text,
                "sprint_text": sprint_text,
                "core_text": core_text,
                "core2_text": core2_text,
                "alt_text": alt_text,
                "cd_text": cd_text,

                "core_error": "Vul Core in, of vul Alternative.",

                "wu_feedback": "", "wu_ok": None,
                "sprint_feedback": "", "sprint_ok": None,
                "core_feedback": "", "core_ok": None,
                "core2_feedback": "", "core2_ok": None,
                "alt_feedback": "", "alt_ok": None,
                "cd_feedback": "", "cd_ok": None,

                "selected_plan": selected_plan,
                "selected_athlete": athlete,
                "is_override": is_override,
            },
        )

    # CORE2 mag niet als enige segment
    if core2_text and not any([wu_text, mob_text, sprint_text, core_text, alt_text, cd_text]):
        return render(
            request,
            "core/partials/slot_modal.html",
            {
                "day": d,
                "slot_index": slot_index,

                "tb_show_wu": tb_show_wu,
                "tb_show_mob": tb_show_mob,
                "tb_show_sprint": tb_show_sprint,
                "tb_show_core2": tb_show_core2,
                "tb_show_cd": tb_show_cd,

                "wu_text": wu_text,
                "mob_text": mob_text,
                "sprint_text": sprint_text,
                "core_text": core_text,
                "core2_text": core2_text,
                "alt_text": alt_text,
                "cd_text": cd_text,

                "core2_error": "2nd core mag niet als enige segment in het slot staan.",

                "wu_feedback": "", "wu_ok": None,
                "sprint_feedback": "", "sprint_ok": None,
                "core_feedback": "", "core_ok": None,
                "core2_feedback": "", "core2_ok": None,
                "alt_feedback": "", "alt_ok": None,
                "cd_feedback": "", "cd_ok": None,

                "selected_plan": selected_plan,
                "selected_athlete": athlete,
                "is_override": is_override,
            },
        )

    # parsing
    sprint_text_for_parse = _ensure_zone_in_text(sprint_text, "6")

    wu_parse = parse_segment_text(wu_text) if wu_text else None
    sprint_parse = parse_segment_text(sprint_text_for_parse) if sprint_text else None
    core_parse = _parse_core_segment_text(core_text) if core_text else None
    core2_parse = _parse_core_segment_text(core2_text) if core2_text else None
    alt_parse = parse_segment_text(alt_text, zone_required=False) if alt_text else None
    cd_parse = parse_segment_text(cd_text) if cd_text else None

    parse_block = False
    if core_parse is not None and not core_parse.ok:
        parse_block = True
    if wu_parse is not None and not wu_parse.ok:
        parse_block = True
    if sprint_parse is not None and not sprint_parse.ok:
        parse_block = True
    if core2_parse is not None and not core2_parse.ok:
        parse_block = True
    if alt_parse is not None and not alt_parse.ok:
        parse_block = True
    if cd_parse is not None and not cd_parse.ok:
        parse_block = True

    if parse_block:
        return render(
            request,
            "core/partials/slot_modal.html",
            {
                "day": d,
                "slot_index": slot_index,

                "tb_show_wu": tb_show_wu,
                "tb_show_mob": tb_show_mob,
                "tb_show_sprint": tb_show_sprint,
                "tb_show_core2": tb_show_core2,
                "tb_show_cd": tb_show_cd,

                "wu_text": wu_text,
                "mob_text": mob_text,
                "sprint_text": sprint_text,
                "core_text": core_text,
                "core2_text": core2_text,
                "alt_text": alt_text,
                "cd_text": cd_text,

                "wu_feedback": (wu_parse.message if wu_parse else ""),
                "wu_ok": (wu_parse.ok if wu_parse else None),
                "sprint_feedback": (sprint_parse.message if sprint_parse else ""),
                "sprint_ok": (sprint_parse.ok if sprint_parse else None),
                "core_feedback": (core_parse.message if core_parse else ""),
                "core_ok": (core_parse.ok if core_parse else None),
                "core2_feedback": (core2_parse.message if core2_parse else ""),
                "core2_ok": (core2_parse.ok if core2_parse else None),
                "alt_feedback": (alt_parse.message if alt_parse else ""),
                "alt_ok": (alt_parse.ok if alt_parse else None),
                "cd_feedback": (cd_parse.message if cd_parse else ""),
                "cd_ok": (cd_parse.ok if cd_parse else None),

                "selected_plan": selected_plan,
                "selected_athlete": athlete,
                "is_override": is_override,
            },
        )

    now = timezone.now()

    # Save WU
    if wu_text:
        if wu_seg:
            wu_seg.text = wu_text
        else:
            wu_seg = slot.segments.create(type="WU", text=wu_text, order=0)
        _apply_parse_to_segment(wu_seg, wu_parse)
        wu_seg.parsed_at = now
        wu_seg.save()
    else:
        if wu_seg:
            wu_seg.delete()

    # Save MOB
    if mob_text:
        if mob_seg:
            _apply_mob_only(mob_seg, mob_text)
            mob_seg.save()
        else:
            mob_seg = slot.segments.create(type="MOB", text=mob_text, order=1)
            _apply_mob_only(mob_seg, mob_text)
            mob_seg.save()
    else:
        if mob_seg:
            mob_seg.delete()

    # Save SPRINT
    if sprint_text:
        if sprint_seg:
            sprint_seg.text = sprint_text
        else:
            sprint_seg = slot.segments.create(type="SPR", text=sprint_text, order=2)
        _apply_parse_to_segment(sprint_seg, sprint_parse)
        sprint_seg.zone = "6"
        sprint_seg.norm_distance_m = _compute_norm_distance_m(sprint_seg)
        sprint_seg.parsed_at = now
        sprint_seg.save()
    else:
        if sprint_seg:
            sprint_seg.delete()

    # Save CORE
    if core_text:
        parts = [p.strip() for p in core_text.split("//") if p.strip()]

        slot.segments.filter(type="CORE").delete()

        order = 3

        for part in parts:
            range_parts = _core_zone_range_parts(part)
            if not range_parts:
                range_parts = _core_t_range_parts(part)

            if range_parts:
                seg = slot.segments.create(
                    type="CORE",
                    text=range_parts["source_text"],
                    order=order,
                )
                _apply_parse_to_segment(seg, range_parts["source_parse"])
                seg.parse_message = range_parts["source_text"]
                seg.parsed_at = now
                seg.save()
                order += 1
                continue

            seg = slot.segments.create(
                type="CORE",
                text=part,
                order=order,
            )

            part_parse = _parse_core_segment_text(part)
            if not part_parse or not part_parse.ok:
                order += 1
                continue

            _apply_parse_to_segment(seg, part_parse)
            seg.parsed_at = now
            seg.save()
            order += 1
    else:
        slot.segments.filter(type="CORE").delete()

    # Save ALT (telt nog niet mee)
        # Save ALT (telt nog niet mee in normale zones, maar wél ALT-minuten mogelijk)
    if alt_text:
        if alt_seg:
            alt_seg.text = alt_text
            alt_seg.order = 6
        else:
            alt_seg = slot.segments.create(type="ALT", text=alt_text, order=6)

        alt_seg.reps = 1
        alt_seg.distance_m = None
        alt_seg.norm_distance_m = None
        alt_seg.special = ""

        if alt_parse and alt_parse.ok:
            alt_seg.zone = str(alt_parse.zone) if (alt_parse.zone and alt_parse.zone) else ""
            alt_seg.duration_s = int(alt_parse.duration_s) if (alt_parse and alt_parse.duration_s) else None
            alt_seg.parse_ok = True
            alt_seg.parse_message = alt_parse.message or ""
        else:
            alt_seg.zone = ""
            alt_seg.duration_s = None
            alt_seg.parse_ok = False if alt_parse else True
            alt_seg.parse_message = (alt_parse.message if alt_parse else "")

        alt_seg.parsed_at = now
        alt_seg.save()
    else:
        if alt_seg:
            alt_seg.delete()



    # Save CORE2
    if core2_text:
        if core2_seg:
            core2_seg.text = core2_text
            core2_seg.order = 4
        else:
            core2_seg = slot.segments.create(type="CORE2", text=core2_text, order=4)
        _apply_parse_to_segment(core2_seg, core2_parse)
        core2_seg.norm_distance_m = _compute_norm_distance_m(core2_seg)
        core2_seg.parsed_at = now
        core2_seg.save()
    else:
        if core2_seg:
            core2_seg.delete()

    # Save CD
    if cd_text:
        if cd_seg:
            cd_seg.text = cd_text
            cd_seg.order = 5
        else:
            cd_seg = slot.segments.create(type="CD", text=cd_text, order=5)
        _apply_parse_to_segment(cd_seg, cd_parse)
        cd_seg.parsed_at = now
        cd_seg.save()
    else:
        if cd_seg:
            cd_seg.delete()

    _bump_stats_version()

    cell_html = render_to_string(
        "core/partials/calendar_cell.html",
        {"day": d, "slot": slot, "slot_index": slot_index, "oob": True, "selected_athlete": athlete, "is_override": is_override},
        request=request,
    )
    resp = HttpResponse(cell_html)
    resp["HX-Trigger"] = "closeModal"
    resp["HX-Refresh"] = "true"
    return resp
