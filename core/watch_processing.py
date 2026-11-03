"""Persisted, display-ready output derived from a slot's raw Watch laps."""

import re
from core.watch_hr import tail_hr


WATCH_SOURCES = {"watch_a", "watch_b", "watch_c", "watch_d"}


def is_walking_load(meters, seconds):
    """Measured pace strictly slower than 10:00/km is walking, not running."""
    return meters > 0 and seconds > meters * 0.6


def align_watch_loads(loads, wu_text="", cd_text=""):
    """Match explicit WU/CD to measured boundary laps, never add distance."""
    result = [dict(load) for load in loads if isinstance(load, dict)]
    for kind, text, reverse in (("WU", wu_text, False), ("CD", cd_text, True)):
        match = re.fullmatch(r"\s*(\d+(?:\.\d+)?)\s*m(?:\s+z[1-6])?(?:\s*\([^)]*\))?\s*", str(text), re.I)
        if not match:
            if not str(text).strip():
                for load in result:
                    if load.get("segment") == kind:
                        load["segment"] = "CORE"
            continue
        target = float(match.group(1))
        total, candidates = 0, []
        indices = list(range(len(result)))
        if reverse:
            indices.reverse()
        for index in indices:
            try:
                total += float(result[index].get("meters") or 0)
            except (TypeError, ValueError):
                break
            candidates.append((abs(total - target), index))
            if total > target + 75:
                break
        if not candidates:
            continue
        error, boundary = min(candidates)
        if error > 75:
            continue
        for index, load in enumerate(result):
            if load.get("segment") == kind:
                load["segment"] = "CORE"
            if (index >= boundary if reverse else index <= boundary):
                load["segment"] = kind
    return result


