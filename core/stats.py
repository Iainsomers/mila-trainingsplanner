from collections import defaultdict
from datetime import date as date_cls
import hashlib
import re

from django.core.cache import cache

from core.zones import ensure_full_zone_dict, DEFAULT_ZONE_SPEED_MPS
from core.models import TrainingSlot, AthleteDayCheck
from core.views.common import _week_days


STATS_CACHE_TTL_S = 300  # 5 min; version bump houdt het toch actueel
STATS_VERSION_KEY = "mila:stats:version"
STATS_SCHEMA_VERSION = "v12"


def _stats_version() -> int:
    v = cache.get(STATS_VERSION_KEY)
    try:
        return int(v or 0)
    except Exception:
        return 0


def _sig(s: str) -> str:
    return hashlib.md5((s or "").encode("utf-8")).hexdigest()


def _athlete_zones_sig(athlete) -> str:
    try:
        z = athlete.get_zone_speed_mps() or {}
    except Exception:
        z = {}

    pr_items = []
    for t in ("800", "1500", "3000", "5000", "10000"):
        pr_items.append((t, getattr(athlete, f"pr_{t}_s", None)))
    pr_items.append(("TM", getattr(athlete, "pr_tm_s", None)))
    pr_items.append(("THM", getattr(athlete, "pr_thm_s", None)))
    pr_items.append(("T4", getattr(athlete, "pr_400_s", None)))

    items = sorted((str(k), str(v)) for k, v in z.items())
    return _sig(repr(items) + "|" + repr(pr_items))


def _group_sig(athletes) -> str:
    parts = []
    for a in athletes or []:
        parts.append(f"{a.id}:{_athlete_zones_sig(a)}")
    return _sig("|".join(parts))


def _empty_zone_bucket(speeds: dict):
    return {z: {"distance_m": 0, "duration_s": 0} for z in speeds.keys()}


def _empty_alt_bucket():
    # Alleen minuten, alleen Z1–Z3
    return {z: {"duration_s": 0} for z in ("1", "2", "3")}


def _empty_t_bucket():
    return {
        "800": {"distance_m": 0, "duration_s": 0},
        "1500": {"distance_m": 0, "duration_s": 0},
        "3000": {"distance_m": 0, "duration_s": 0},
        "5000": {"distance_m": 0, "duration_s": 0},
        "10000": {"distance_m": 0, "duration_s": 0},
        "TM": {"distance_m": 0, "duration_s": 0},
        "THM": {"distance_m": 0, "duration_s": 0},
        "T4": {"distance_m": 0, "duration_s": 0},
    }


def _t_speed_mps(athlete, t_type: str):
    if not athlete or not t_type:
        return None

    field_map = {
        "800": "pr_800_s",
        "1500": "pr_1500_s",
        "3000": "pr_3000_s",
        "5000": "pr_5000_s",
        "10000": "pr_10000_s",
        "TM": "pr_tm_s",
        "THM": "pr_thm_s",
        "T4": "pr_400_s",
    }

    distance_map = {
        "800": 800.0,
        "1500": 1500.0,
        "3000": 3000.0,
        "5000": 5000.0,
        "10000": 10000.0,
        "TM": 42195.0,
        "THM": 21097.5,
        "T4": 400.0,
    }

    field = field_map.get(t_type)
    distance_m = distance_map.get(t_type)
    if not field or not distance_m:
        return None

    pr_s = getattr(athlete, field, None)
    if not pr_s:
        return None

    try:
        return float(distance_m) / float(pr_s)
    except Exception:
        return None


def _norm_m_base(seg, speed_mps: float) -> int:
    nm = int(seg.norm_distance_m or 0)
    if nm > 0:
        return nm

    if seg.distance_m:
        return int(seg.reps or 1) * int(seg.distance_m)

    if seg.duration_s and speed_mps:
        return int(round(int(seg.duration_s) * float(speed_mps)))

    return 0


def _norm_m_athlete(seg, speed_mps: float) -> int:
    if seg.distance_m:
        return int(seg.reps or 1) * int(seg.distance_m)

    if seg.duration_s and speed_mps:
        return int(round(int(seg.duration_s) * float(speed_mps)))

    nm = int(seg.norm_distance_m or 0)
    if nm > 0:
        return nm

    return 0


