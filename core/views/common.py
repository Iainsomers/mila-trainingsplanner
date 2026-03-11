from datetime import timedelta, date as date_cls
import re

from django.http import HttpResponse
from django.utils import timezone
from django.db.models import Q

from core.models import TrainingPlan, Athlete, TrainingSlot


# Backwards-compatible constant (sommige views importeren dit nog)
CALENDAR_DISPLAY_MODE = "core_only"


def _calendar_display_mode(request) -> str:
    """
    Calendar display mode:
    - core_only: toon alleen core/alt in cell (hover blijft volledig)
    - all: toon alle segmenten in cell
    Default = core_only
    """
    show_only_core = request.session.get("calendar_show_only_core", True)
    return "core_only" if bool(show_only_core) else "all"


DEFAULT_ZONE_SPEED_MPS = {
    "1": 2.8,
    "2": 3.1,
    "3": 3.4,
    "4": 3.8,
    "5": 4.2,
    "6": 4.6,  # sprint norm (intern)
}

# Calendar/time logic uses this global default for now
ZONE_SPEED_MPS = dict(DEFAULT_ZONE_SPEED_MPS)


# =============================
# Generic helpers
# =============================
def _format_km(meters: int) -> str:
    km = (meters or 0) / 1000.0
    return f"{km:.1f}"


def _pct(part: float, total: float) -> str:
    if not total:
        return "—"
    return f"{(100.0 * float(part) / float(total)):.1f}%"


def _parse_iso_date(value: str):
    v = (value or "").strip()
    if not v:
        return None
    return date_cls.fromisoformat(v)


def _parse_int(value: str):
    v = (value or "").strip()
    if not v:
        return None
    return int(v)


def _parse_float(value: str):
    v = (value or "").strip()
    if not v:
        return None
    v = v.replace(",", ".")
    return float(v)


def _clean_int_list(values):
    out = []
    for x in values or []:
        sx = str(x).strip()
        if sx.isdigit():
            out.append(int(sx))
    return out


