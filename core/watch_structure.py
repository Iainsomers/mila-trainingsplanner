"""Conservative structure recognition; measured lap facts are never rewritten."""
import math
from statistics import median


def continuous_kilometre_run(laps, zone_for_lap):
    """Kilometre splits need additional work/recovery evidence to imply reps."""
    if not isinstance(laps, list) or len(laps) < 3:
        return None
    rows = []
    for lap in laps:
        try:
            meters, seconds = float(lap["distanceMeters"]), float(lap["durationMillis"]) / 1000
            pause = float(lap.get("pausedDurationMillis") or 0) / 1000
        except (TypeError, KeyError, ValueError):
            return None
        if not math.isfinite(meters + seconds + pause) or meters <= 0 or seconds <= 0:
            return None
        rows.append((meters, seconds, pause))
    full = rows[:-1] if rows[-1][0] < 950 else rows
    if len(full) < 3 or any(not 950 <= m <= 1050 for m, _, _ in full) or rows[-1][0] > 1050:
        return None
    threshold = max(3, math.ceil(len(full) * 0.25))
    if sum(p >= 15 for _, _, p in full) >= threshold:
        return None
    paces = sorted(s / m for m, s, _ in full)
    running_pace = median(paces[:max(1, (len(paces) + 1) // 2)])
    if sum(s / m >= running_pace * 1.6 for m, s, _ in full) >= threshold:
        return None
    if any(lap.get("lapIntensity") in {1, 4, 5} for lap in laps):
        return None  # FIT explicitly marks rest, recovery or interval laps.
    zones = {}
    for lap, (meters, _, _) in zip(laps, rows):
        zone = zone_for_lap(lap)
        if zone in {"Z1", "Z2", "Z3", "Z4", "Z5"}:
            zones[zone] = zones.get(zone, 0) + meters
    zone = max(zones, key=zones.get) if zones else ""
    distance = math.floor(sum(m for m, _, _ in rows) / 50 + 0.5) * 50
    return f"WU: none · Main: {distance} m{(' ' + zone) if zone else ''} · CD: none"


def short_sets_and_continuous(laps, zone_for_lap):
    """Recognize repeated short sets followed by consistently split running loops.

    Require alternating work/recovery, equal sets separated by long recovery,
    and at least two kilometre/remainder pairs at a consistent running speed.
    A single anomalous short rep may inherit its set's distance, never its facts.
    """
    rows = []
    for lap in laps or []:
        try:
            distance = float(lap["distanceMeters"])
            seconds = float(lap["durationMillis"]) / 1000
        except (KeyError, TypeError, ValueError):
            return None
        if not math.isfinite(distance + seconds) or distance <= 0 or seconds <= 0:
            return None
        rows.append((distance, seconds))
    sets, work, recoveries = [], [], []
    position = 0
    while position + 1 < len(rows):
        distance, seconds = rows[position]
        recovery_m, recovery_s = rows[position + 1]
        if not (60 <= distance <= 125 and 10 <= seconds <= 30
                and recovery_m <= 160 and 30 <= recovery_s <= 360
                and distance / seconds >= 1.3 * recovery_m / recovery_s):
            break
        work.append(distance)
        if recovery_s >= 120:
            if len(work) < 3:
                return None
            sets.append(work)
            work = []
        elif recovery_s <= 65:
            recoveries.append(recovery_s)
        else:
            return None
        position += 2
    if work or len(sets) < 2 or len({len(group) for group in sets}) != 1:
        return None
    work_distances = [value for group in sets for value in group]
    nominal = round(median(work_distances) / 50) * 50
    if nominal != 100 or sum(abs(value - nominal) > 25 for value in work_distances) > 1:
        return None
    if not recoveries:
        return None
    # Auto-kilometre laps plus a manual lap at the end of each longer loop.
    continuous_start = position
    loops, speeds = [], []
    while position + 1 < len(rows):
        first_m, first_s = rows[position]
        last_m, last_s = rows[position + 1]
        first_speed, last_speed = first_m / first_s, last_m / last_s
        if not (950 <= first_m <= 1050 and 175 <= last_m <= 375
                and max(first_speed, last_speed) <= 1.15 * min(first_speed, last_speed)):
            break
        if speeds and abs(first_speed / median(speeds) - 1) > 0.15:
            break
        loops.append(first_m + last_m)
        speeds.extend([first_speed, last_speed])
        position += 2
    if len(loops) < 2:
        return None
    loop_m = round(median(loops) / 250) * 250
    if any(abs(value - loop_m) > loop_m * 0.05 for value in loops):
        return None
    cooldown_start = position
    tail = rows[position:]
    if tail:
        # A pronounced slowdown starts CD; subsequent Z2 laps may belong to it.
        if (sum(value[0] for value in tail) < 500 or tail[0][0] < 500
                or tail[0][0] / tail[0][1] > median(speeds) / 1.25
                or any(m / s > median(speeds) * 1.08 for m, s in tail)):
            return None
    zone_distances = {}
    for lap, (meters, _) in zip(laps[continuous_start:cooldown_start], rows[continuous_start:cooldown_start]):
        zone = zone_for_lap(lap)
        if zone in {"Z1", "Z2", "Z3", "Z4", "Z5"}:
            zone_distances[zone] = zone_distances.get(zone, 0) + meters
    zone = max(zone_distances, key=zone_distances.get) if zone_distances else ""
    # Only the even-positioned work laps contribute to the short-rep range.
    # Slow recoveries and the continuous block must not dilute these zones.
    work_zones = {zone_for_lap(lap) for lap in laps[:continuous_start:2]}
    work_zones = sorted(value.lower() for value in work_zones
                        if value in {"Z1", "Z2", "Z3", "Z4", "Z5"})
    work_zone = ""
    if work_zones:
        work_zone = " " + (work_zones[0] if len(work_zones) == 1
                            else f"{work_zones[0]}>{work_zones[-1]}")
    recovery = int(math.floor(median(recoveries) / 5 + 0.5) * 5)
    main = f"{len(sets)}*({len(sets[0])}*{nominal}m{work_zone}) p{recovery}//{len(loops) * loop_m}m"
    if zone:
        main += " " + zone.lower()
    cd = f"{round(sum(m for m, _ in tail) / 100) * 100}m" if tail else ""
    return {"description": f"WU: none · Main: {main} · CD: {cd or 'none'}",
            "cooldown_start": cooldown_start, "main": main, "cd": cd}