def _dur_s(seg, nm: int, speed_mps: float) -> int:
    if seg.duration_s:
        return int(seg.duration_s)

    if nm > 0 and speed_mps > 0:
        return int(round(float(nm) / float(speed_mps)))

    return 0




_COMPOUND_SET_RE = re.compile(r"\b(\d+)\s*(?:x|\*|×)\s*\(\s*([^)]+?)\s*\)", re.IGNORECASE)
_COMPOUND_DISTANCE_RE = re.compile(r"\b(\d+(?:[.,]\d+)?)\s*(km|k|m)\b", re.IGNORECASE)
_COMPOUND_ZONE_RE = re.compile(r"\bZ\s*([1-6])\b", re.IGNORECASE)
_COMPOUND_T_RE = re.compile(r"\b(T\s*(?:800|1500|3000|5000|10000|8|15|3|5|10|4)|TM|THM)\b", re.IGNORECASE)


_PROGRESSIVE_ZONE_RE = re.compile(
    r"\bZ\s*([1-6])\s*(?:>|-)\s*Z?\s*([1-6])\b",
    re.IGNORECASE,
)
_PROGRESSIVE_T_RE = re.compile(
    r"\b(T\s*(?:800|1500|3000|5000|10000|15|8|10|5|3|4)|TM|THM)\s*(?:>|-)\s*(T\s*(?:800|1500|3000|5000|10000|15|8|10|5|3|4)|TM|THM)\b",
    re.IGNORECASE,
)


def _progressive_t_types(seg):
    text = (getattr(seg, "text", "") or "").strip()
    match = _PROGRESSIVE_T_RE.search(text)
    if not match:
        return None

    t1 = _normalize_compound_t_type(match.group(1))
    t2 = _normalize_compound_t_type(match.group(2))
    if not t1 or not t2 or t1 == t2:
        return None

    return t1, t2


def _default_zone_for_t_type(t_type: str):
    mapping = {
        "TM": "2",
        "THM": "3",
        "10000": "4",
        "5000": "4",
        "3000": "4",
        "1500": "5",
        "800": "5",
        "T4": "5",
    }
    return mapping.get(str(t_type or "").strip().upper())


def _progressive_zone_loads(seg, speeds: dict, total_nm: int, total_duration_s: int, total_speed_mps: float = None):
    """
    Herkent progressive zones zoals 4*1000m z2>z3.
    Het segment blijft één opgeslagen CORE-regel; alleen stats splitst 50/50.
    """
    text = (getattr(seg, "text", "") or "").strip()
    match = _PROGRESSIVE_ZONE_RE.search(text)
    if not match:
        return None

    z1 = str(match.group(1))
    z2 = str(match.group(2))
    if z1 not in speeds or z2 not in speeds or z1 == z2:
        return None

    total_nm = int(total_nm or 0)
    total_duration_s = int(total_duration_s or 0)

    if total_nm <= 0 and total_duration_s <= 0:
        return None

    if total_duration_s > 0 and total_nm <= 0:
        half_duration_1 = int(round(float(total_duration_s) / 2.0))
        half_duration_2 = int(total_duration_s) - half_duration_1
        loads = []
        for z, dur in ((z1, half_duration_1), (z2, half_duration_2)):
            speed = float(total_speed_mps or speeds[z])
            loads.append({
                "zone": z,
                "distance_m": int(round(float(dur) * speed)),
                "duration_s": int(dur),
            })
        return loads

    half_nm_1 = int(round(float(total_nm) / 2.0))
    half_nm_2 = int(total_nm) - half_nm_1

    loads = []
    for z, nm in ((z1, half_nm_1), (z2, half_nm_2)):
        speed = float(speeds[z])
        loads.append({
            "zone": z,
            "distance_m": int(nm),
            "duration_s": _dur_s(seg, int(nm), speed),
        })

    return loads or None


