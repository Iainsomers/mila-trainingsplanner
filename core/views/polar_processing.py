"""Inspectable, read-only pace processing. Thresholds are provisional, not zones."""
from bisect import bisect_left, bisect_right
from datetime import datetime
from math import ceil
from statistics import median

from .polar_raw import number, pace, display

WINDOW = 15.0
STOP_SPEED = 0.5
STOP_SECONDS = 5.0


def _seconds(value, origin):
    try:
        return (datetime.fromisoformat(str(value).replace("Z", "+00:00")) - origin).total_seconds()
    except (ValueError, TypeError, OverflowError):
        return None


def _merge_pauses(pauses):
    merged = []
    for start, end in sorted(pauses):
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(end, merged[-1][1]))
        else:
            merged.append((start, end))
    return merged


def _pause_movement(values, rate, start, end):
    """Require five consecutive measured moving seconds, not one GPS jump.

    Missing or negative increments break the evidence chain. Intervals only
    partly inside the proposed pause contribute their overlapping duration.
    """
    seconds = 0.0
    first = max(1, int(start / rate) + 1)
    last = min(len(values) - 1, ceil(end / rate))
    for index in range(first, last + 1):
        previous, current = number(values[index - 1]), number(values[index])
        overlap = max(0.0, min(end, index * rate) - max(start, (index - 1) * rate))
        if previous is not None and current is not None and previous >= 0 and current >= previous and (current - previous) / rate > STOP_SPEED:
            seconds += overlap
            if seconds >= STOP_SECONDS - 1e-8:
                return True
        else:
            seconds = 0.0
    return False


def _boundaries(exercise, sample_end, rate):
    cuts, pauses, notes = set(), [], []
    laps = exercise.get("laps")
    laps = laps if isinstance(laps, dict) else {}
    manual = laps.get("laps") or laps.get("manualLaps") or laps.get("manual-laps") or []
    for lap in manual if isinstance(manual, list) else []:
        split = number(lap.get("splitTimeMillis")) if isinstance(lap, dict) else None
        if split is not None and 0 < split / 1000 < sample_end:
            cuts.add(split / 1000)
    source = exercise.get("pauseTimes") or []
    try:
        origin = datetime.fromisoformat(str(exercise.get("startTime")).replace("Z", "+00:00"))
    except (ValueError, TypeError):
        if source:
            notes.append("Polar pause timestamps cannot be aligned: recording start time is missing or invalid.")
        return cuts, pauses, notes
    for pause in source if isinstance(source, list) else []:
        if not isinstance(pause, dict):
            continue
        start, end = _seconds(pause.get("startTime"), origin), _seconds(pause.get("endTime"), origin)
        if start is not None and end is not None and 0 <= start < end:
            pauses.append((start, end))
    merged = _merge_pauses(pauses)
    if merged:
        wall_end = _seconds(exercise.get("stopTime"), origin)
        pause_duration = sum(end - start for start, end in merged)
        tolerance = max(2.0, 2 * rate)
        if wall_end is not None and abs(sample_end - wall_end) <= tolerance:
            source = exercise.get("samples")
            streams = source.get("samples", []) if isinstance(source, dict) else []
            streams = streams if isinstance(streams, list) else []
            distance_stream = next((stream for stream in streams if isinstance(stream, dict) and str(stream.get("type", "")).upper() == "DISTANCE"), {})
            values = distance_stream.get("values", [])
            accepted = []
            for start, end in pauses:
                clipped_start, clipped_end = max(0.0, start), min(sample_end, end)
                label = f"{display(start)}–{display(end)} s"
                if clipped_start >= clipped_end:
                    notes.append(f"Ignored Polar pause {label}: outside the available distance samples.")
                elif _pause_movement(values, rate, clipped_start, clipped_end):
                    notes.append(f"Ignored conflicting Polar pause {label}: distance samples show sustained movement. Sample-based possible stops remain visible.")
                else:
                    accepted.append((clipped_start, clipped_end))
            pauses = _merge_pauses(accepted)
            if pauses:
                notes.append("Polar pauses aligned to elapsed time and checked against distance samples.")
            for start, end in pauses:
                cuts.update((start, end))
        elif wall_end is not None and abs(sample_end - (wall_end - pause_duration)) <= tolerance:
            elapsed_pause = 0
            for start, end in merged:
                cuts.add(start - elapsed_pause)
                elapsed_pause += end - start
            pauses = []
            notes.append("Samples use active recording time: Polar paused seconds are omitted. Pause boundaries still split the pace window.")
        else:
            pauses = []
            notes.append("Polar pause clock is uncertain: explicit pauses were not mapped onto samples. Inspect original JSON.")
    return cuts, pauses, notes


