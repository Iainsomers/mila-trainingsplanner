"""Conservative structure recognition; measured lap facts are never rewritten."""
import math
from statistics import median


def kilometre_split_timed_intervals(laps, zone_for_lap):
    """Recognize equal timed efforts split into two kilometre laps + remainder."""
    if not isinstance(laps, list):
        return None
    try:
        rows = [(float(lap['distanceMeters']), float(lap['durationMillis']) / 1000) for lap in laps]
    except (KeyError, TypeError, ValueError):
        return None
    if any(not math.isfinite(m + s) or m <= 0 or s <= 0 for m, s in rows):
        return None
    blocks, recoveries = [], []
    cursor = 0
    while cursor + 2 < len(rows):
        block = rows[cursor:cursor + 3]
        if not (all(950 <= m <= 1050 for m, _ in block[:2]) and 250 <= block[2][0] <= 600):
            return None
        indices = list(range(cursor, cursor + 3))
        blocks.append(indices)
        speed = sum(m for m, _ in block) / sum(s for _, s in block)
        cursor += 3
        if cursor == len(rows):
            break
        m, s = rows[cursor]
        if cursor == len(rows) - 1 and m <= 50 and s <= 30:
            cursor += 1
            break  # final stop remainder
        if not (100 <= m <= 500 and 60 <= s <= 180 and speed >= 1.2 * m / s
                and zone_for_lap(laps[cursor]) in {'Z1', '', 'NA'}):
            return None
        recoveries.append(s)
        cursor += 1
    if cursor != len(rows) or len(blocks) < 3 or len(recoveries) != len(blocks) - 1:
        return None
    durations = [sum(rows[i][1] for i in block) for block in blocks]
    minutes = int(math.floor(median(durations) / 60 + .5))
    if minutes < 5 or any(abs(s - minutes * 60) > 5 for s in durations):
        return None
    zones = sorted({zone_for_lap(laps[i]) for block in blocks for i in block} & {'Z1','Z2','Z3','Z4','Z5'})
    zone = (' ' + (zones[0] if len(zones) == 1 else zones[0] + '>' + zones[-1])) if zones else ''
    recovery = int(math.floor(median(recoveries) + .5))
    main = f"{len(blocks)}×{minutes}'{zone} p{recovery}"
    return {'description': f'WU: none · Main: {main} · CD: none', 'main': main,
            'blocks': blocks, 'minutes': minutes, 'cooldown_start': len(rows)}