def _normalize_compound_t_type(value: str):
    v = str(value or "").strip().upper().replace(" ", "")
    mapping = {
        "8": "800",
        "15": "1500",
        "3": "3000",
        "5": "5000",
        "10": "10000",
        "T8": "800",
        "T15": "1500",
        "T3": "3000",
        "T5": "5000",
        "T10": "10000",
        "T800": "800",
        "T1500": "1500",
        "T3000": "3000",
        "T5000": "5000",
        "T10000": "10000",
        "TM": "TM",
        "THM": "THM",
        "T4": "T4",
    }
    return mapping.get(v, v if v in ("800", "1500", "3000", "5000", "10000") else "")


def _compound_distance_to_m(value: str, unit: str) -> int:
    v = float(str(value).replace(",", "."))
    u = str(unit or "").lower()
    if u in ("k", "km"):
        v *= 1000.0
    return int(round(v))


def _compound_rep_loads(seg, default_zone: str, speeds: dict):
    """
    Herkent compound reps zoals: 25*(300m z2-100m z1).
    Geeft losse load-regels terug zonder het opgeslagen segment of de UI-tekst te wijzigen.
    """
    text = (getattr(seg, "text", "") or "").strip()
    match = _COMPOUND_SET_RE.search(text)
    if not match:
        return None

    try:
        outer_reps = int(match.group(1))
    except Exception:
        return None

    inner = match.group(2) or ""
    parts = [p.strip() for p in re.split(r"\s*-\s*", inner) if p.strip()]
    if len(parts) < 2:
        return None

    default_t = (getattr(seg, "t_type", "") or "").strip()
    loads = []

    for part in parts:
        dm = _COMPOUND_DISTANCE_RE.search(part)
        if not dm:
            return None

        dist_m = _compound_distance_to_m(dm.group(1), dm.group(2))

        zm = _COMPOUND_ZONE_RE.search(part)
        part_zone = str(zm.group(1)) if zm else str(default_zone or "")
        if not part_zone or part_zone not in speeds:
            return None

        tm = _COMPOUND_T_RE.search(part)
        part_t = _normalize_compound_t_type(tm.group(1)) if tm else default_t

        nm = int(outer_reps * dist_m)
        speed = float(speeds[part_zone])
        dur = _dur_s(seg, nm, speed)

        loads.append({
            "zone": part_zone,
            "t_type": part_t,
            "distance_m": nm,
            "duration_s": dur,
        })

    return loads or None


_SIMPLE_REPS_DISTANCE_RE = re.compile(r"\b(\d+(?:[.,]\d+)?)\s*(?:x|\*|×)\s*(\d+(?:[.,]\d+)?)\s*(km|k|m)\b", re.IGNORECASE)
_SIMPLE_DISTANCE_RE = re.compile(r"\b(\d+(?:[.,]\d+)?)\s*(km|k|m)\b", re.IGNORECASE)
_SIMPLE_MIN_RE = re.compile(r"\b(\d+(?:[.,]\d+)?)\s*(?:'|min\b)", re.IGNORECASE)
_SIMPLE_TIME_RE = re.compile(r"\b(\d{1,2}):(\d{2})(?::(\d{2}))?\b")


def _text_duration_s(text: str) -> int:
    tm = _SIMPLE_TIME_RE.search(text or "")
    if tm:
        a = int(tm.group(1))
        b = int(tm.group(2))
        c = tm.group(3)
        if c is not None:
            return (a * 3600) + (b * 60) + int(c)
        return (a * 60) + b

    mm = _SIMPLE_MIN_RE.search(text or "")
    if mm:
        try:
            return int(round(float(mm.group(1).replace(",", ".")) * 60.0))
        except Exception:
            return 0

    return 0