def preserve_long_main_laps(fields, loads):
    """Do not silently omit long Main laps when only short reps were described."""
    fields = dict(fields)
    main = str(fields.get("main") or "")
    distances = re.findall(r"(\d+(?:\.\d+)?)\s*m\b", main, re.I)
    if not distances or any(float(distance) > 800 for distance in distances):
        return fields
    # Only restore leading long work before the short rep sequence; trailing
    # long laps could be a cooldown and need their own structural evidence.
    additions = []
    for load in loads:
        if load.get("segment") != "CORE":
            continue
        meters = float(load.get("meters") or 0)
        seconds = float(load.get("seconds") or 0)
        if meters >= 1000:
            nominal = int((meters + 25) // 50 * 50)
            zone = str(load.get("zone") or "")
            additions.append(f"{nominal} m" + (f" Z{zone}" if zone in {"1", "2", "3", "4", "5", "6"} else ""))
        elif meters >= 25 and seconds > 0 and meters / seconds >= 2.5:
            break
    if additions:
        fields["main"] = " + ".join(additions + [main])
    return fields


def _block_average_hr(loads):
    """Time-weighted lap averages; incomplete HR coverage remains unknown."""
    try:
        values = [(float(load["average_hr"]), float(load["seconds"])) for load in loads]
    except (KeyError, TypeError, ValueError):
        return None
    if not values or any(hr <= 0 or seconds <= 0 for hr, seconds in values):
        return None
    return round(sum(hr * seconds for hr, seconds in values) / sum(seconds for _, seconds in values))


def structured_segment_loads(segment, raw_loads):
    """Assign measured short-set laps and the following continuous block.

    Reconstruct from existing raw loads too, so saved Watch slots need no
    reimport. Return None when this conservative structure does not apply.
    """
    from core.watch_structure import short_sets_and_continuous, continuous_kilometre_run
    if str(getattr(segment, "type", "")).upper() != "CORE":
        return None
    loads = [load for load in raw_loads if isinstance(load, dict) and not load.get("combined_outer")
             and str(load.get("segment") or "CORE").upper() in {"CORE", "CD"}]
    try:
        laps = [{"distanceMeters": float(load.get("meters") or 0),
                 "durationMillis": float(load.get("seconds") or 0) * 1000,
                 "zone": str(load.get("pace_zone", load.get("zone")) or "")} for load in loads]
    except (TypeError, ValueError):
        return None
    # A nominal rep may consist of two uninterrupted auto-laps. Reuse the
    # conservative work/work/recovery check used by Garmin C's description.
    text = str(getattr(segment, "text", "") or "")
    match = re.fullmatch(r"\s*(\d+)\s*[x×*]\s*(\d+)\s*m\b.*", text, re.IGNORECASE)
    if match:
        count, distance = map(int, match.groups())
        if count >= 3 and 700 <= distance <= 1600:
            from core.views.coach import _watch_c_merge_half_laps_from_raw
            half = distance // 2
            verified = _watch_c_merge_half_laps_from_raw(f"{count * 2}×{half} m Z1", laps)
            if verified.startswith(f"{count}×{distance} m "):
                work = [load for load in loads if abs(float(load["meters"]) - half) <= max(75, half * .12)]
                return [{"matched_rep": True,
                         "meters": sum(float(item["meters"]) for item in work[i:i+2]),
                         "seconds": sum(float(item["seconds"]) for item in work[i:i+2]),
                         "average_hr": _block_average_hr(work[i:i+2]),
                         "hr_tail": tail_hr(work[i:i+2]),
                         "average_hr_last_15": work[i+1].get("average_hr_last_15")}
                        for i in range(0, len(work), 2)]
    from core.watch_alternatives import long_interval_options
    alternatives = long_interval_options(laps, lambda lap: "Z" + lap["zone"])
    if alternatives:
        match_time = re.match(r"^\s*(\d+)\s*[x×*]\s*(\d+)\s*['′]", text)
        if match_time:
            for group in alternatives["groups"]:
                minutes = round(sum(float(loads[i]["seconds"]) for i in group) / len(group) / 60)
                if len(group) == int(match_time.group(1)) and minutes == int(match_time.group(2)):
                    return [dict(loads[i], matched_rep=True) for i in group]
    from core.watch_structure import kilometre_split_timed_intervals
    timed = kilometre_split_timed_intervals(laps, lambda lap: "Z" + lap["zone"])
    if timed and re.match(rf"^\s*{len(timed['blocks'])}\s*[x×*]\s*{timed['minutes']}\s*['′]", text):
        output = []
        for indices in timed["blocks"]:
            block = [loads[i] for i in indices]
            output.append({"matched_rep": True, "meters": sum(float(load["meters"]) for load in block),
                "seconds": sum(float(load["seconds"]) for load in block),
                "average_hr": _block_average_hr(block), "hr_tail": tail_hr(block),
                "average_hr_last_15": block[-1].get("average_hr_last_15")})
        return output
    structure = short_sets_and_continuous(laps, lambda lap: "Z" + lap["zone"])
    if not structure:
        continuous = continuous_kilometre_run(laps, lambda lap: "Z" + lap["zone"])
        if continuous:
            total = int(continuous.split("Main: ")[1].split(" m")[0])
            text = str(getattr(segment, "text", "") or "")
            if re.fullmatch(rf"\s*{total}\s*m(?:\s+Z[1-5])?\s*", text, re.IGNORECASE):
                return [{"matched_rep": True, "meters": sum(lap["distanceMeters"] for lap in laps),
                         "seconds": sum(lap["durationMillis"] for lap in laps) / 1000,
                         "average_hr": _block_average_hr(loads), "hr_tail": tail_hr(loads),
                         "split_loads": loads}]
        return None
    text = str(getattr(segment, "text", "") or "")
    continuous_m = int(structure["main"].split("//")[1].split("m")[0])
    if re.search(r"\b100\s*m\b", text, re.IGNORECASE):
        # Work/recovery pairs precede the first long lap.
        end = next(index for index, lap in enumerate(laps) if lap["distanceMeters"] >= 950)
        return [dict(load, matched_rep=True) for load in loads[:end:2]]
    if re.search(rf"\b{continuous_m}\s*m\b", text, re.IGNORECASE):
        start = next(index for index, lap in enumerate(laps) if lap["distanceMeters"] >= 950)
        block = loads[start:structure["cooldown_start"]]
        return [{"matched_rep": True, "meters": sum(float(load["meters"]) for load in block),
                 "seconds": sum(float(load["seconds"]) for load in block),
                 "average_hr": _block_average_hr(block), "hr_tail": tail_hr(block),
                 "average_hr_last_15": block[-1].get("average_hr_last_15")
                    if float(block[-1]["seconds"]) >= 15 else None}]
    return None


def processed_main_reps(slot):
    """Match raw Main laps to planned rep distances without changing raw loads.

    Recovery laps normally have a different distance from the planned reps, so
    they are left out. A distance tolerance accommodates GPS drift on short
    reps while still keeping (for example) 150 m and 200 m sets separate.
    Unsupported/time-only segments are omitted rather than guessed.
    """
    if str(getattr(slot, "source", "") or "") not in WATCH_SOURCES:
        return []

    raw_loads = getattr(slot, "watch_loads", [])
    if not isinstance(raw_loads, list):
        return []

    candidates = []
    for index, load in enumerate(raw_loads):
        if not isinstance(load, dict) or str(load.get("segment") or "CORE").upper() != "CORE":
            continue
        if load.get("work_rep") is False:
            continue
        try:
            meters = float(load.get("meters") or 0)
            seconds = float(load.get("seconds") or 0)
        except (TypeError, ValueError):
            continue
        if meters > 0 and seconds > 0:
            candidates.append((index, meters, seconds, str(load.get("zone") or "").strip()))

    used_indices = set()
    output = []
    try:
        segments = slot.segments.filter(type="CORE").order_by("order", "id")
    except Exception:
        segments = [seg for seg in slot.segments.all() if str(getattr(seg, "type", "")).upper() == "CORE"]
        segments.sort(key=lambda seg: (getattr(seg, "order", 0), getattr(seg, "id", 0) or 0))

    for segment in segments:
        structured = structured_segment_loads(segment, raw_loads)
        if structured is not None:
            for load in structured:
                meters, seconds = float(load["meters"]), float(load["seconds"])
                distance_match = re.search(r"(\d+)\s*m\b", str(segment.text), re.IGNORECASE)
                target_m = int(distance_match.group(1)) if distance_match else round(meters)
                output.append({"rep": len(output) + 1,
                    "distance_m": target_m,
                    "measured_distance_m": round(meters, 4),
                    "measured_seconds": round(seconds, 4),
                    "seconds": round(seconds * target_m / meters, 2) if distance_match and len(structured) > 1 else round(seconds, 2),
                    "pace_seconds_per_km": round(seconds * 1000 / meters, 2),
                    "average_hr_last_15": load.get("average_hr_last_15")})
                output[-1]["average_hr"] = load.get("average_hr")
                output[-1]["hr_tail"] = load.get("hr_tail") if "hr_tail" in load else tail_hr([load])
                if load.get("split_loads"):
                    splits = []
                    for index, split in enumerate(load["split_loads"], 1):
                        split_m, split_s = float(split["meters"]), float(split["seconds"])
                        full_split = 950 <= split_m <= 1050 or 475 <= split_m <= 525
                        target = (1000 if split_m >= 950 else 500) if full_split else round(split_m)
                        splits.append({"rep": index, "distance_m": target,
                            "measured_distance_m": split_m, "measured_seconds": split_s,
                            "seconds": round(split_s * target / split_m, 2) if full_split else split_s,
                            "pace_seconds_per_km": round(split_s * 1000 / split_m, 2),
                            "average_hr_last_15": split.get("average_hr_last_15")})
                        splits[-1]["average_hr"] = split.get("average_hr")
                        splits[-1]["hr_tail"] = tail_hr([split])
                    output[-1]["splits"] = splits
            continue
        try:
            reps = max(1, int(getattr(segment, "reps", 1) or 1))
            distance = float(getattr(segment, "distance_m", None) or 0)
        except (TypeError, ValueError):
            continue
        if distance <= 0:
            continue

        expected_zones = set(re.findall(r"\bz\s*([1-6])\b", str(getattr(segment, "text", "") or ""), re.IGNORECASE))
        for first, last in re.findall(r"\bz\s*([1-6])\s*(?:>|-)\s*z?\s*([1-6])\b", str(getattr(segment, "text", "") or ""), re.IGNORECASE):
            expected_zones.update(str(zone) for zone in range(min(int(first), int(last)), max(int(first), int(last)) + 1))
        segment_zone = str(getattr(segment, "zone", "") or "").strip()
        if segment_zone:
            expected_zones.add(segment_zone)

        tolerance = max(25.0 if distance <= 50 else 20.0, distance * 0.25)
        for _ in range(reps):
            match = next(
                (
                    (index, meters, seconds)
                    for index, meters, seconds, zone in candidates
                    if index not in used_indices
                    and (float(raw_loads[index]["nominal_rep_m"]) == distance
                         if raw_loads[index].get("nominal_rep_m") else abs(meters - distance) <= tolerance)
                    # Explicit structure metadata identifies the rep even if
                    # model D later assigns a different HR zone to that lap.
                    and ((raw_loads[index].get("work_rep") is True and raw_loads[index].get("nominal_rep_m"))
                         or not expected_zones or not zone or zone in expected_zones)
                ),
                None,
            )
            if not match:
                continue
            raw_index, meters, seconds = match
            used_indices.add(raw_index)
            output.append({
                "rep": len(output) + 1,
                "_lap_order": raw_index,
                # Show the clean planned rep distance (e.g. 200 m), not GPS
                # drift such as 190 or 250 m. Pace remains based on measured
                # meters, which are retained separately for transparency.
                "distance_m": round(distance),
                "measured_distance_m": round(meters, 4),
                "measured_seconds": round(seconds, 4),
                "seconds": round(seconds * distance / meters, 2) if reps > 1 else round(seconds, 2),
                "pace_seconds_per_km": round(seconds * 1000.0 / meters, 2),
                "average_hr_last_15": raw_loads[raw_index].get("average_hr_last_15"),
                "average_hr": raw_loads[raw_index].get("average_hr"),
                "hr_tail": tail_hr([raw_loads[raw_index]]),
            })
    if any("work_rep" in load for load in raw_loads if isinstance(load, dict)):
        output.sort(key=lambda row: row.get("_lap_order", -1))
    for index, row in enumerate(output, 1):
        row.pop("_lap_order", None)
        row["rep"] = index
    return output


def save_processed_main_reps(slot):
    """Refresh the derived layer after the slot's segments have been saved."""
    slot.watch_main_reps = processed_main_reps(slot)
    slot.save(update_fields=["watch_main_reps", "updated_at"])
    return slot.watch_main_reps