# =============================
# Pace helpers (min/km <-> m/s)
# =============================
def _mps_to_pace_str(mps: float) -> str:
    try:
        mps = float(mps)
    except (TypeError, ValueError):
        mps = 0.0
    if mps <= 0:
        return "—"
    sec_per_km = 1000.0 / mps
    mm = int(sec_per_km // 60)
    ss = int(round(sec_per_km - 60 * mm))
    if ss == 60:
        mm += 1
        ss = 0
    return f"{mm}:{ss:02d}"


def _pace_to_mps(pace_str: str) -> float:
    s = (pace_str or "").strip()
    if not s:
        raise ValueError("empty")

    s = s.replace(" ", "")
    if ":" in s:
        parts = s.split(":")
        if len(parts) != 2:
            raise ValueError("bad pace format")
        mm = int(parts[0])
        ss = int(parts[1])
        if mm < 0 or ss < 0 or ss >= 60:
            raise ValueError("bad pace range")
        sec_per_km = mm * 60 + ss
    else:
        mins = float(s.replace(",", "."))
        if mins <= 0:
            raise ValueError("bad pace range")
        sec_per_km = mins * 60.0

    if sec_per_km <= 0:
        raise ValueError("bad pace range")
    return 1000.0 / float(sec_per_km)


# =============================
# Speed helpers (km/h <-> m/s)
# =============================
def _mps_to_kmh_str(mps: float) -> str:
    try:
        mps = float(mps)
    except (TypeError, ValueError):
        return "—"
    if mps <= 0:
        return "—"
    kmh = mps * 3.6
    if abs(kmh - round(kmh)) < 1e-9:
        return str(int(round(kmh)))
    return f"{kmh:.1f}".rstrip("0").rstrip(".")


def _kmh_to_mps(kmh_str: str) -> float:
    s = (kmh_str or "").strip()
    if not s:
        raise ValueError("empty")
    s = s.replace(",", ".")
    kmh = float(s)
    if kmh <= 0:
        raise ValueError("bad speed range")
    return kmh / 3.6


def _zone_unit_label(unit: str) -> str:
    unit = (unit or "").strip().lower()
    return "km/h" if unit == "kmh" else "min/km"


def _parse_manual_zone_values_required(post, unit: str):
    """
    Z1..Z5 required, strict increasing speed in m/s.
    unit="pace" => min/km input
    unit="kmh"  => km/h input
    Returns (zone_speed_mps, errors, normalized_input, other_under)
    """
    unit = (unit or "").strip().lower()
    if unit not in ("pace", "kmh"):
        unit = "pace"

    errors = []
    out_mps = {}
    normalized_input = {}
    other_under = {}

    for z in ("1", "2", "3", "4", "5"):
        raw = (post.get(f"z{z}_pace") or "").strip()
        if not raw:
            errors.append(f"Z{z}: waarde is verplicht.")
            out_mps[z] = None
            normalized_input[z] = ""
            other_under[z] = "—"
            continue

        try:
            mps = float(_pace_to_mps(raw)) if unit == "pace" else float(_kmh_to_mps(raw))
        except Exception:
            errors.append(f"Z{z}: ongeldig ({'bijv. 4:30' if unit=='pace' else 'bijv. 15'}).")
            out_mps[z] = None
            normalized_input[z] = raw
            other_under[z] = "—"
            continue

        if mps <= 0:
            errors.append(f"Z{z}: waarde moet > 0 zijn.")
            out_mps[z] = None
            normalized_input[z] = raw
            other_under[z] = "—"
            continue

        out_mps[z] = mps
        if unit == "pace":
            normalized_input[z] = _mps_to_pace_str(mps)
            other_under[z] = f"{_mps_to_kmh_str(mps)} km/h"
        else:
            normalized_input[z] = _mps_to_kmh_str(mps)
            other_under[z] = f"{_mps_to_pace_str(mps)} min/km"

    if all(isinstance(out_mps.get(z), (int, float)) and float(out_mps[z]) > 0 for z in ("1", "2", "3", "4", "5")):
        s1, s2, s3, s4, s5 = [float(out_mps[z]) for z in ("1", "2", "3", "4", "5")]
        if not (s1 < s2 < s3 < s4 < s5):
            errors.append("Zone-volgorde fout: Z1 moet langzamer zijn dan Z2, …, en Z5 het snelst.")

    # Z6 fixed internal
    out_mps["6"] = float(DEFAULT_ZONE_SPEED_MPS["6"])
    return out_mps, errors, normalized_input, other_under


# =============================
# Plan / athlete selection helpers
# =============================
def _ranges_overlap(start_a, end_a, start_b, end_b) -> bool:
    if not (start_a and end_a and start_b and end_b):
        return False
    return start_a <= end_b and start_b <= end_a


def _plans_targeting_athlete(athlete_id: int):
    return (
        TrainingPlan.objects.filter(
            Q(athletes__id=athlete_id) | Q(groups__athletes__id=athlete_id)
        )
        .distinct()
        .order_by("name")
    )


def _plan_targets_athlete(plan: TrainingPlan, athlete: Athlete) -> bool:
    if not plan or not athlete:
        return False
    return TrainingPlan.objects.filter(id=plan.id).filter(
        Q(athletes__id=athlete.id) | Q(groups__athletes__id=athlete.id)
    ).exists()


def _get_selected_plan(request):
    plan_id = (request.GET.get("plan") or "").strip()
    if not plan_id:
        plan_id = (request.POST.get("plan") or "").strip()

    if plan_id.isdigit():
        p = TrainingPlan.objects.filter(id=int(plan_id)).first()
        if p:
            request.session["selected_plan_id"] = p.id
            request.session.modified = True
            return p

    session_pid = request.session.get("selected_plan_id")
    if isinstance(session_pid, int):
        p = TrainingPlan.objects.filter(id=session_pid).first()
        if p:
            return p

    p = TrainingPlan.objects.filter(name="Default").first()
    if p:
        request.session["selected_plan_id"] = p.id
        request.session.modified = True
        return p

    p = TrainingPlan.objects.order_by("name").first()
    if p:
        request.session["selected_plan_id"] = p.id
        request.session.modified = True
    return p


def _get_selected_athlete_from_request(request):
    athlete_id = (request.GET.get("athlete") or request.POST.get("athlete") or "").strip()
    if athlete_id.isdigit():
        return Athlete.objects.filter(id=int(athlete_id)).first()
    return None


def _forbid_if_athlete_not_in_plan(plan: TrainingPlan, athlete: Athlete):
    if athlete and plan and not _plan_targets_athlete(plan, athlete):
        return HttpResponse("Athlete not in plan", status=403)
    return None


# =============================
# Base/override helpers (needed by slots.py)
# =============================
def _get_base_slot(plan: TrainingPlan, day: date_cls, slot_index: int, prefetch_segments: bool = False):
    if not plan:
        return None
    qs = TrainingSlot.objects.filter(plan=plan, athlete__isnull=True, date=day, slot_index=int(slot_index))
    if prefetch_segments:
        qs = qs.prefetch_related("segments")
    return qs.first()


def _get_override_slot(plan: TrainingPlan, athlete: Athlete, day: date_cls, slot_index: int, prefetch_segments: bool = False):
    if not plan or not athlete:
        return None
    qs = TrainingSlot.objects.filter(plan=plan, athlete=athlete, date=day, slot_index=int(slot_index))
    if prefetch_segments:
        qs = qs.prefetch_related("segments")
    return qs.first()


def _get_effective_slot(plan: TrainingPlan, athlete: Athlete, day: date_cls, slot_index: int, prefetch_segments: bool = False):
    base_slot = _get_base_slot(plan, day, slot_index, prefetch_segments=prefetch_segments)
    override_slot = _get_override_slot(plan, athlete, day, slot_index, prefetch_segments=prefetch_segments)
    visible_slot = override_slot if override_slot else base_slot
    return {
        "base_slot": base_slot,
        "override_slot": override_slot,
        "visible_slot": visible_slot,
        "has_fix": bool(override_slot),
    }


# =============================
# Week helpers
# =============================
def _week_start(d: date_cls) -> date_cls:
    return d - timedelta(days=d.weekday())


def _week_days(week_start: date_cls):
    return [week_start + timedelta(days=i) for i in range(7)]


# =============================
# Segment helpers (used by slot_modal)
# =============================
def _compute_norm_distance_m(seg):
    if seg.distance_m:
        return int(seg.reps) * int(seg.distance_m)

    if seg.duration_s:
        speed = ZONE_SPEED_MPS.get(seg.zone)
        if speed is None:
            return None
        return int(round(int(seg.duration_s) * float(speed)))

    return None


def _apply_parse_to_segment(seg, parse_res):
    seg.parse_ok = bool(parse_res.ok)
    seg.parse_message = parse_res.message or ""
    seg.parsed_at = timezone.now()

    if hasattr(seg, "special"):
        seg.special = (parse_res.special or "")

    if parse_res.zone is not None:
        seg.zone = str(parse_res.zone)

    if parse_res.duration_s is not None:
        seg.duration_s = int(parse_res.duration_s)
        seg.reps = 1
        seg.distance_m = None
        seg.norm_distance_m = _compute_norm_distance_m(seg)
        return

    if parse_res.distance_m is not None:
        if parse_res.reps is not None and parse_res.rep_distance_m is not None:
            seg.reps = int(parse_res.reps)
            seg.distance_m = int(parse_res.rep_distance_m)
        else:
            seg.reps = 1
            seg.distance_m = int(parse_res.distance_m)

        seg.duration_s = None
        seg.norm_distance_m = _compute_norm_distance_m(seg)
        return


def _apply_mob_only(seg, text):
    seg.text = text
    seg.parse_ok = False
    seg.parse_message = ""
    seg.parsed_at = timezone.now()

    seg.duration_s = None
    seg.distance_m = None
    seg.norm_distance_m = None
    seg.reps = 1


def _ensure_zone_in_text(text: str, zone: str) -> str:
    if not text:
        return text
    if re.search(r"\bZ\s*[1-6]\b", text, re.IGNORECASE):
        return text
    return f"{text} Z{zone}"