def _text_fallback_loads(seg, default_zone: str, speeds: dict, t_speed_func=None):
    """
    Fallback voor athlete-overrides die als tekstsegment zijn opgeslagen.
    De parserstructuur blijft ongemoeid; stats interpreteert alleen de tekst voor totalen.
    """
    text = (getattr(seg, "text", "") or "").strip()
    if not text:
        return None

    default_t = (getattr(seg, "t_type", "") or "").strip()
    chunks = []
    for line in re.split(r"[\n/]+", text):
        line = line.strip()
        if line:
            chunks.append(line)

    loads = []
    for chunk in chunks or [text]:
        zm = _COMPOUND_ZONE_RE.search(chunk)
        zone = str(zm.group(1)) if zm else str(default_zone or "")
        if not zone or zone not in speeds:
            continue

        tm = _COMPOUND_T_RE.search(chunk)
        t_type = _normalize_compound_t_type(tm.group(1)) if tm else default_t

        reps_match = _SIMPLE_REPS_DISTANCE_RE.search(chunk)
        single_match = _SIMPLE_DISTANCE_RE.search(chunk)
        duration_s = _text_duration_s(chunk)

        if reps_match:
            try:
                reps = float(reps_match.group(1).replace(",", "."))
                dist_m = _compound_distance_to_m(reps_match.group(2), reps_match.group(3))
                nm = int(round(reps * dist_m))
            except Exception:
                nm = 0
        elif single_match:
            nm = _compound_distance_to_m(single_match.group(1), single_match.group(2))
        elif duration_s:
            reps_match2 = re.search(r"(\d+)\s*(?:x|\*|×)", chunk)
            reps2 = int(reps_match2.group(1)) if reps_match2 else 1
            total_duration = duration_s * reps2
            t_speed = t_speed_func(t_type) if (t_type and t_speed_func) else None
            speed = float(t_speed) if t_speed else float(speeds[zone])
            nm = int(round(total_duration * speed))
            duration_s = total_duration
        else:
            nm = 0

        if nm <= 0:
            continue

        speed_for_duration = float(speeds[zone])
        dur = int(duration_s) if duration_s else int(round(float(nm) / speed_for_duration))

        loads.append({
            "zone": zone,
            "t_type": t_type,
            "distance_m": nm,
            "duration_s": dur,
        })

    return loads or None

def _apply_progressive_zone_split(seg, zones, speeds, nm, dur, t_totals=None, t="", zone=None):
    progressive_loads = _progressive_zone_loads(seg, speeds, nm, dur, None)
    progressive_t = _progressive_t_types(seg)

    if not progressive_loads:
        if not progressive_t:
            return False

        text = (getattr(seg, "text", "") or "").strip()
        has_explicit_zone = bool(_COMPOUND_ZONE_RE.search(text))

        half_nm_1 = int(round(float(nm or 0) / 2.0))
        half_nm_2 = int(nm or 0) - half_nm_1
        half_dur_1 = int(round(float(dur or 0) / 2.0))
        half_dur_2 = int(dur or 0) - half_dur_1

        z1 = str(zone or getattr(seg, "zone", "") or "")
        z2 = z1
        if not has_explicit_zone:
            z1 = _default_zone_for_t_type(progressive_t[0]) or z1
            z2 = _default_zone_for_t_type(progressive_t[1]) or z2

        if not z1 or not z2 or z1 not in speeds or z2 not in speeds:
            return False

        progressive_loads = [
            {
                "zone": z1,
                "t_type": progressive_t[0],
                "distance_m": half_nm_1,
                "duration_s": half_dur_1,
            },
            {
                "zone": z2,
                "t_type": progressive_t[1],
                "distance_m": half_nm_2,
                "duration_s": half_dur_2,
            },
        ]

    split_count = len(progressive_loads)

    for i, load in enumerate(progressive_loads):
        load_zone = str(load["zone"])
        load_nm = int(load["distance_m"])
        load_dur = int(load["duration_s"])

        if t_totals is not None:
            if progressive_t:
                t_key = (load.get("t_type") or "").strip()
                if not t_key:
                    t_key = progressive_t[0] if i < split_count / 2 else progressive_t[1]
                if t_key in t_totals:
                    t_totals[t_key]["distance_m"] += load_nm
                    t_totals[t_key]["duration_s"] += load_dur
            elif t in t_totals:
                t_totals[t]["distance_m"] += load_nm
                t_totals[t]["duration_s"] += load_dur

        zones[load_zone]["distance_m"] += load_nm
        zones[load_zone]["duration_s"] += load_dur

    return True


def _fetch_week_slots(plan, week_start: date_cls, athlete_ids=None):
    days = _week_days(week_start)

    base_qs = (
        TrainingSlot.objects.filter(
            plan=plan,
            athlete__isnull=True,
            date__in=days,
            slot_index__in=(1, 2),
        )
        .prefetch_related("segments")
    )
    base_map = {}
    for s in base_qs:
        base_map[(s.date, s.slot_index)] = s

    override_map = {}
    if athlete_ids:
        ov_qs = (
            TrainingSlot.objects.filter(
                plan=plan,
                athlete_id__in=list(athlete_ids),
                date__in=days,
                slot_index__in=(1, 2),
            )
            .prefetch_related("segments")
        )
        for s in ov_qs:
            override_map[(s.athlete_id, s.date, s.slot_index)] = s

    return base_map, override_map