def mixed_short_repetitions(laps, zone_for_lap):
    """Keep short work/recovery laps visible after an easy lead-in.

    Relative speed establishes work; a kilometre warmup must not dominate
    recognition. Never infer missing repetitions or treat stopped time as work.
    """
    if not isinstance(laps, list):
        return None
    rows = []
    for lap in laps:
        try:
            m, s = float(lap['distanceMeters']), float(lap['durationMillis']) / 1000
        except (KeyError, TypeError, ValueError):
            return None
        if not math.isfinite(m + s) or m < 0 or s <= 0:
            return None
        rows.append((m, s))
    work = []
    for i, (m, s) in enumerate(rows[:-1]):
        rm, rs = rows[i + 1]
        if (25 <= m <= 250 and 3 <= s <= 60 and rs >= 30
                and (rm <= 300 or (i == len(rows) - 2 and rm >= 500)) and m / s >= 2.5 and m / s >= 1.5 * rm / rs):
            work.append(i)
    if len(work) < 4:
        return None
    # Every intervening lap must be recovery: no hidden unanalysed work block.
    if any(m > 300 or (m / s >= 2.5 and s < 60)
           for i, (m, s) in enumerate(rows[work[0]:work[-1] + 1], work[0]) if i not in work):
        return None
    prefix = rows[:work[0]]
    long_prefix = [i for i, (m, _) in enumerate(prefix) if m >= 800]
    # A separately recorded Main has no warmup prefix. Only accept a fully
    # alternating work/recovery recording here; retain ordinary 50m rounding
    # instead of the lead-in branch's GPS cluster correction.
    main_only = not prefix and work == list(range(0, len(rows), 2)) and len(rows) == len(work) * 2
    if not main_only and (not long_prefix or long_prefix[0] != 0):
        return None
    if any(zone_for_lap(laps[i]) not in {'Z1', '', 'NA'} for i in range(work[0])):
        return None
    # Similar automatic splits belong to one warmup. Distinct long laps after
    # one warmup remain separate Main work, even if elapsed pace includes stops.
    long_distances = [rows[i][0] for i in long_prefix]
    wu_end = 0 if main_only else (work[0] if max(long_distances) <= min(long_distances) * 1.25 else 1)
    def distance_label(m):
        return int(math.floor(m / 50 + .5) * 50)
    def zone_label(indices):
        zones = sorted({zone_for_lap(laps[i]) for i in indices} & {'Z1','Z2','Z3','Z4','Z5'})
        return (' ' + (zones[0] if len(zones) == 1 else zones[0] + '>' + zones[-1])) if zones else ''
    main = [f'{distance_label(rows[i][0])} m{zone_label([i])}'
            for i in range(wu_end, work[0]) if rows[i][0] >= 800]
    nominal_by_index = {i: distance_label(rows[i][0]) for i in work}
    # GPS can put alternating 200m reps just below the 175m rounding boundary.
    # Only two clearly separated repeated distance clusters justify correcting
    # nominal labels; isolated outliers do not establish a new rep distance.
    longer = sorted((rows[i][0], i) for i in work if rows[i][0] >= 100)
    gaps = [(longer[j + 1][0] - longer[j][0], j + 1) for j in range(1, len(longer) - 2)]
    gap, split = max(gaps, default=(0, 0))
    if gap >= 15 and not main_only:
        clusters = [longer[:split], longer[split:]]
        targets = [distance_label(cluster[min(len(cluster) - 1, int(len(cluster) * .75))][0]) for cluster in clusters]
        if targets[1] - targets[0] >= 50:
            for cluster, target in zip(clusters, targets):
                for _, i in cluster:
                    nominal_by_index[i] = target
    grouped = {}
    for i in work:
        grouped.setdefault(nominal_by_index[i], []).append(i)
    groups = list(grouped.values())
    for group in groups:
        nominal = nominal_by_index[group[0]]
        label = (f'{len(group)}×' if len(group) > 1 else '') + f'{nominal} m' + zone_label(group)
        # Use the recovery immediately following each work lap; a separate
        # near-stationary lap must not inflate its typical rep recovery.
        recovery = [rows[i + 1][1] for i in group if rows[i + 1][1] < 180]
        if recovery:
            label += f' p{int(math.floor(median(recovery) + .5))}'
        main.append(label)
    cooldown_start = work[-1] + 1
    tail = rows[cooldown_start:]
    cd_m = sum(m for m, _ in tail)
    # Keep one clear trailing run as CD; short final recoveries alone are not CD.
    has_cd = any(m >= 500 for m, _ in tail) and all(zone_for_lap(laps[i]) in {'Z1', '', 'NA'}
                  for i in range(cooldown_start, len(rows)))
    wu = (f'{distance_label(sum(m for m, _ in rows[:wu_end]))} m' + zone_label(list(range(wu_end)))) if wu_end else 'none'
    cd = f'{distance_label(cd_m)} m' + zone_label(list(range(cooldown_start, len(rows)))) if has_cd else ''
    main_text = ' + '.join(main)
    return {'description': f'WU: {wu} · Main: {main_text} · CD: {cd or "none"}',
            'main': main_text, 'wu_end': wu_end, 'work_indices': work, 'work_distances': nominal_by_index,
            'cooldown_start': cooldown_start if has_cd else len(rows)}


def continuous_kilometre_run(laps, zone_for_lap):
    """Regular 500 m / kilometre splits alone do not establish repetitions."""
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
    step = min((500, 1000), key=lambda value: abs(median(m for m, _, _ in rows[:-1]) - value))
    lower, upper = step * 0.95, step * 1.05
    full = rows[:-1] if rows[-1][0] < lower else rows
    if len(full) < 3 or any(not lower <= m <= upper for m, _, _ in full) or rows[-1][0] > upper:
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
