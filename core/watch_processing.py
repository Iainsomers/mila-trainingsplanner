"""Persisted, display-ready output derived from a slot's raw Watch laps."""

import re


WATCH_SOURCES = {"watch_a", "watch_b", "watch_c"}


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
                "distance_m": round(meters, 1),
                "seconds": round(seconds, 2),
                "pace_seconds_per_km": round(seconds * 1000.0 / meters, 2),
            })
    return output


def save_processed_main_reps(slot):
    """Refresh the derived layer after the slot's segments have been saved."""
    slot.watch_main_reps = processed_main_reps(slot)
    slot.save(update_fields=["watch_main_reps", "updated_at"])
    return slot.watch_main_reps