def base_week_stats(plan, week_start: date_cls):
    if not plan:
        return {"zones": {}, "race": {}, "alt_zones": _empty_alt_bucket(), "t_totals": _empty_t_bucket()}

    v = _stats_version()
    cache_key = f"mila:stats:base:{STATS_SCHEMA_VERSION}:{plan.id}:{week_start.isoformat()}:v{v}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    speeds = ensure_full_zone_dict(dict(DEFAULT_ZONE_SPEED_MPS))
    zones = _empty_zone_bucket(speeds)
    alt_zones = _empty_alt_bucket()
    race = {"distance_m": 0, "duration_s": 0}
    t_totals = _empty_t_bucket()

    base_map, _ = _fetch_week_slots(plan, week_start, athlete_ids=None)
    days = _week_days(week_start)

    for day in days:
        for slot_index in (1, 2):
            slot = base_map.get((day, slot_index))
            if not slot:
                continue

            for seg in slot.segments.all():
                if seg.type == "MOB":
                    continue

                special = (getattr(seg, "special", "") or "").strip()
                if special == "STRENGTH":
                    continue

                is_race = special in ("RACE", "IMPORTANT_RACE")
                z_raw = (seg.zone or "").strip()
                zone = str(z_raw) if z_raw else ("4" if is_race else "")

                if seg.type == "ALT":
                    if zone in alt_zones and seg.duration_s:
                        alt_zones[zone]["duration_s"] += int(seg.duration_s)
                    continue

                if not zone or zone not in speeds:
                    continue

                compound_loads = _compound_rep_loads(seg, zone, speeds)
                if compound_loads:
                    for load in compound_loads:
                        load_zone = load["zone"]
                        nm = int(load["distance_m"])
                        dur = int(load["duration_s"])
                        t = (load.get("t_type") or "").strip()

                        if t in t_totals:
                            t_totals[t]["distance_m"] += int(nm)
                            t_totals[t]["duration_s"] += int(dur)

                        if is_race:
                            race["distance_m"] += int(nm)
                            race["duration_s"] += int(dur)

                        zones[load_zone]["distance_m"] += int(nm)
                        zones[load_zone]["duration_s"] += int(dur)
                    continue

                speed = float(speeds[zone])
                nm = _norm_m_base(seg, speed)
                if nm <= 0:
                    continue

                dur = _dur_s(seg, nm, speed)

                t = (getattr(seg, "t_type", "") or "").strip()
                if _apply_progressive_zone_split(seg, zones, speeds, nm, dur, t_totals, t, zone):
                    continue

                if t in t_totals:
                    t_totals[t]["distance_m"] += int(nm)
                    t_totals[t]["duration_s"] += int(dur)

                if is_race:
                    race["distance_m"] += int(nm)
                    race["duration_s"] += int(dur)

                zones[zone]["distance_m"] += int(nm)
                zones[zone]["duration_s"] += int(dur)

    out = {"zones": zones, "race": race, "alt_zones": alt_zones, "t_totals": t_totals}
    cache.set(cache_key, out, STATS_CACHE_TTL_S)
    return out


