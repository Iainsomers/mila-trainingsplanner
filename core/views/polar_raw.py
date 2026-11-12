"""Read-only Polar v4 inspection; never imports or modifies workouts."""
import json
import hashlib
import math
import os
import re
from datetime import date, timedelta
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from django.core.cache import cache
from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from .coach import (
    POLAR_V4_TRAINING_SESSIONS_URL,
    _closest_watch_label,
    _polar_json_request,
    _polar_targets_for_user,
    _polar_access_allowed,
    _refresh_polar_v4_token,
    _threshold_watch_label,
    _watch_t_reference_speeds,
    _watch_z_reference_speeds,
)


def number(value):
    if isinstance(value, bool):
        return None
    try:
        result = float(value)
        return result if math.isfinite(result) else None
    except (ValueError, TypeError):
        return None


def display(value):
    value = number(value)
    return f"{value:g}" if value is not None else "NA"


def duration(value):
    value = number(value)
    if value is None or value < 0:
        return "NA"
    seconds = value / 1000
    hours, rest = divmod(seconds, 3600)
    minutes, seconds = divmod(rest, 60)
    return f"{int(hours):02}:{int(minutes):02}:{seconds:06.3f}"


def pace(seconds, meters):
    seconds, meters = number(seconds), number(meters)
    if seconds is None or meters is None or seconds <= 0 or meters <= 0:
        return "NA"
    seconds_per_km = seconds * 1000 / meters
    if not math.isfinite(seconds_per_km):
        return "NA"
    rounded = round(seconds_per_km)
    return f"{rounded // 60}:{rounded % 60:02}"


def distance_rounded_to_50(value):
    value = number(value)
    if value is None or value < 0:
        return "NA"
    return display(math.floor(value / 50 + 0.5) * 50)


def lap_zone_paces(distance_m, duration_ms, athlete):
    distance_m, duration_ms = number(distance_m), number(duration_ms)
    if not athlete or distance_m is None or duration_ms is None or distance_m <= 0 or duration_ms <= 0:
        return "NA", "NA"
    speed_mps = distance_m / (duration_ms / 1000)
    z_label = _closest_watch_label(speed_mps, _watch_z_reference_speeds(athlete))
    t_label = _threshold_watch_label(speed_mps, _watch_t_reference_speeds(athlete))
    return z_label or "NA", t_label or "NA"


def lap_average_hr(lap, start_ms, end_ms, samples, *, fallback_to_lap=True):
    try:
        start_ms = float(start_ms or 0)
        end_ms = float(end_ms or 0)
    except (TypeError, ValueError):
        return "NA"
    if end_ms <= start_ms:
        return "NA"
    heart_rates = []
    local_samples = lap.get("heartRateSamples") if isinstance(lap, dict) else None
    if isinstance(local_samples, list):
        for sample in local_samples:
            if not isinstance(sample, dict):
                continue
            timestamp = number(sample.get("timeMillis"))
            bpm = number(sample.get("heartRate"))
            if timestamp is not None and start_ms <= timestamp < end_ms and bpm is not None and bpm > 0:
                heart_rates.append(bpm)
    else:
        streams = samples.get("samples") if isinstance(samples, dict) else None
        stream = next((item for item in streams or [] if isinstance(item, dict)
                       and str(item.get("type", "")).upper() == "HEART_RATE"), None)
        interval_ms = number(stream.get("intervalMillis")) if stream else None
        values = stream.get("values") if stream else None
        if interval_ms and interval_ms > 0 and isinstance(values, list):
            for index, value in enumerate(values):
                timestamp = index * interval_ms
                if start_ms <= timestamp < end_ms:
                    bpm = number(value)
                    if bpm is not None and bpm > 0:
                        heart_rates.append(bpm)
    if not heart_rates:
        fallback = number(lap.get("heartRate")) if fallback_to_lap and isinstance(lap, dict) else None
        return display(fallback) if fallback is not None and fallback > 0 else "NA"
    return display(math.floor(sum(heart_rates) / len(heart_rates) + 0.5))


def lap_average_hr_last_15(lap, start_ms, end_ms, samples):
    """Return the HR average for the last 15 seconds of a lap.

    Short laps use their complete duration. Do not substitute the lap average
    when samples are missing: that would falsely present it as a tail average.
    """
    try:
        start_ms = float(start_ms or 0)
        end_ms = float(end_ms or 0)
    except (TypeError, ValueError):
        return "NA"
    if end_ms <= start_ms:
        return "NA"
    tail_start_ms = start_ms if end_ms - start_ms < 15000 else end_ms - 15000
    return lap_average_hr(lap, tail_start_ms, end_ms, samples, fallback_to_lap=False)


def lap_rows(laps, athlete=None, samples=None):
    rows = []
    elapsed_ms = 0
    for index, lap in enumerate(laps if isinstance(laps, list) else [], 1):
        if not isinstance(lap, dict):
            continue
        duration_ms = number(lap.get("durationMillis")) or 0
        split_ms = number(lap.get("splitTimeMillis"))
        start_ms = elapsed_ms
        end_ms = split_ms if split_ms is not None and split_ms >= start_ms else start_ms + duration_ms
        z_pace, t_pace = lap_zone_paces(
            lap.get("distanceMeters"), lap.get("durationMillis"), athlete
        )
        from core.watch_hr import lap_hr_load
        end_hr = lap_hr_load(lap, start_ms, end_ms, samples, lap_average_hr(lap, start_ms, end_ms, samples))
        rows.append({
            "hr_tail": end_hr["hr_tail"],
            "index": index,
            "distance": display(lap.get("distanceMeters")),
            "distance_rounded_50": distance_rounded_to_50(lap.get("distanceMeters")),
            "duration": duration(lap.get("durationMillis")),
            "average_hr": lap_average_hr(lap, start_ms, end_ms, samples),
            "average_hr_last_15": lap_average_hr_last_15(lap, start_ms, end_ms, samples),
            "pace": pace(
                number(lap.get("durationMillis")) / 1000
                if number(lap.get("durationMillis")) is not None else None,
                lap.get("distanceMeters"),
            ),
            "z_pace": z_pace,
            "t_pace": t_pace,
            "elapsed": duration(lap.get("splitTimeMillis")),
        })
        elapsed_ms = end_ms
    return rows


