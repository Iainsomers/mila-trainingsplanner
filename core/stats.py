from collections import defaultdict
from datetime import date as date_cls
import hashlib
import re

from django.core.cache import cache

from core.zones import ensure_full_zone_dict, DEFAULT_ZONE_SPEED_MPS
from core.models import TrainingSlot
from core.views.common import _week_days


STATS_CACHE_TTL_S = 300  # 5 min; version bump houdt het toch actueel
STATS_VERSION_KEY = "mila:stats:version"
STATS_SCHEMA_VERSION = "v4"


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
_COMPOUND_T_RE = re.compile(r"\b(?:T\s*)?(TM|THM|T4|8|15|3|5|10|800|1500|3000|5000|10000)\b", re.IGNORECASE)


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

                t = (getattr(seg, "t_type", "") or "").strip()
                t_speed = _t_speed_mps(athlete, t) if seg.duration_s else None
                speed = float(t_speed) if t_speed else float(speeds[zone])
                nm = _norm_m_athlete(seg, speed)
                if nm <= 0:
                    continue

                dur = _dur_s(seg, nm, speed)

                t = (getattr(seg, "t_type", "") or "").strip()
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