def athlete_week_stats(plan, athlete, week_start: date_cls):
    if not plan or not athlete:
        return {"zones": {}, "race": {}, "alt_zones": _empty_alt_bucket(), "t_totals": _empty_t_bucket()}

    v = _stats_version()
    zones_sig = _athlete_zones_sig(athlete)
    cache_key = f"mila:stats:athlete:{STATS_SCHEMA_VERSION}:{plan.id}:{athlete.id}:{week_start.isoformat()}:{zones_sig}:v{v}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    speeds = ensure_full_zone_dict(athlete.get_zone_speed_mps())
    zones = _empty_zone_bucket(speeds)
    alt_zones = _empty_alt_bucket()
    race = {"distance_m": 0, "duration_s": 0}
    t_totals = _empty_t_bucket()

    base_map, override_map = _fetch_week_slots(plan, week_start, athlete_ids=[athlete.id])
    days = _week_days(week_start)

    for day in days:
        for slot_index in (1, 2):
            check = AthleteDayCheck.objects.filter(
                athlete=athlete,
                date=day,
                slot_index=slot_index
            ).first()

            if check and check.status == AthleteDayCheck.STATUS_NOT_DONE:
                continue

            slot = override_map.get((athlete.id, day, slot_index)) or base_map.get((day, slot_index))
            if not slot:
                continue

            for seg in slot.segments.all():
                if seg.type == "MOB":
                    continue

                special = (getattr(seg, "special", "") or "").strip()
                if special == "STRENGTH":
                    continue

                is_race = special in ("RACE", "IMPORTANT_RACE")
                z_raw = (seg.zone or "").strip()
                zone = str(z_raw) if z_raw else ("4" if is_race else "")

                if seg.type == "ALT":
                    if zone in alt_zones:
                        alt_duration_s = int(seg.duration_s or 0)
                        if alt_duration_s <= 0:
                            alt_duration_s = _text_duration_s(getattr(seg, "text", "") or "")
                            reps_match = re.search(r"(\d+)\s*(?:x|\*|×)", getattr(seg, "text", "") or "")
                            if reps_match and alt_duration_s > 0:
                                alt_duration_s *= int(reps_match.group(1))
                        if alt_duration_s > 0:
                            alt_zones[zone]["duration_s"] += int(alt_duration_s)
                    continue

                if not zone or zone not in speeds:
                    continue

                compound_loads = _compound_rep_loads(seg, zone, speeds)
                if compound_loads:
                    for load in compound_loads:
                        load_zone = load["zone"]
                        nm = int(load["distance_m"])
                        dur = int(load["duration_s"])
                        t = (load.get("t_type") or "").strip()

                        if t in t_totals:
                            t_totals[t]["distance_m"] += int(nm)
                            t_totals[t]["duration_s"] += int(dur)

                        if is_race:
                            race["distance_m"] += int(nm)
                            race["duration_s"] += int(dur)

                        zones[load_zone]["distance_m"] += int(nm)
                        zones[load_zone]["duration_s"] += int(dur)
                    continue

                t = (getattr(seg, "t_type", "") or "").strip()
                t_speed = _t_speed_mps(athlete, t) if seg.duration_s else None
                speed = float(t_speed) if t_speed else float(speeds[zone])
                nm = _norm_m_athlete(seg, speed)
                if nm <= 0:
                    fallback_loads = _text_fallback_loads(seg, zone, speeds, lambda tt: _t_speed_mps(athlete, tt))
                    if fallback_loads:
                        for load in fallback_loads:
                            load_zone = load["zone"]
                            load_nm = int(load["distance_m"])
                            load_dur = int(load["duration_s"])
                            load_t = (load.get("t_type") or "").strip()

                            if load_t in t_totals:
                                t_totals[load_t]["distance_m"] += int(load_nm)
                                t_totals[load_t]["duration_s"] += int(load_dur)

                            if is_race:
                                race["distance_m"] += int(load_nm)
                                race["duration_s"] += int(load_dur)

                            zones[load_zone]["distance_m"] += int(load_nm)
                            zones[load_zone]["duration_s"] += int(load_dur)
                        continue

                    continue

                dur = _dur_s(seg, nm, speed)

                t = (getattr(seg, "t_type", "") or "").strip()
                if _apply_progressive_zone_split(seg, zones, speeds, nm, dur, t_totals, t, zone):
                    continue

                if t in t_totals:
                    t_totals[t]["distance_m"] += int(nm)
                    t_totals[t]["duration_s"] += int(dur)

                if is_race:
                    race["distance_m"] += int(nm)
                    race["duration_s"] += int(dur)

                zones[zone]["distance_m"] += int(nm)
                zones[zone]["duration_s"] += int(dur)

    out = {"zones": zones, "race": race, "alt_zones": alt_zones, "t_totals": t_totals}
    cache.set(cache_key, out, STATS_CACHE_TTL_S)
    return out


