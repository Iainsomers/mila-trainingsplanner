"""Persisted, display-ready output derived from a slot's raw Watch laps."""

import re


WATCH_SOURCES = {"watch_a", "watch_b", "watch_c"}


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
                 "zone": str(load.get("zone") or "")} for load in loads]
    except (TypeError, ValueError):
        return None
    structure = short_sets_and_continuous(laps, lambda lap: "Z" + lap["zone"])
    if not structure:
        continuous = continuous_kilometre_run(laps, lambda lap: "Z" + lap["zone"])
        if continuous:
            total = int(continuous.split("Main: ")[1].split(" m")[0])
            text = str(getattr(segment, "text", "") or "")
            if re.fullmatch(rf"\s*{total}\s*m(?:\s+Z[1-5])?\s*", text, re.IGNORECASE):
                return [{"matched_rep": True, "meters": sum(lap["distanceMeters"] for lap in laps),
                         "seconds": sum(lap["durationMillis"] for lap in laps) / 1000,
                         "average_hr": _block_average_hr(loads),
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
                 "average_hr": _block_average_hr(block),
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
                output.append({"rep": len(output) + 1,
                    "distance_m": int(distance_match.group(1)),
                    "measured_distance_m": round(meters, 4),
                    "measured_seconds": round(seconds, 4),
                    "seconds": round(seconds * int(distance_match.group(1)) / meters, 2) if len(structured) > 1 else round(seconds, 2),
                    "pace_seconds_per_km": round(seconds * 1000 / meters, 2),
                    "average_hr_last_15": load.get("average_hr_last_15")})
                output[-1]["average_hr"] = load.get("average_hr")
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
        segment_zone = str(getattr(segment, "zone", "") or "").strip()
        if segment_zone:
            expected_zones.add(segment_zone)

        tolerance = max(20.0, distance * 0.25)
        for _ in range(reps):
            match = next(
                (
                    (index, meters, seconds)
                    for index, meters, seconds, zone in candidates
                    if index not in used_indices
                    and abs(meters - distance) <= tolerance
                    and (not expected_zones or not zone or zone in expected_zones)
                ),
                None,
            )
            if not match:
                continue
            raw_index, meters, seconds = match
            used_indices.add(raw_index)
            output.append({
                "rep": len(output) + 1,
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
            })
    return output


def save_processed_main_reps(slot):
    """Refresh the derived layer after the slot's segments have been saved."""
    slot.watch_main_reps = processed_main_reps(slot)
    slot.save(update_fields=["watch_main_reps", "updated_at"])
    return slot.watch_main_reps