def processed_rows(exercise, raw_rows):
    source = exercise.get("samples")
    streams = source.get("samples", []) if isinstance(source, dict) else []
    streams = streams if isinstance(streams, list) else []
    stream = next((item for item in streams if isinstance(item, dict) and str(item.get("type", "")).upper() == "DISTANCE"), None)
    if not stream or not isinstance(stream.get("values"), list):
        return [dict(row, processed="NA", status="Missing data", reason="No distance samples", window="NA") for row in raw_rows], []
    rate = number(stream.get("intervalMillis"))
    if rate is None or rate <= 0:
        return [dict(row, processed="NA", status="Missing data", reason="Invalid distance sample interval", window="NA") for row in raw_rows], []
    rate /= 1000
    values = stream["values"]
    end = min((len(values) - 1) * rate, 86400)
    duration = number(exercise.get("durationMillis"))
    if duration is not None and duration >= 0:
        end = min(end, duration / 1000)
    cuts, pauses, notes = _boundaries(exercise, end, rate)
    cut_times = sorted(cuts)
    segments = []
    pause_index = 0
    for index in range(1, min(len(values), int(end / rate) + 1)):
        start, stop = (index - 1) * rate, index * rate
        previous, current = number(values[index - 1]), number(values[index])
        speed = (current - previous) / rate if previous is not None and current is not None and previous >= 0 and current >= previous else None
        while pause_index < len(pauses) and pauses[pause_index][1] <= start:
            pause_index += 1
        paused = pause_index < len(pauses) and pauses[pause_index][0] < stop and pauses[pause_index][1] > start
        cross = bisect_right(cut_times, start) < bisect_left(cut_times, stop)
        segments.append({"start": start, "end": stop, "speed": speed, "value": speed,
                         "kind": "pause" if paused else "boundary" if cross else "missing" if speed is None else "run"})
    # A single erroneous cumulative distance can cause a high increment followed
    # by a negative one. Repair only this bounded pair, using its intact endpoints
    # and stable measured running on both sides. A permanent reset stays missing.
    support = max(1, ceil(5 / rate))
    if rate * 2 <= 5:
        for index in range(support, len(segments) - support - 1):
            first, second = segments[index:index + 2]
            if first["kind"] != "run" or second["kind"] != "missing":
                continue
            before = segments[index - support:index]
            after = segments[index + 2:index + 2 + support]
            neighbors = before + after
            left, middle, right = (number(values[index + offset]) for offset in [0, 1, 2])
            if any(value is None for value in [left, middle, right]) or not middle > right >= left >= 0:
                continue
            if len(neighbors) != support * 2 or not all(item["kind"] == "run" and item["speed"] > STOP_SPEED for item in neighbors):
                continue
            if bisect_right(cut_times, before[0]["start"]) < bisect_left(cut_times, after[-1]["end"]):
                continue
            baseline = median(item["speed"] for item in neighbors)
            replacement = (right - left) / (2 * rate)
            if first["speed"] - baseline > max(1, baseline * 0.5) and abs(replacement - baseline) <= max(0.4, baseline * 0.15) and all(abs(item["speed"] - baseline) <= max(0.6, baseline * 0.25) for item in neighbors):
                for entry in [first, second]:
                    entry.update(kind="run", speed=replacement, value=replacement, corrected=True)
    # Low movement is kept separate; one bad sample is not automatically a stop.
    index = 0
    while index < len(segments):
        item = segments[index]
        if item["kind"] != "run" or item["speed"] > STOP_SPEED:
            index += 1
            continue
        stop = index + 1
        while stop < len(segments) and segments[stop]["kind"] == "run" and segments[stop]["speed"] <= STOP_SPEED and segments[stop]["start"] not in cuts:
            stop += 1
        if segments[stop - 1]["end"] - item["start"] >= STOP_SECONDS:
            for entry in segments[index:stop]:
                entry["kind"] = "stop"
        index = stop
    # Assign independent stretches before filtering, including exact lap boundaries.
    group = 0
    for index, item in enumerate(segments):
        if item["kind"] != "run" or item["start"] in cuts or (index and segments[index - 1]["kind"] != "run"):
            group += 1
        item["group"] = group
    # Isolated high or low bursts <= 5 s require stable running on BOTH sides.
    # A sustained acceleration, missing data, stop or lap boundary cannot be corrected.
    radius = max(1, ceil(10 / rate))
    support = max(1, ceil(5 / rate))
    candidates = {}
    for index, item in enumerate(segments):
        if item["kind"] != "run" or rate > 5:
            continue
        nearby = [entry["speed"] for entry in segments[max(0, index - radius):index + radius + 1]
                  if entry["kind"] == "run" and entry["group"] == item["group"]]
        if not nearby:
            continue
        baseline = median(nearby)
        if baseline > STOP_SPEED and abs(item["speed"] - baseline) > max(1.0, baseline * 0.5):
            candidates[index] = baseline
    index = 0
    while index < len(segments):
        if index not in candidates:
            index += 1
            continue
        stop = index + 1
        while stop in candidates and segments[stop]["group"] == segments[index]["group"]:
            stop += 1
        before, after = segments[max(0, index - support):index], segments[stop:stop + support]
        neighbors = before + after
        supported = len(before) * rate >= 5 and len(after) * rate >= 5 and all(
            entry["kind"] == "run" and entry["group"] == segments[index]["group"] for entry in neighbors)
        if supported and (stop - index) * rate <= 5:
            left, right = median(entry["speed"] for entry in before), median(entry["speed"] for entry in after)
            baseline = median(entry["speed"] for entry in neighbors)
            stable = baseline > STOP_SPEED and abs(left - right) <= max(0.4, baseline * 0.15)
            stable = stable and all(abs(entry["speed"] - baseline) <= max(0.6, baseline * 0.25) for entry in neighbors)
            if stable:
                for entry in segments[index:stop]:
                    entry["value"] = baseline
                    entry["corrected"] = True
        index = stop
    # Centered time-weighted 15-second windows, clipped to a valid stretch.
    bounds = {}
    for item in segments:
        if item["kind"] == "run":
            if item["group"] not in bounds:
                bounds[item["group"]] = [item["start"], item["end"]]
            else:
                bounds[item["group"]][1] = item["end"]
    ends = [item["end"] for item in segments]
    rows = []
    for raw in raw_rows:
        t = number(raw["time"])
        row = dict(raw, processed="NA", window="NA", status="Missing data", reason="No valid distance segment")
        index = bisect_left(ends, t) if t is not None else len(segments)
        if t == 0:
            row.update(status="Start", reason="No preceding segment")
        elif index < len(segments):
            item = segments[index]
            if item["kind"] == "pause":
                row.update(status="Polar pause", reason="Recorded Polar pause")
            elif item["kind"] == "stop":
                row.update(status="Possible stop", reason="At most 0.5 m/s for at least 5 seconds")
            elif item["kind"] == "boundary":
                row.update(status="Boundary", reason="Sample crosses a lap or pause boundary")
            elif item["kind"] == "run":
                low, high = bounds[item["group"]]
                left, right = max(low, t - WINDOW / 2), min(high, t + WINDOW / 2)
                distance, seconds, corrected = 0.0, 0.0, False
                for entry in segments[bisect_right(ends, left):bisect_left(ends, right) + 1]:
                    overlap = max(0, min(right, entry["end"]) - max(left, entry["start"]))
                    if entry["group"] == item["group"] and entry["kind"] == "run" and overlap:
                        distance += entry["value"] * overlap
                        seconds += overlap
                        corrected |= entry.get("corrected", False)
                if seconds > 0:
                    reason = "Time-weighted pace within this stretch"
                    if corrected:
                        reason = "Isolated burst replaced by stable neighboring speed"
                    if seconds < WINDOW - 1e-6:
                        reason += "; window shortened at boundary"
                    row.update(processed=pace(seconds, distance), window=display(seconds),
                               status="Possible measurement spike" if item.get("corrected") else "Processed with correction" if corrected else "Running",
                               reason=reason)
        rows.append(row)
    return rows, notes
