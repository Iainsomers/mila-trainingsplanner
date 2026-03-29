from collections import defaultdict
from datetime import date as date_cls
import hashlib

from django.core.cache import cache

from core.zones import ensure_full_zone_dict, DEFAULT_ZONE_SPEED_MPS
from core.models import TrainingSlot
from core.views.common import _week_days


STATS_CACHE_TTL_S = 300  # 5 min; version bump houdt het toch actueel
STATS_VERSION_KEY = "mila:stats:version"
STATS_SCHEMA_VERSION = "v2"


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
    items = sorted((str(k), str(v)) for k, v in z.items())
    return _sig(repr(items))


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
    }


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

                # ALT: alleen minuten, alleen Z1–Z3
                if seg.type == "ALT":
                    if zone in alt_zones and seg.duration_s:
                        alt_zones[zone]["duration_s"] += int(seg.duration_s)
                    continue

                if not zone or zone not in speeds:
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

                bucket = race if is_race else zones[zone]
                bucket["distance_m"] += int(nm)
                bucket["duration_s"] += int(dur)

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

                speed = float(speeds[zone])
                nm = _norm_m_athlete(seg, speed)
                if nm <= 0:
                    continue

                dur = _dur_s(seg, nm, speed)

                t = (getattr(seg, "t_type", "") or "").strip()
                if t in t_totals:
                    t_totals[t]["distance_m"] += int(nm)
                    t_totals[t]["duration_s"] += int(dur)

                bucket = race if is_race else zones[zone]
                bucket["distance_m"] += int(nm)
                bucket["duration_s"] += int(dur)

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

    athlete_ids = [a.id for a in athletes]
    base_map, override_map = _fetch_week_slots(plan, week_start, athlete_ids=athlete_ids)
    days = _week_days(week_start)

    zones_sum = defaultdict(lambda: {"distance_m": 0, "duration_s": 0})
    alt_sum = defaultdict(lambda: {"duration_s": 0})
    race_sum = {"distance_m": 0, "duration_s": 0}
    t_sum = _empty_t_bucket()

    for a in athletes:
        speeds = ensure_full_zone_dict(a.get_zone_speed_mps())
        zones_a = _empty_zone_bucket(speeds)
        alt_a = _empty_alt_bucket()
        race_a = {"distance_m": 0, "duration_s": 0}
        t_a = _empty_t_bucket()

        for day in days:
            for slot_index in (1, 2):
                slot = override_map.get((a.id, day, slot_index)) or base_map.get((day, slot_index))
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
                        if zone in alt_a and seg.duration_s:
                            alt_a[zone]["duration_s"] += int(seg.duration_s)
                        continue

                    if not zone or zone not in speeds:
                        continue

                    speed = float(speeds[zone])
                    nm = _norm_m_athlete(seg, speed)
                    if nm <= 0:
                        continue

                    dur = _dur_s(seg, nm, speed)

                    t = (getattr(seg, "t_type", "") or "").strip()
                    if t in t_a:
                        t_a[t]["distance_m"] += int(nm)
                        t_a[t]["duration_s"] += int(dur)

                    bucket = race_a if is_race else zones_a[zone]
                    bucket["distance_m"] += int(nm)
                    bucket["duration_s"] += int(dur)

        for z, vals in zones_a.items():
            zones_sum[str(z)]["distance_m"] += int(vals["distance_m"])
            zones_sum[str(z)]["duration_s"] += int(vals["duration_s"])

        for z, vals in alt_a.items():
            alt_sum[str(z)]["duration_s"] += int(vals["duration_s"])

        for t, vals in t_a.items():
            t_sum[t]["distance_m"] += int(vals["distance_m"])
            t_sum[t]["duration_s"] += int(vals["duration_s"])

        race_sum["distance_m"] += int(race_a["distance_m"])
        race_sum["duration_s"] += int(race_a["duration_s"])

    n = len(athletes)
    zones_avg = {
        z: {
            "distance_m": int(round(vals["distance_m"] / n)),
            "duration_s": int(round(vals["duration_s"] / n)),
        }
        for z, vals in zones_sum.items()
    }

    # Zorg dat Z1–Z3 altijd bestaan (ook als 0)
    alt_avg = _empty_alt_bucket()
    for z in ("1", "2", "3"):
        alt_avg[z]["duration_s"] = int(round(int(alt_sum.get(z, {}).get("duration_s", 0)) / n))

    race_avg = {
        "distance_m": int(round(race_sum["distance_m"] / n)),
        "duration_s": int(round(race_sum["duration_s"] / n)),
    }

    t_avg = _empty_t_bucket()
    for t in t_avg.keys():
        t_avg[t]["distance_m"] = int(round(int(t_sum.get(t, {}).get("distance_m", 0)) / n))
        t_avg[t]["duration_s"] = int(round(int(t_sum.get(t, {}).get("duration_s", 0)) / n))

    out = {"zones": zones_avg, "race": race_avg, "alt_zones": alt_avg, "t_totals": t_avg}
    cache.set(cache_key, out, STATS_CACHE_TTL_S)
    return out