def group_week_stats(plan, athletes, week_start: date_cls):
    athletes = list(athletes or [])
    if not plan or not athletes:
        return {"zones": {}, "race": {}, "alt_zones": _empty_alt_bucket(), "t_totals": _empty_t_bucket()}

    v = _stats_version()
    gsig = _group_sig(athletes)
    cache_key = f"mila:stats:group:{STATS_SCHEMA_VERSION}:{plan.id}:{week_start.isoformat()}:{gsig}:v{v}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    zone_speed_sums = defaultdict(float)
    zone_speed_counts = defaultdict(int)
    for a in athletes:
        speeds = ensure_full_zone_dict(a.get_zone_speed_mps())
        for z in ("1", "2", "3", "4", "5", "6"):
            try:
                zone_speed_sums[z] += float(speeds[z])
                zone_speed_counts[z] += 1
            except Exception:
                pass

    avg_zone_speeds = {}
    for z in ("1", "2", "3", "4", "5", "6"):
        if zone_speed_counts[z] > 0:
            avg_zone_speeds[z] = zone_speed_sums[z] / zone_speed_counts[z]
        else:
            avg_zone_speeds[z] = float(DEFAULT_ZONE_SPEED_MPS[z])

    zones = _empty_zone_bucket(avg_zone_speeds)
    alt_zones = _empty_alt_bucket()
    race = {"distance_m": 0, "duration_s": 0}
    t_totals = _empty_t_bucket()

    def _avg_t_speed(t_type: str):
        vals = []
        for a in athletes:
            s = _t_speed_mps(a, t_type)
            if s:
                vals.append(float(s))
        if vals:
            return sum(vals) / float(len(vals))
        return None

    base_map, _ = _fetch_week_slots(plan, week_start, athlete_ids=None)
    days = _week_days(week_start)

    for day in days:
        for slot_index in (1, 2):
            slot = base_map.get((day, slot_index))
            if not slot:
                continue

            for seg in slot.segments.all():
                if seg.type == "MOB":
                    continue

                special = (getattr(seg, "special", "") or "").strip()
                if special == "STRENGTH":
                    continue

                is_race = special in ("RACE", "IMPORTANT_RACE")
                z_raw = (seg.zone or "").strip()
                zone = str(z_raw) if z_raw else ("4" if is_race else "")

                if seg.type == "ALT":
                    if zone in alt_zones and seg.duration_s:
                        alt_zones[zone]["duration_s"] += int(seg.duration_s)
                    continue

                if not zone or zone not in avg_zone_speeds:
                    continue

                compound_loads = _compound_rep_loads(seg, zone, avg_zone_speeds)
                if compound_loads:
                    for load in compound_loads:
                        load_zone = load["zone"]
                        nm = int(load["distance_m"])
                        dur = int(load["duration_s"])
                        t = (load.get("t_type") or "").strip()

                        if t in t_totals:
                            t_totals[t]["distance_m"] += int(nm)
                            t_totals[t]["duration_s"] += int(dur)

                        if is_race:
                            race["distance_m"] += int(nm)
                            race["duration_s"] += int(dur)

                        zones[load_zone]["distance_m"] += int(nm)
                        zones[load_zone]["duration_s"] += int(dur)
                    continue

                t = (getattr(seg, "t_type", "") or "").strip()
                t_speed = _avg_t_speed(t) if seg.duration_s else None
                speed = float(t_speed) if t_speed else float(avg_zone_speeds[zone])

                nm = _norm_m_athlete(seg, speed)
                if nm <= 0:
                    continue

                dur = _dur_s(seg, nm, speed)

                if _apply_progressive_zone_split(seg, zones, avg_zone_speeds, nm, dur, t_totals, t, zone):
                    continue

                if t in t_totals:
                    t_totals[t]["distance_m"] += int(nm)
                    t_totals[t]["duration_s"] += int(dur)

                if is_race:
                    race["distance_m"] += int(nm)
                    race["duration_s"] += int(dur)

                zones[zone]["distance_m"] += int(nm)
                zones[zone]["duration_s"] += int(dur)

    out = {"zones": zones, "race": race, "alt_zones": alt_zones, "t_totals": t_totals}
    cache.set(cache_key, out, STATS_CACHE_TTL_S)
    return out