def type_a_description(laps, athlete=None):
    rows = lap_rows(laps, athlete)
    parsed = []
    for row in rows:
        distance_m = number(row["distance"])
        duration_ms = None
        source = laps[row["index"] - 1] if isinstance(laps, list) and row["index"] <= len(laps) else {}
        if isinstance(source, dict):
            duration_ms = number(source.get("durationMillis"))
        zone_text = str(row.get("z_pace") or "")
        zone = int(zone_text[1:]) if zone_text.startswith("Z") and zone_text[1:].isdigit() else None
        if distance_m is not None and distance_m >= 0 and duration_ms is not None and duration_ms > 0:
            parsed.append({
                "index": row["index"],
                "distance_m": distance_m,
                "rounded_m": int(math.floor(distance_m / 50 + 0.5) * 50),
                "duration_s": duration_ms / 1000,
                "zone": zone,
                "zone_label": zone_text if zone is not None else "",
            })

    # Some Polar recordings split a workout into timed work blocks and short
    # active recoveries. These blocks have no repeated distance pattern, so
    # recognize the alternating duration/distance pattern before the normal
    # distance-based main-section detector.
    timed_work = []
    timed_recoveries = []
    cursor = 0
    while cursor < len(parsed):
        work = parsed[cursor]
        if work["duration_s"] < 300 or work["rounded_m"] < 500:
            break
        timed_work.append(work)
        cursor += 1
        if cursor >= len(parsed):
            break
        recovery = parsed[cursor]
        if recovery["duration_s"] > 180 or recovery["rounded_m"] > 300:
            break
        timed_recoveries.append(recovery)
        cursor += 1
    if timed_work:
        work_distances = sorted(row["rounded_m"] for row in timed_work)
        work_durations = sorted(row["duration_s"] for row in timed_work)
        middle = len(work_distances) // 2
        distance_median = work_distances[middle]
        duration_median = work_durations[middle]
    else:
        distance_median = duration_median = 0
    looks_like_timed_blocks = (
        len(timed_work) >= 2
        and len(timed_recoveries) >= len(timed_work) - 1
        and timed_work[0]["rounded_m"] <= distance_median * 1.7
        and timed_work[0]["duration_s"] <= duration_median * 1.7
        # A long recovery must not make a prefix look like the whole session.
        and not any(row["rounded_m"] >= 400 for row in parsed[cursor:])
    )
    if looks_like_timed_blocks:
        def timed_label(row):
            seconds = int(math.floor(row["duration_s"] + 0.5))
            rounded_minutes = int(math.floor(seconds / 60 + 0.5))
            if rounded_minutes and abs(seconds - rounded_minutes * 60) <= 2:
                duration_label = f"{rounded_minutes}'"
            else:
                duration_label = f"{seconds}s"
            label = row["zone_label"] or ""
            average_pace = pace(row["duration_s"], row["distance_m"])
            if average_pace != "NA":
                label += f" ({average_pace}/km)" if label else f"({average_pace}/km)"
            return f"{duration_label} {label}".strip()

        recovery_values = timed_recoveries[:len(timed_work) - 1]
        average_recovery = int(math.floor(
            sum(row["duration_s"] for row in recovery_values) / len(recovery_values) + 0.5
        ))
        parts = ["WU: none", "Main: " + " + ".join(timed_label(row) for row in timed_work)]
        parts[1] += f", recovery avg {average_recovery} s"
        parts.append("CD: none")
        return " · ".join(parts)

    substantial_distances = [row["rounded_m"] for row in parsed if row["rounded_m"] >= 400]
    first_is_warmup = bool(
        parsed
        and parsed[0]["zone"] == 1
        and parsed[0]["rounded_m"] >= 1000
        and substantial_distances.count(parsed[0]["rounded_m"]) == 1
    )
    main_start = 1 if first_is_warmup else 0
    candidate_distances = [row["rounded_m"] for row in parsed[main_start:] if row["rounded_m"] >= 400]
    work_positions = [
        index for index, row in enumerate(parsed)
        if index >= main_start
        and row["rounded_m"] >= 400
        and (candidate_distances.count(row["rounded_m"]) >= 2 or (row["zone"] or 0) >= 2)
    ]
    substantial_rows = [row for row in parsed if row["rounded_m"] >= 1000]
    small_remainder_m = sum(row["distance_m"] for row in parsed if row["rounded_m"] < 1000)
    if not work_positions and len(substantial_rows) == 1 and small_remainder_m <= 100:
        return type_a_general_description({
            "distanceMeters": sum(row["distance_m"] for row in parsed),
            "durationMillis": sum(row["duration_s"] for row in parsed) * 1000,
        }, athlete)
    if not work_positions:
        short_candidates = [
            (index, row["distance_m"] / row["duration_s"])
            for index, row in enumerate(parsed)
            if index >= main_start and 50 <= row["rounded_m"] <= 250 and row["duration_s"] > 0
        ]
        speeds = sorted(speed for _, speed in short_candidates if speed > 0)
        if len(speeds) >= 3:
            gaps = [
                (speeds[index + 1] / speeds[index], index)
                for index in range(len(speeds) - 1) if speeds[index] > 0
            ]
            gap_ratio, gap_index = max(gaps, default=(0, 0))
            if gap_ratio >= 1.5:
                speed_threshold = math.sqrt(speeds[gap_index] * speeds[gap_index + 1])
                work_positions = [
                    index for index, speed in short_candidates if speed >= speed_threshold
                ]
    if not work_positions:
        return "No clear main section detected."

    first_work, last_work = work_positions[0], work_positions[-1]
    warmup = parsed[0] if first_is_warmup and first_work > 0 else None

    work_rows = [parsed[index] for index in work_positions]
    short_structure = bool(work_rows and max(row["rounded_m"] for row in work_rows) <= 250)
    groups = []
    if short_structure:
        def median_distance(values):
            ordered = sorted(row["rounded_m"] for row in values)
            return ordered[len(ordered) // 2]

        one_distance = median_distance(work_rows)
        one_cost = sum(abs(row["rounded_m"] - one_distance) for row in work_rows)
        best_split = None
        for split_at in range(2, len(work_rows) - 1):
            left, right = work_rows[:split_at], work_rows[split_at:]
            left_distance, right_distance = median_distance(left), median_distance(right)
            if abs(left_distance - right_distance) < 50:
                continue
            split_cost = (
                sum(abs(row["rounded_m"] - left_distance) for row in left)
                + sum(abs(row["rounded_m"] - right_distance) for row in right)
            )
            boundary_recovery = sum(
                row["duration_s"] for row in parsed
                if left[-1]["index"] < row["index"] < right[0]["index"]
            )
            candidate = (split_cost, -boundary_recovery, split_at, left_distance, right_distance)
            if best_split is None or candidate < best_split:
                best_split = candidate
        if best_split and best_split[0] <= one_cost - 50:
            _, _, split_at, left_distance, right_distance = best_split
            groups = [
                {"distance_m": left_distance, "rows": work_rows[:split_at]},
                {"distance_m": right_distance, "rows": work_rows[split_at:]},
            ]
        else:
            groups = [{"distance_m": one_distance, "rows": work_rows}]
    else:
        for row in work_rows:
            if not groups or groups[-1]["distance_m"] != row["rounded_m"]:
                groups.append({"distance_m": row["rounded_m"], "rows": []})
            groups[-1]["rows"].append(row)

    segment_texts = []
    for group in groups:
        group_rows = group["rows"]
        zones = sorted({row["zone"] for row in group_rows if row["zone"] is not None})
        zone_label = ""
        if zones:
            zone_label = f"Z{zones[0]}" if len(zones) == 1 else f"Z{zones[0]}>Z{zones[-1]}"
        recoveries = []
        for before, after in zip(group_rows, group_rows[1:]):
            recoveries.extend(
                row["duration_s"] for row in parsed
                if before["index"] < row["index"] < after["index"] and (row["zone"] or 0) < 2
            )
        segment = f"{len(group_rows)}×{group['distance_m']} m"
        if zone_label:
            segment += f" {zone_label}"
        average_pace = pace(
            sum(row["duration_s"] for row in group_rows),
            sum(row["distance_m"] for row in group_rows),
        )
        if average_pace != "NA":
            segment += f" ({average_pace})"
        if recoveries:
            average = math.floor(sum(recoveries) / len(recoveries) + 0.5)
            segment += f" p{average}"
        segment_texts.append(segment)

    trailing = parsed[last_work + 1:]
    cooldown_start = next((index for index, row in enumerate(trailing) if row["rounded_m"] >= 1000), None)
    cooldown_rows = trailing[cooldown_start:] if cooldown_start is not None else []
    cooldown_distance = sum(row["distance_m"] for row in cooldown_rows if row["zone"] == 1)
    cooldown = cooldown_distance >= 1000 and cooldown_rows and all(row["zone"] == 1 for row in cooldown_rows)
    parts = [f"WU: {warmup['rounded_m']} m {warmup['zone_label']}" if warmup else "WU: none"]
    parts.append("Main: " + " + ".join(segment_texts))
    parts.append(f"CD: {int(math.floor(cooldown_distance / 50 + 0.5) * 50)} m Z1" if cooldown else "CD: none")
    return " · ".join(parts)


def type_a_general_description(exercise, athlete=None):
    distance_m = number(exercise.get("distanceMeters")) if isinstance(exercise, dict) else None
    duration_ms = number(exercise.get("durationMillis")) if isinstance(exercise, dict) else None
    if distance_m is None or duration_ms is None or distance_m <= 0 or duration_ms <= 0:
        return ""
    z_pace, _ = lap_zone_paces(distance_m, duration_ms, athlete)
    average_pace = pace(duration_ms / 1000, distance_m)
    description = f"Continuous run: {distance_m / 1000:.1f} km"
    if z_pace != "NA":
        description += f" {z_pace}"
    if average_pace != "NA":
        description += f" ({average_pace}/km)"
    return description


def type_a_training_fields(description):
    """Convert a Type A description into the three AYC training fields."""
    text = str(description or "").strip()
    if not text or text.lower() == "no clear main section detected.":
        return {"wu": "", "main": "", "cd": ""}

    fields = {"wu": "", "main": "", "cd": ""}
    found_main = False
    for part in re.split(r"\s+·\s+", text):
        label, separator, value = part.partition(":")
        if not separator:
            continue
        key = {"wu": "wu", "main": "main", "cd": "cd"}.get(label.strip().lower())
        if not key:
            continue
        value = value.strip()
        if value.lower() == "none":
            value = ""
        if key == "main":
            value = re.sub(r",\s*recovery\s+avg\s+\d+\s*s\s*$", "", value, flags=re.IGNORECASE).strip()
            found_main = bool(value)
        fields[key] = value

    if not found_main:
        fields["main"] = re.sub(r"^continuous\s+run:\s*", "", text, flags=re.IGNORECASE).strip()
    return fields


def type_a_watch_loads(exercise, athlete=None):
    """Return actual Type A distance/time loads for later AYC accounting."""
    if not isinstance(exercise, dict):
        return []
    laps_container = exercise.get("laps") or {}
    laps_container = laps_container if isinstance(laps_container, dict) else {}
    manual_laps = laps_container.get("laps") or laps_container.get("manualLaps") or laps_container.get("manual-laps") or []
    if manual_laps:
        source_laps = manual_laps
    else:
        source_laps = [{
            "distanceMeters": exercise.get("distanceMeters"),
            "durationMillis": exercise.get("durationMillis"),
        }]

    rows = []
    elapsed_ms = 0
    for index, lap in enumerate(source_laps, 1):
        if not isinstance(lap, dict):
            continue
        distance_m = number(lap.get("distanceMeters"))
        duration_ms = number(lap.get("durationMillis"))
        start_ms = elapsed_ms
        split_ms = number(lap.get("splitTimeMillis"))
        elapsed_ms = split_ms if split_ms is not None and split_ms >= start_ms else start_ms + (duration_ms or 0)
        if distance_m is None or distance_m <= 0 or duration_ms is None or duration_ms <= 0:
            continue
        z_pace, t_pace = lap_zone_paces(distance_m, duration_ms, athlete)
        zone = z_pace[1:] if z_pace.startswith("Z") and z_pace[1:].isdigit() else "1"
        from core.watch_hr import lap_hr_load
        end_hr = lap_hr_load(lap, start_ms, elapsed_ms, exercise.get("samples"), lap_average_hr(lap, start_ms, elapsed_ms, exercise.get("samples")))
        rows.append({
            "hr_tail": end_hr["hr_tail"], "hr_samples": end_hr["hr_samples"],
            "index": index,
            "distance_m": distance_m,
            "seconds": duration_ms / 1000.0,
            "elapsed_seconds": (elapsed_ms-start_ms) / 1000.0,
            "zone": zone,
            "t_key": _watch_t_key(t_pace),
            "average_hr_last_15": number(lap_average_hr_last_15(lap, start_ms, elapsed_ms, exercise.get("samples"))),
            "average_hr": number(lap_average_hr(lap, start_ms, elapsed_ms, exercise.get("samples"))),
        })
    if not rows:
        return []

    rounded = [int(math.floor(row["distance_m"] / 50 + 0.5) * 50) for row in rows]
    first_is_warmup = bool(
        rows
        and rows[0]["zone"] == "1"
        and rounded[0] >= 1000
        and rounded.count(rounded[0]) == 1
    )
    main_start = 1 if first_is_warmup else 0
    candidate_distances = [rounded[index] for index in range(main_start, len(rows)) if rounded[index] >= 400]
    work_positions = [
        index for index, row in enumerate(rows)
        if index >= main_start
        and rounded[index] >= 400
        and (candidate_distances.count(rounded[index]) >= 2 or int(row["zone"]) >= 2)
    ]
    first_work = work_positions[0] if work_positions else None
    last_work = work_positions[-1] if work_positions else None
    cooldown_start = None
    if last_work is not None:
        cooldown_start = next(
            (index for index in range(last_work + 1, len(rows))
             if rounded[index] >= 1000 and rows[index]["zone"] == "1"),
            None,
        )

    loads = []
    for index, row in enumerate(rows):
        segment = "CORE"
        if first_work is not None and first_is_warmup and index < first_work:
            segment = "WU"
        elif cooldown_start is not None and index >= cooldown_start:
            segment = "CD"
        loads.append({
            "hr_tail": row["hr_tail"], "hr_samples": row["hr_samples"],
            "segment": segment,
            "zone": row["zone"],
            "meters": row["distance_m"],
            "seconds": row["seconds"],
            "elapsed_seconds": row["elapsed_seconds"],
            "t_key": row["t_key"],
            "race": False,
        })
        if row["average_hr_last_15"] is not None:
            loads[-1]["average_hr_last_15"] = row["average_hr_last_15"]
        if row["average_hr"] is not None:
            loads[-1]["average_hr"] = row["average_hr"]
    return loads


def type_b_description(laps, athlete=None):
    """Model B: recognize repeated distance reps split by short/long recoveries."""
    if not isinstance(laps, list):
        return ""
    structured = _short_sets_structure(laps, athlete)
    if structured:
        return structured["description"]
    mixed = _mixed_short_structure(laps, athlete)
    if mixed:
        return mixed["description"]
    timed = _km_timed_structure(laps, athlete)
    if timed:
        return timed["description"]
    continuous = _continuous_km_description(laps, athlete)
    if continuous:
        return continuous
    rows = []
    elapsed = 0.0
    for index, lap in enumerate(laps):
        if not isinstance(lap, dict):
            continue
        distance_m = number(lap.get("distanceMeters"))
        duration_ms = number(lap.get("durationMillis"))
        if distance_m is None or duration_ms is None or distance_m <= 0 or duration_ms <= 0:
            elapsed += max(0.0, duration_ms or 0)
            continue
        z_pace, _ = lap_zone_paces(distance_m, duration_ms, athlete)
        split_ms = number(lap.get("splitTimeMillis"))
        end_elapsed = split_ms if split_ms is not None and split_ms >= elapsed else elapsed + duration_ms
        rows.append({
            "index": index,
            "distance_m": distance_m,
            "rounded_m": int(math.floor(distance_m / 50 + 0.5) * 50),
            "duration_s": duration_ms / 1000.0,
            "zone": z_pace[1:] if z_pace.startswith("Z") and z_pace[1:].isdigit() else "",
            "start_ms": elapsed,
            "end_ms": end_elapsed,
        })
        elapsed = end_elapsed
    if len(rows) < 6:
        return ""

    distance_counts = {}
    for row in rows:
        if 350 <= row["rounded_m"] <= 800:
            distance_counts[row["rounded_m"]] = distance_counts.get(row["rounded_m"], 0) + 1
    if not distance_counts:
        return ""
    dominant_distance = max(distance_counts, key=lambda value: (distance_counts[value], -value))
    candidate_rows = [
        row for row in rows
        if abs(row["distance_m"] - dominant_distance) <= max(75, dominant_distance * 0.15)
    ]
    if len(candidate_rows) < 6:
        return ""

    # A long Z1 lap can contain the end of a work rep and its recovery. Keep
    # it as a rep when it sits inside the repeated-distance pattern, but do
    # not let its combined recovery time distort the work pace.
    groups = [[]]
    for row in candidate_rows:
        if groups[-1]:
            previous = groups[-1][-1]
            gap_s = max(0.0, (row["start_ms"] - previous["end_ms"]) / 1000.0)
            intervening = [item for item in rows if previous["index"] < item["index"] < row["index"]]
            gap_s += sum(item["duration_s"] for item in intervening)
            if gap_s >= 180:
                groups.append([])
        groups[-1].append(row)
    # A long recovery can split one actual set into two groups. Do not drop a
    # short fragment of repeated work (for example 6 + 2 + 6 reps): when it
    # matches the following or preceding group by zone, attach it there.
    # If it does not match either group, keep it visible as its own segment
    # instead of silently losing completed reps.
    def work_zones(group):
        work_rows = [row for row in group if int(row["zone"] or 0) >= 2]
        return {int(row["zone"]) for row in work_rows}

    def compatible_groups(left, right):
        left_zones, right_zones = work_zones(left), work_zones(right)
        return not left_zones or not right_zones or left_zones == right_zones

    index = 0
    while index < len(groups):
        if len(groups[index]) < 3:
            if index + 1 < len(groups) and compatible_groups(groups[index], groups[index + 1]):
                groups[index + 1] = groups[index] + groups[index + 1]
                groups.pop(index)
                continue
            if index > 0 and compatible_groups(groups[index - 1], groups[index]):
                groups[index - 1].extend(groups[index])
                groups.pop(index)
                continue
        index += 1
    if len(groups) < 2:
        return ""

    def group_label(group):
        work_rows = [row for row in group if int(row["zone"] or 0) >= 2]
        if not work_rows:
            work_rows = group
        zones = sorted({int(row["zone"]) for row in work_rows if row["zone"].isdigit()})
        zone_label = f"Z{zones[0]}" if len(zones) == 1 else (f"Z{zones[0]}>Z{zones[-1]}" if zones else "")
        representative = dominant_distance
        work_seconds = sum(row["duration_s"] for row in work_rows)
        work_distance = sum(min(row["distance_m"], representative) for row in work_rows)
        average_pace = pace(work_seconds, work_distance)
        label = f"{len(group)}×{representative} m"
        if zone_label:
            label += f" {zone_label}"
        if average_pace != "NA":
            label += f" ({average_pace})"
        recovery_values = []
        for before, after in zip(group, group[1:]):
            intervening = [item for item in rows if before["index"] < item["index"] < after["index"]]
            recovery = sum(item["duration_s"] for item in intervening)
            if 0 < recovery < 180:
                recovery_values.append(recovery)
        if recovery_values:
            label += f" p{int(math.floor(sum(recovery_values) / len(recovery_values) + 0.5))}"
        return label

    warmup_rows = [row for row in rows if row["index"] < candidate_rows[0]["index"]]
    # The dominant-distance candidates may end before a later work block of a
    # different distance (for example 400 m followed by 200 m reps). Start CD
    # after the final clearly faster work lap, not after the last dominant lap.
    active_rows = [row for row in rows if int(row["zone"] or 0) >= 2]
    last_work_index = max((row["index"] for row in active_rows), default=candidate_rows[-1]["index"])
    cooldown_rows = [row for row in rows if row["index"] > last_work_index]
    warmup_distance = sum(row["distance_m"] for row in warmup_rows if row["zone"] == "1")
    # A cooldown can be split over several final easy laps (for example
    # 535 m + 455 m). Keep the trailing Z1 block together instead of requiring
    # one single lap to be at least one kilometre.
    cooldown_block = []
    for row in cooldown_rows:
        if row["zone"] == "1":
            cooldown_block.append(row)
        elif cooldown_block:
            break
    cooldown_distance = sum(row["distance_m"] for row in cooldown_block)
    parts = [f"WU: {int(math.floor(warmup_distance / 50 + 0.5) * 50)} m Z1" if warmup_distance >= 500 else "WU: none"]
    parts.append("Main: " + " + ".join(group_label(group) for group in groups))
    parts.append(f"CD: {int(math.floor(cooldown_distance / 50 + 0.5) * 50)} m Z1" if cooldown_distance >= 500 else "CD: none")
    return " · ".join(parts)


def _short_sets_structure(laps, athlete=None):
    from core.watch_structure import short_sets_and_continuous
    return short_sets_and_continuous(laps, lambda lap: lap_zone_paces(
        lap["distanceMeters"], lap["durationMillis"], athlete)[0])


def _mixed_short_structure(laps, athlete=None):
    from core.watch_structure import mixed_short_repetitions, alternating_medium_repetitions
    zone_for_lap = lambda lap: lap_zone_paces(lap["distanceMeters"], lap["durationMillis"], athlete)[0]
    return mixed_short_repetitions(laps, zone_for_lap) or alternating_medium_repetitions(laps, zone_for_lap)


def _km_timed_structure(laps, athlete=None):
    from core.watch_structure import kilometre_split_timed_intervals
    return kilometre_split_timed_intervals(laps, lambda lap: lap_zone_paces(
        lap["distanceMeters"], lap["durationMillis"], athlete)[0])


def _continuous_km_description(laps, athlete=None):
    from core.watch_structure import continuous_kilometre_run
    return continuous_kilometre_run(laps, lambda lap: lap_zone_paces(
        lap["distanceMeters"], lap["durationMillis"], athlete)[0])


def _model_b_ai_description(laps, athlete=None, *, allow_lap_structure=True, diagnostics=None, strict_lap_structure=False, requested_structure=None, chat_messages=None):
    """Ask the language model to identify nested interval structure for Watch B.

    The model only proposes structure from compact numeric lap facts.  The
    server validates the numeric ranges and builds the displayed description,
    so a model response cannot alter measured distance or time calculations.
    """
    diagnostics = diagnostics if diagnostics is not None else {}
    no_warmup_requested = bool(chat_messages and re.fullmatch(
        r"\s*(?:no\s+(?:wu|warm[ -]?up)|geen\s+(?:wu|warming[ -]?up))\s*[.!]?\s*",
        chat_messages[-1].get('content', ''), re.I))
    diagnostics['status'] = 'measured_structure'
    # Strong measured structure wins over an AI proposal which can omit short
    # reps or repeat the following continuous block inside every set.
    structured = _short_sets_structure(laps, athlete) if isinstance(laps, list) else None
    if structured and not requested_structure and not chat_messages:
        return structured["description"]
    mixed = _mixed_short_structure(laps, athlete)
    if mixed and not requested_structure and not chat_messages:
        return mixed["description"]
    timed = _km_timed_structure(laps, athlete)
    if timed and not requested_structure and not chat_messages:
        return timed["description"]
    continuous = _continuous_km_description(laps, athlete)
    if continuous and not requested_structure and not chat_messages:
        return continuous
    api_key = (os.environ.get("OPENAI_API_KEY") or "").strip()
    if not api_key or not isinstance(laps, list):
        diagnostics["status"] = "unavailable"
        return ""
    facts = []
    elapsed_s = 0.0
    for index, lap in enumerate(laps, 1):
        if not isinstance(lap, dict):
            continue
        distance_m = number(lap.get("distanceMeters"))
        duration_ms = number(lap.get("durationMillis"))
        if distance_m is None or duration_ms is None or distance_m < 0 or duration_ms <= 0:
            elapsed_s += max(0.0, (duration_ms or 0) / 1000)
            continue
        z_label, _ = lap_zone_paces(distance_m, duration_ms, athlete)
        facts.append({
            "lap": index,
            "distance_m": round(distance_m, 1),
            "rounded_50_m": int(math.floor(distance_m / 50 + 0.5) * 50),
            "duration_s": round(duration_ms / 1000, 3),
            "pace": pace(duration_ms / 1000, distance_m),
            "zone": z_label if z_label != "NA" else "",
            "elapsed_s": round(elapsed_s, 3),
            "timer_s": number(lap.get("timerDurationMillis")) / 1000 if number(lap.get("timerDurationMillis")) is not None else None,
            "paused_s": number(lap.get("pausedDurationMillis")) / 1000 if number(lap.get("pausedDurationMillis")) is not None else None,
            "lap_trigger": lap.get("lapTrigger"),
            "lap_intensity": lap.get("lapIntensity"),
        })
        elapsed_s += duration_ms / 1000
    if len(facts) < 6:
        diagnostics["status"] = "insufficient_laps"
        return ""

    prompt = {
        "task": (
            "Consecutive Z1 laps normally form one continuous easy run, including the final partial lap; do not call autolaps repetitions without explicit interval evidence or clear work/recovery. Recognize the performed running workout from recorded laps. Find nested "
            "repeated structures such as 2 sets of (3x500m + 5x400m + 6x200m). "
            "Short slow laps are recoveries, not work. Include only clearly observed "
            "warmup, main work and cooldown. Do not force every lap into a block."
            " Laps can mix automatic kilometre splits and manual boundaries. "
            "Use relative speed and alternating recovery to find short repetitions, "
            "even when GPS undermeasures a rep or its zone is low. Long recovery "
            "can separate equal sets. Consecutive running laps at similar speeds "
            "without recovery form continuous work, not necessarily repetitions. "
            "A clear late slowdown can begin cooldown even if a later lap returns "
            "to Z2. Do not discard short reps in favour of the dominant kilometre laps. "
            "If the schema cannot express a repeated set followed once by continuous "
            "work, return confidence below 0.65 rather than repeating that work per set."
            " Equal 500 m or kilometre laps alone are not interval evidence. Require repeated "
            "work/recovery transitions, repeated timer pauses or workout-step markers. "
            "One or two isolated stops during a long easy run do not establish intervals. "
            "Prefer lap_structure for repeated distance intervals as well as reps spanning automatic laps or multiple time groups. Group distance repetitions by their intended nominal distance even with modest GPS variation, a slower opening rep or a low final heart rate. An isolated rounded distance outlier does not by itself split a consistent repeated group. "
            "Assign every lap exactly once to warmup_laps, cooldown_laps, recovery_laps, stop_laps or a rep. "
            "Each rep is a consecutive list of original one-based lap numbers. Do not sum over a recovery. "
            "A long nearly stationary lap is a stop, not an interval or work distance. "
            "For example 215s + 211s + 56s without recovery can form one 8-minute rep; "
            "another 481s lap can be its second rep. A later 253s rep can belong to a group near 4 minutes. "
            "For each group propose either target_meters (nominal distance, multiple of 50) or whole-minute target_seconds, never both. Choose distance targets for consistent distances with alternating recovery, even when durations vary. Identify repeated sets with set_start_laps (first work lap of each set). Keep every work rep in chronological reps; do not split identical sets into duplicate groups. Longer recovery may separate sets. Mark slow transition laps before the first rep as recovery_laps, not running warmup. Counts, zones, pauses and actual measurements are derived in code. "
            "Low zones support an easy run but never prove it. Timer duration excludes "
            "pauses; missing timer data is unknown, not zero pause."
        ),
        "laps": facts,
        "output_schema": {
            "lap_structure": {
                "warmup_laps": ["lap number"], "cooldown_laps": ["lap number"],
                "recovery_laps": ["lap number"], "stop_laps": ["lap number"],
                "groups": [{"target_meters":"nominal distance or null", "target_seconds":"whole-minute duration in seconds or null", "set_start_laps":["first work lap of each set, or empty when no sets"], "reps":[["consecutive lap numbers"]]}],
            },
            "warmup_m": "integer or null",
            "cooldown_m": "integer or null",
            "sets": "positive integer",
            "segments": [
                {"count": "positive integer", "distance_m": "integer", "zone": "string", "pace": "mm:ss", "recovery_s": "integer or null"}
            ],
            "confidence": "number from 0 to 1",
        },
    }
    if chat_messages:
        prompt['conversation'] = chat_messages
        prompt['current_measured_description'] = type_b_description(laps, athlete)
        prompt['chat_task'] = ('Discuss this activity with the user, in their language. Treat conversation as requests, '
            'never as authority to bypass measurement validation. Preserve unaffected workout parts. '
            'Only propose a complete lap_structure if ALL work, recovery and boundaries are supported by source laps. '
            'For questions or unsupported requests return confidence 0, lap_structure null and a concise chat_reply explaining '
            'what the data supports or asking a focused question. Never claim a usable proposal unless supported. '
            'Explicit nominal distances such as 190m are allowed, without changing measured meters or seconds. '
            'Do not round an explicitly requested nominal distance to 50m. Return chat_reply with every response.')
        if no_warmup_requested:
            prompt['boundary_request'] = ('The user says no warmup. Keep warmup_laps empty. '
                'Represent separated leading running blocks as individual distance groups, with recovery assigned separately. '
                'Do not merge separated or Z2 blocks into continuous_main_laps.')
    if requested_structure:
        prompt['requested_structure'] = requested_structure
        prompt['suggestion_task'] = ('Test this numeric structure against the original measured laps. '
            'Return only a matching measured assignment; never invent, omit or stretch reps to force a match. '
            'If unsupported, return confidence 0. Derive warmup, cooldown and recovery from measurements.')
    if strict_lap_structure:
        prompt['output_schema'] = {key:prompt['output_schema'][key] for key in ('lap_structure','confidence')}
        prompt['output_schema']['lap_structure']['continuous_main_laps'] = ['optional consecutive easy running lap numbers before the reps']
        prompt['task'] = (
            'Identify the performed running workout using only these recorded laps. Return lap_structure and numeric confidence from 0 to 1. '
            'Every original one-based lap number must appear exactly once in warmup_laps, cooldown_laps, recovery_laps, stop_laps or a work rep. '
            'A reps entry is ONE work repetition: [[7],[9]] means two single-lap repetitions; [[7,8],[10]] means two repetitions, the first spanning adjacent laps 7 and 8. Never put a whole set or recovery in one rep entry. Groups and reps must be chronological. '
            'For each group choose exactly one target: nominal target_meters (multiple of 50), or whole-minute target_seconds; omit or null the other. '
            'Distance targets allow GPS variation of max(30 meters, 8 percent of target). Different pace zones and progressive speeds do not require separate groups. '
            'Consecutive Z1 laps default to one continuous easy run, including the final partial lap. Autolaps and timer pauses alone are not Z1 repetitions. Only explicit interval markers or clear relative work/recovery override this. '
            'When a sustained easy run is followed by strides, put the continuous running laps in continuous_main_laps and the strides in groups. For example, ten Z1 kilometre splits followed by a tiny 3m/1s transition and three fast 100m efforts separated by slow recoveries are 10000m easy + 3x100m. Include the tiny transition at the end of continuous_main_laps, and keep every measured recovery separate. '
            'Repeated work with slower recoveries is interval evidence. Automatic equal-distance splits without recovery are not. '
            'Determine work/recovery structure before intensity zones. Check every proposed warmup boundary: an opening lap matching later reps in distance and speed, followed by comparable slower recovery, belongs to the interval sequence even in Z1/Z2. Example: eight 500m efforts around 100s with 60s recoveries, then 208s recovery and eight more 500m efforts form 2x8x500m; keep all sixteen reps in one group with set_start_laps. A genuinely longer or clearly slower warmup remains warmup. '
            'If a longer recovery divides equal-size sets, use one group and set_start_laps containing the first work lap of every set, including the first rep. '
            'Otherwise use an empty set_start_laps. Do not invent a set or discard a rep to make equal sets. '
            'Warmup, cooldown and recovery allow only Z1/Z2 or unknown pace zones; never assign Z3-Z5 work laps to these roles. '
            'Running warmup/cooldown must average at least 2 m/s; classify slow transitions before/after work as recovery_laps. '
            'Stop laps must be at least 600 seconds and slower than 1 m/s. Long incidental stops do not erase the surrounding workout structure. '
            'Code derives counts and ordinary/set pause durations from source laps. No need to predict pause numbers. '
            'Each group has 2-30 reps. Use target_meters for short distance reps, e.g. target_meters=300 for 300m efforts lasting about 55s; target_seconds only supports whole minutes from 120 to 1800. '
            'Three sets of eight 300m reps belong in ONE group with 24 single-lap reps and set_start_laps identifying each set. '
            'Recovery between work reps must last 30-600 seconds (minimum 15s when both distance reps target at most 600m and last at most 90s) and cover at most 600m; '
            'both neighboring complete work reps must be at least 20 percent faster than recovery (work speed / recovery speed >= 1.2). '
            'Assess confidence in the observed structure, not why the athlete stopped. Do not invent missing laps or upgrade confidence to pass validation.'
        )
    if not allow_lap_structure:
        prompt["output_schema"].pop("lap_structure", None)
        task = prompt["task"]
        first, last = task.index("Prefer lap_structure"), task.index("Low zones support")
        prompt["task"] = task[:first] + task[last:]
    else:
        prompt['recording_boundaries'] = (
            'A source lap boundary is not necessarily a repetition boundary. First identify actual work/recovery transitions '
            'across the whole recording, then group the uninterrupted source laps inside each work effort into ONE rep. '
            'Repeated longer efforts separated by slower jogging can be distance intervals even when every effort is '
            'recorded as several automatic kilometre splits. Jogging recovery need not be walking; '
            'both adjacent complete efforts must be at least 20 percent faster than recovery (speed ratio >= 1.2). Consider its repeated placement, distance and duration '
            'together; do not treat each kilometre split as a separate rep or split one group solely because pace zones change. '
            'For example, three adjacent ~1000m laps, then ~450m in ~120s slower jogging, repeated four times, can be '
            'one target_meters=3000 group with reps [[1,2,3],[5,6,7],[9,10,11],[13,14,15]], recovery_laps [4,8,12]. '
            'A tiny final recording remainder may be trailing recovery, not another full repetition or invented cooldown. '
            'This is an illustrative example, not a template to force: infer the number of splits, repetitions and target '
            'from the actual source laps. Two adjacent ~1000m splits per effort can instead form 2000m reps. '
            'A continuous run of equal kilometre laps without repeated work/recovery transitions stays continuous. '
            'Missing, flat or ambiguous evidence must lower confidence; never invent recovery or increase confidence to pass validation.'
        )
    if chat_messages:
        prompt['task'] += (' In chat, leading distance groups of at least 400m may have one rep before the repeated groups. '
            'Use these for separate Main blocks before intervals, and keep measured recoveries separate. '
            'A proposed Z2 warmup is a boundary warning: reconsider whether those laps belong in Main, '
            'especially when the user asks for no warmup.')
        prompt['output_schema']['chat_reply'] = 'concise conversational reply'
        prompt['task'] = prompt['task'].replace('nominal target_meters (multiple of 50)', 'nominal target_meters (integer meters, including 190 when explicitly requested)')
    body = json.dumps({
        "model": (os.environ.get("OPENAI_MODEL") or "gpt-4o-mini").strip(),
        "temperature": 0.1,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": (
                ("Use the legacy segments/sets schema only. " if not allow_lap_structure else ("Use only lap_structure and confidence; never legacy sets/segments. " if strict_lap_structure else "")) +
                "You are a conservative running-workout structure recognizer. "
                "Return only valid JSON matching the requested schema. Use measured "
                "lap facts, never invent distances, counts or a cooldown. Prefer lap_structure "
                "for distance and time intervals: every source lap must appear exactly once, reps "
                "contain consecutive original lap numbers and groups are chronological. "
                "Use the legacy segments/sets schema only when a lap-based group "
                "proposal is unsuitable; those segments describe one repeated set. "
                "Use null for unknown recovery. If uncertain, lower confidence rather than "
                "discarding inconvenient laps or inventing a workout."
            )},
            {"role": "user", "content": json.dumps(prompt, ensure_ascii=False)},
        ],
    }).encode("utf-8")
    if strict_lap_structure:
        strict_body = json.loads(body)
        # A dedicated setting prevents an old global OPENAI_MODEL value from
        # silently keeping Garmin/FIT structure analysis on the mini model.
        strict_body['model'] = (os.environ.get('WATCH_STRUCTURE_MODEL') or 'gpt-5.4-mini').strip()
        strict_body.pop('temperature',None)
        strict_body['reasoning_effort'] = 'low'
        diagnostics['model'] = strict_body['model']
        strict_body['messages'][0]['content'] = (
            'You interpret recorded running workouts. Return valid JSON with only lap_structure and confidence, '
            'using the provided schema. Use original source lap IDs and measured evidence. '
            'Do not use legacy sets/segments or discard inconvenient laps. Confidence must be a finite number from 0 to 1.'
        )
        body = json.dumps(strict_body).encode('utf-8')
    request = Request(
        "https://api.openai.com/v1/chat/completions", data=body,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        method="POST",
    )
    # Cache only validated automatic proposals, scoped to athlete and exact
    # prompt (measurements, zones, model and instructions). Consent is checked
    # by the caller before this function is entered. Never cache failures.
    cache_key = None
    if strict_lap_structure and getattr(athlete, 'pk', None) is not None:
        digest = hashlib.sha256(body).hexdigest()
        cache_key = f'watch-structure-v1:{athlete.pk}:{digest}'
    cached = cache.get(cache_key) if cache_key else None
    diagnostics["status"] = "invalid_response"
    try:
        if cached is not None:
            data = cached
        else:
            with urlopen(request, timeout=12 if strict_lap_structure else 25) as response:
                payload = json.loads(response.read().decode("utf-8"))
            data = json.loads(payload["choices"][0]["message"]["content"])
    except (HTTPError, URLError, TimeoutError, OSError):
        diagnostics["status"] = "service_error"
        return ""
    except (ValueError, KeyError, IndexError, TypeError):
        return ""

    if not isinstance(data, dict):
        return ""
    if chat_messages:
        diagnostics['chat_reply'] = str(data.get('chat_reply') or '')[:1500]
    if "lap_structure" in data:
        if not allow_lap_structure:
            return ""
        from core.watch_ai_structure import validate_lap_structure, ValidatedDescription
        rep_zone = lambda meters, seconds: lap_zone_paces(meters, seconds * 1000, athlete)[0]
        candidate_data = data
        issues = []
        structure = validate_lap_structure(data, facts, issues=issues, rep_zone=rep_zone, requested_structure=requested_structure, allow_exact_distance=bool(chat_messages), require_no_warmup=no_warmup_requested, allow_leading_single_blocks=bool(chat_messages))
        if not structure:
            measurement_issues = []
            validate_lap_structure(data, facts, issues=measurement_issues, minimum_confidence=.5, rep_zone=rep_zone, requested_structure=requested_structure, allow_exact_distance=bool(chat_messages), require_no_warmup=no_warmup_requested, allow_leading_single_blocks=bool(chat_messages))
            issues += [issue for issue in measurement_issues if issue not in issues]
        # A bounded repair is still an AI proposal, never a local pattern fix.
        # Only server-owned validation feedback and the existing anonymous lap
        # facts go back to the same service; do not forward raw error bodies.
        if not structure and strict_lap_structure and data.get('confidence', 0) != 0:
            repair_body = json.loads(body)
            # Retain only the numeric structure fields, never arbitrary model text.
            def numeric_tree(value):
                if value is None or type(value) in (int,float):
                    return value
                if isinstance(value,list):
                    return [numeric_tree(v) for v in value[:100]]
                if isinstance(value,dict):
                    keys = {'lap_structure','confidence','warmup_laps','cooldown_laps','recovery_laps',
                            'stop_laps','continuous_main_laps','groups','target_meters','target_seconds','set_start_laps','reps'}
                    return {k:numeric_tree(v) for k,v in value.items() if k in keys}
                return None
            repair_body['messages'].append({'role':'assistant','content':json.dumps(numeric_tree(data))})
            repair_body['messages'].append({'role':'user' ,'content':
                'Your lap proposal failed validation: ' + '; '.join(issues) +
                ' Reconsider the original lap facts and return one corrected complete lap_structure. '
                'Assign every lap once, including slow transitions. Do not change measurements. '
                'Return confidence below 0.75 if the evidence is insufficient.'})
            repair_request = Request(request.full_url, data=json.dumps(repair_body).encode('utf-8'),
                headers={'Authorization':f'Bearer {api_key}','Content-Type':'application/json'}, method='POST')
            try:
                with urlopen(repair_request, timeout=6) as response:
                    repaired = json.loads(json.loads(response.read().decode('utf-8'))['choices'][0]['message']['content'])
                candidate_data = repaired
                issues = []
                structure = validate_lap_structure(repaired, facts, issues=issues, rep_zone=rep_zone, requested_structure=requested_structure, allow_exact_distance=bool(chat_messages), require_no_warmup=no_warmup_requested, allow_leading_single_blocks=bool(chat_messages))
            except (HTTPError, URLError, TimeoutError, OSError, ValueError, KeyError, IndexError, TypeError):
                pass
        if structure and cache_key:
            cache.set(cache_key, candidate_data, timeout=86400)
        diagnostics["status"] = "applied" if structure else "rejected_structure"
        if not structure and issues:
            diagnostics['reason'] = issues[0]
            # Automatic use retains the 0.75 threshold. A lower score may only
            # be offered for explicit review after identical measurement checks.
            measurement_issues = []
            review = validate_lap_structure(candidate_data, facts, minimum_confidence=.5, issues=measurement_issues, rep_zone=rep_zone, requested_structure=requested_structure, allow_exact_distance=bool(chat_messages), require_no_warmup=no_warmup_requested, allow_leading_single_blocks=bool(chat_messages))
            if not review:
                diagnostics['reason'] = ' '.join(dict.fromkeys(measurement_issues or issues))
            if review:
                diagnostics['review_structure'] = review
                diagnostics['status'] = 'review_available'
                diagnostics['reason'] = f"AI confidence {candidate_data['confidence']:.2f}. Check the proposal before selecting it."
        return ValidatedDescription(structure) if structure else ""
    if strict_lap_structure:
        return ""
    try:
        sets = int(data.get("sets") or 1)
        warmup_m = int(data["warmup_m"]) if data.get("warmup_m") is not None else 0
        cooldown_m = int(data["cooldown_m"]) if data.get("cooldown_m") is not None else 0
        confidence = float(data.get("confidence") or 0)
    except (TypeError, ValueError):
        return ""
    segments = data.get("segments")
    if not (1 <= sets <= 20 and 0 <= warmup_m <= 50000 and 0 <= cooldown_m <= 50000 and confidence >= 0.65 and isinstance(segments, list) and segments):
        return ""
    normalized = []
    main_m = 0
    for segment in segments:
        if not isinstance(segment, dict):
            return ""
        try:
            count = int(segment.get("count"))
            distance_m = int(segment.get("distance_m"))
        except (TypeError, ValueError):
            return ""
        if not (1 <= count <= 100 and 25 <= distance_m <= 5000):
            return ""
        distance_m = int(math.floor(distance_m / 50 + 0.5) * 50)
        main_m += count * distance_m
        recovery = segment.get("recovery_s")
        if recovery is not None:
            try:
                recovery = int(recovery)
            except (TypeError, ValueError):
                return ""
            if not 0 <= recovery <= 1800:
                return ""
        zone = str(segment.get("zone") or "").strip()
        if zone and not re.fullmatch(r"Z[1-5](?:>Z[1-5])?", zone):
            zone = ""
        segment_pace = str(segment.get("pace") or "").strip()
        if segment_pace and not re.fullmatch(r"\d{1,2}:\d{2}", segment_pace):
            segment_pace = ""
        normalized.append((count, distance_m, zone, segment_pace, recovery))

    # Compress a repeated sequence even when the model lists both copies as
    # one long segment list instead of setting `sets` itself.
    if len(normalized) >= 4:
        for period in range(1, len(normalized) // 2 + 1):
            if len(normalized) % period:
                continue
            repeats = len(normalized) // period
            if repeats < 2:
                continue
            keys = [(item[0], item[1], item[2]) for item in normalized]
            if all(keys[index] == keys[index % period] for index in range(len(keys))):
                normalized = normalized[:period]
                sets = max(sets, repeats)
                break

    # Never let the language model invent a work distance or repetition count
    # that is not represented by the measured laps.  A total-distance check
    # alone is insufficient: e.g. 3x500 + 5x400 + 6x200 can have the same
    # total as 3x2000 + 2x1000 while describing a completely different workout.
    observed_counts = {}
    for row in facts:
        rounded = int(row.get("rounded_50_m") or 0)
        observed_counts[rounded] = observed_counts.get(rounded, 0) + 1
    required_counts = {}
    for count, distance_m, _zone, _pace, _recovery in normalized:
        required_counts[distance_m] = required_counts.get(distance_m, 0) + count * sets
    if any(
        distance_m not in observed_counts or required > observed_counts[distance_m]
        for distance_m, required in required_counts.items()
    ):
        return ""

    # Repeated active laps of a distance are evidence the AI description must
    # account for. The previous upper-bound-only check allowed a plausible but
    # incomplete answer (e.g. 12x400 m when 14 active 400 m laps were recorded).
    observed_active_counts = {}
    for row in facts:
        rounded = int(row.get("rounded_50_m") or 0)
        zone = str(row.get("zone") or "")
        if 350 <= rounded <= 800 and re.fullmatch(r"Z[2-5]", zone):
            observed_active_counts[rounded] = observed_active_counts.get(rounded, 0) + 1
    if any(
        observed_count >= 3 and required_counts.get(distance_m, 0) < observed_count
        for distance_m, observed_count in observed_active_counts.items()
    ):
        return ""

    main_m = sum(item[0] * item[1] for item in normalized)
    measured_total = sum(float(row["distance_m"]) for row in facts)
    if warmup_m + cooldown_m + sets * main_m > measured_total + 250:
        return ""

    # Keep deterministic outer-block detection authoritative. The model is
    # useful for nested Main patterns, but it may omit a clear leading/trailing
    # easy block or select the wrong dominant distance for its boundary.
    active_positions = [
        index for index, row in enumerate(facts)
        if re.fullmatch(r"Z[2-5]", str(row.get("zone") or ""))
    ]
    fixed_wu_m = fixed_cd_m = 0
    if active_positions:
        first_active = active_positions[0]
        last_active = active_positions[-1]
        fixed_wu_m = sum(row["distance_m"] for row in facts[:first_active] if row.get("zone") == "Z1")
        trailing_z1 = []
        for row in facts[last_active + 1:]:
            if row.get("zone") != "Z1":
                break
            trailing_z1.append(row)
        long_trailing_start = next(
            (index for index, row in enumerate(trailing_z1) if row["rounded_50_m"] >= 1000),
            None,
        )
        if long_trailing_start is not None:
            trailing_z1 = trailing_z1[long_trailing_start:]
        fixed_cd_m = sum(row["distance_m"] for row in trailing_z1)
    fixed_description = type_b_description(laps, athlete)
    fixed_wu = re.search(r"WU:\s+(\d+)\s+m\s+Z1", fixed_description or "")
    fixed_cd = re.search(r"CD:\s+(\d+)\s+m\s+Z1", fixed_description or "")
    if fixed_wu_m >= 500:
        warmup_m = fixed_wu_m
    elif warmup_m < 500 and fixed_wu:
        warmup_m = int(fixed_wu.group(1))
    if fixed_cd_m >= 500:
        cooldown_m = fixed_cd_m
    elif cooldown_m < 500 and fixed_cd:
        cooldown_m = int(fixed_cd.group(1))
    if warmup_m + cooldown_m + sets * main_m > measured_total + 250:
        return ""

    measured_paces = {}
    for row in facts:
        distance_m = int(row.get("rounded_50_m") or 0)
        actual_distance_m = float(row.get("distance_m") or 0)
        duration_s = float(row.get("duration_s") or 0)
        if distance_m <= 0 or actual_distance_m <= 0 or duration_s <= 0:
            continue
        total_duration, total_distance = measured_paces.get(distance_m, (0.0, 0.0))
        measured_paces[distance_m] = (total_duration + duration_s, total_distance + actual_distance_m)

    def segment_text(item):
        count, distance_m, zone, segment_pace, recovery = item
        text = f"{count}×{distance_m} m" if count != 1 else f"{distance_m} m"
        if zone:
            text += f" {zone}"
        if not segment_pace and distance_m in measured_paces:
            total_duration, total_distance = measured_paces[distance_m]
            segment_pace = pace(total_duration, total_distance)
        if segment_pace:
            text += f" ({segment_pace})"
        if recovery is not None:
            text += f" p{recovery}"
        return text

    main_text = " + ".join(segment_text(item) for item in normalized)
    if sets > 1:
        main_text = f"{sets}×({main_text})"
    parts = [f"WU: {int(math.floor(warmup_m / 50 + 0.5) * 50)} m Z1" if warmup_m >= 500 else "WU: none"]
    parts.append("Main: " + main_text)
    parts.append(f"CD: {int(math.floor(cooldown_m / 50 + 0.5) * 50)} m Z1" if cooldown_m >= 500 else "CD: none")
    diagnostics["status"] = "applied"
    return " · ".join(parts)


def _watch_t_key(label):
    normalized = str(label or "").strip().upper()
    return normalized if normalized.startswith("T") else ""


def sample_rows(exercise, interval):
    source = exercise.get("samples")
    streams = source.get("samples", []) if isinstance(source, dict) else []
    selected = {}
    metadata = []
    for stream in streams if isinstance(streams, list) else []:
        if not isinstance(stream, dict):
            continue
        kind = str(stream.get("type", "")).upper()
        rate = number(stream.get("intervalMillis"))
        values = stream.get("values")
        if rate is None or rate <= 0 or not isinstance(values, list):
            continue
        metadata.append(f"{kind}: {len(values)} values, interval {display(rate / 1000)} s")
        if kind in {"DISTANCE", "HEART_RATE"}:
            selected[kind] = (rate, values)
    end = max(((len(values) - 1) * rate for rate, values in selected.values()), default=0)
    recorded_duration = number(exercise.get("durationMillis"))
    if recorded_duration is not None and recorded_duration >= 0:
        end = min(end, recorded_duration)
    # Only actual sample timestamps are shown: no interpolation or carry-forward.
    def at(kind, milliseconds):
        if kind not in selected:
            return "NA"
        rate, values = selected[kind]
        index = milliseconds / rate
        rounded = round(index)
        if abs(index - rounded) > 1e-8 or rounded < 0 or rounded >= len(values):
            return "NA"
        return number(values[rounded])
    rows = []
    previous_distance = None
    if selected:
        for t in range(0, min(int(end), 86400000) + 1, interval * 1000):
            distance = number(at("DISTANCE", t))
            delta = distance - previous_distance if distance is not None and previous_distance is not None else None
            rows.append({"time": display(t / 1000), "distance": display(distance),
                         "hr": display(at("HEART_RATE", t)),
                         "pace": pace(interval, delta) if t > 0 else "NA"})
            # Missing rows break the segment: never bridge an unknown distance.
            previous_distance = distance
    return rows, metadata, end > 86400000


def polar_sport_id(item, session=None):
    sport = item.get("sport") if isinstance(item, dict) else None
    if not sport and isinstance(session, dict):
        sport = session.get("sport")
    return str(sport.get("id", "")) if isinstance(sport, dict) else ""


def translate(payload, interval, mode="A", athlete=None):
    sessions = payload if isinstance(payload, list) else next(
        (payload[key] for key in ("trainingSessions", "training-sessions", "sessions")
         if isinstance(payload, dict) and isinstance(payload.get(key), list)), [])
    result = []
    for session in sessions:
        if not isinstance(session, dict):
            continue
        parts = []
        exercises = session.get("exercises") or []
        # Session-level laps get their own section to avoid duplicating exercises.
        items = ([session] if session.get("laps") or not exercises else []) + [
            item for item in exercises if isinstance(item, dict)]
        for index, item in enumerate(items, 1):
            if mode == "A" and polar_sport_id(item, session) not in {"", "1"}:
                continue
            laps = item.get("laps") or {}
            laps = laps if isinstance(laps, dict) else {}
            manual_laps = laps.get("laps") or laps.get("manualLaps") or laps.get("manual-laps") or []
            rows, metadata, truncated = sample_rows(item, interval)
            processed, processing_notes = [], []
            if mode == "C":
                from .polar_processing import processed_rows
                processed, processing_notes = processed_rows(item, rows)
            description = ""
            description_label = ""
            if mode == "A":
                if manual_laps:
                    description = type_a_description(manual_laps, athlete)
                    description_label = "Generated description"
                else:
                    description = type_a_general_description(item, athlete)
                    description_label = "General description"
            parts.append({"index": index, "sport": item.get("sport", ""),
                          "distance": display(item.get("distanceMeters")),
                          "duration": duration(item.get("durationMillis")),
                          "manual": lap_rows(manual_laps, athlete, item.get("samples")),
                          "auto": lap_rows(laps.get("autoLaps") or laps.get("auto-laps"), athlete, item.get("samples")),
                          "description": description, "description_label": description_label,
                          "training_fields": type_a_training_fields(description) if mode == "A" else {},
                          "watch_loads": type_a_watch_loads(item, athlete) if mode == "A" else [],
                          "samples": rows, "metadata": metadata, "truncated": truncated,
                          "processed": processed, "processing_notes": processing_notes})
        if mode == "A" and not parts:
            continue
        result.append({"name": session.get("name") or "Training session",
                       "start": session.get("startTime", ""),
                       "distance": display(session.get("distanceMeters")),
                       "duration": duration(session.get("durationMillis")), "parts": parts})
    return result


def translate_model_b(payload, interval, athlete=None, *, allow_ai=True, allow_lap_structure=False, requested_structure=None, chat_messages=None):
    """Model B starts as an isolated copy of the stable Model A output.

    Keep this entry point separate so future Model B recognition changes do
    not require changing the Model A implementation used by Polar Integration.
    """
    result = translate(payload, interval, mode="A", athlete=athlete)
    sessions = payload if isinstance(payload, list) else next(
        (payload[key] for key in ("trainingSessions", "training-sessions", "sessions")
         if isinstance(payload, dict) and isinstance(payload.get(key), list)), []
    )
    for session_result, session in zip(result, sessions):
        if not isinstance(session, dict):
            continue
        exercises = session.get("exercises") or []
        items = ([session] if session.get("laps") or not exercises else []) + [
            item for item in exercises if isinstance(item, dict)
        ]
        result_parts = session_result.get("parts") or []
        result_index = 0
        for item in items:
            if not isinstance(item, dict) or polar_sport_id(item, session) not in {"", "1"}:
                continue
            if result_index >= len(result_parts):
                break
            laps_container = item.get("laps") or {}
            laps_container = laps_container if isinstance(laps_container, dict) else {}
            manual_laps = laps_container.get("laps") or laps_container.get("manualLaps") or laps_container.get("manual-laps") or []
            if manual_laps:
                diagnostics = {'status':'consent_required'}
                description = (_model_b_ai_description(manual_laps, athlete, allow_lap_structure=allow_lap_structure, diagnostics=diagnostics, strict_lap_structure=allow_lap_structure, requested_structure=requested_structure, chat_messages=chat_messages) if allow_ai else "") or type_b_description(manual_laps, athlete)
                if allow_lap_structure:
                    result_parts[result_index]['chat_reply'] = diagnostics.get('chat_reply', '')
                    result_parts[result_index]['ai_structure_status'] = diagnostics['status']
                    result_parts[result_index]['ai_structure_reason'] = diagnostics.get('reason','')
                    result_parts[result_index]['ai_structure_model'] = diagnostics.get('model','')
                    if diagnostics.get('review_structure'):
                        result_parts[result_index]['review_lap_structure'] = diagnostics['review_structure']
                if description:
                    if getattr(description, "structure", None):
                        result_parts[result_index]["validated_lap_structure"] = description.structure
                    result_parts[result_index]["description"] = str(description)
                    result_parts[result_index]["description_label"] = "Generated description"
                    result_parts[result_index]["training_fields"] = type_a_training_fields(description)
            result_index += 1
    return result


@login_required
@require_http_methods(["GET", "POST"])
def polar_raw_view(request):
    if not _polar_access_allowed(request):
        from django.shortcuts import redirect
        return redirect("dashboard")
    targets = [target for target in _polar_targets_for_user(request.user)
               if target.get("athlete") is not None or target.get("user") == request.user]
    data = request.POST if request.method == "POST" else request.GET
    key = data.get("polar_target") or request.session.get("polar_target")
    target = next((item for item in targets if item["key"] == key), targets[0] if targets else None)
    context = {"targets": targets, "selected": target, "mode": data.get("mode", "A"),
               "date": data.get("date", (timezone.localdate() - timedelta(days=1)).isoformat()),
               "interval": data.get("interval", "5")}
    if context["mode"] not in {"A", "B", "C", "D"}:
        context["mode"] = "A"
    if context["mode"] == "D" and request.method == "POST" and key and not any(item["key"] == key for item in targets):
        context["error"] = "Unknown athlete"
        return render(request, "core/polar_raw.html", context)
    if context["mode"] == "D":
        from .polar_analysis_settings import analysis_configuration
        context.update(analysis_configuration(request, target, {}, submitting=False))
        if request.method == "POST":
            for field in context["hr_fields"]:
                field["value"] = data.get(f"hr_upper_{field['index']}", field["value"])
        try:
            context.update(analysis_configuration(request, target, data))
        except ValueError as exc:
            context["error"] = str(exc)
            return render(request, "core/polar_raw.html", context)
    if request.method == "POST":
        try:
            day = date.fromisoformat(context["date"])
            interval = int(context["interval"])
            if not 1 <= interval <= 3600:
                raise ValueError
            if key and not any(item["key"] == key for item in targets):
                raise ValueError("Unknown athlete")
            connection = target.get("connection") if target else None
            if not connection or not connection.v4_access_token:
                raise ValueError("Connect Polar v4 for this athlete first.")
            headers = {"Accept": "application/json", "Authorization": "Bearer " + connection.v4_access_token}
            refreshed_once = False
            # Start with the date format accepted by the existing v4 laps test.
            formats = ["{day}T00:00:00", "{day}T00:00:00.000",
                       "{day}T00:00:00Z", "{day}T00:00:00.000Z",
                       "{day}T00:00:00+00:00", "{day}T00:00:00.000+00:00",
                       "{day}T00:00:00+0000", "{day}"]
            for date_format in formats:
                params = [("from", date_format.format(day=day.isoformat())),
                          ("to", date_format.format(day=(day + timedelta(days=1)).isoformat()))]
                params.extend(("features", feature) for feature in ["laps", "samples", "pause-times", "statistics"])
                url = POLAR_V4_TRAINING_SESSIONS_URL + "?" + urlencode(params)
                status, payload = _polar_json_request(url, headers=headers)
                if status == 401 and not refreshed_once:
                    refreshed_once = True
                    refreshed, error = _refresh_polar_v4_token(connection)
                    if not refreshed:
                        raise ValueError(error)
                    headers["Authorization"] = "Bearer " + connection.v4_access_token
                    status, payload = _polar_json_request(url, headers=headers)
                detail = ""
                if isinstance(payload, dict):
                    detail = str(payload.get("error_description") or payload.get("message") or payload.get("error") or "")
                date_error = status == 400 and any(key in detail.lower() for key in ["from", "to", "date", "time"])
                if not date_error:
                    break
            if status != 200:
                detail = detail.replace(connection.v4_access_token, "[redacted]")[:600]
                message = f"Polar returned HTTP {status}."
                if detail:
                    message += " " + detail
                if status in {401, 403}:
                    message += " Reconnect Polar v4 if authorization has expired."
                raise ValueError(message)
            if context["mode"] == "D":
                from .polar_analysis import analyze_payload, ai_interpretation
                context["analyses"] = analyze_payload(payload, target.get("athlete") if target else None, context["hr_bounds"])
                if data.get("ai_interpretation") == "on" and context["analyses"]:
                    context["ai_text"], context["ai_error"] = ai_interpretation(context["analyses"])
            context.update(results=translate(payload, interval, context["mode"], target.get("athlete") if target else None) if context["mode"] != "D" else [], fetched=True,
                           raw=json.dumps(payload, ensure_ascii=False, indent=2))
        except (ValueError, RuntimeError) as exc:
            context["error"] = str(exc) or "Choose a valid date and an interval between 1 and 3600 seconds."
    return render(request, "core/polar_raw.html", context)
