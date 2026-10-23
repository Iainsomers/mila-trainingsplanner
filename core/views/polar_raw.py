"""Read-only Polar v4 inspection; never imports or modifies workouts."""
import json
import math
import os
import re
from datetime import date, timedelta
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from .coach import (
    POLAR_V4_TRAINING_SESSIONS_URL,
    _closest_watch_label,
    _polar_json_request,
    _polar_targets_for_user,
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


def lap_average_hr(lap, start_ms, end_ms, samples):
    if not isinstance(samples, dict):
        return "NA"
    streams = samples.get("samples")
    if not isinstance(streams, list):
        return "NA"
    stream = next((item for item in streams if isinstance(item, dict) and str(item.get("type", "")).upper() == "HEART_RATE"), None)
    if not stream:
        return "NA"
    interval_ms = number(stream.get("intervalMillis"))
    values = stream.get("values")
    if interval_ms is None or interval_ms <= 0 or not isinstance(values, list):
        return "NA"
    try:
        start_ms = float(start_ms or 0)
        end_ms = float(end_ms or 0)
    except (TypeError, ValueError):
        return "NA"
    if end_ms <= start_ms:
        return "NA"
    heart_rates = []
    for index, value in enumerate(values):
        timestamp = index * interval_ms
        if timestamp < start_ms or timestamp >= end_ms:
            continue
        bpm = number(value)
        if bpm is not None and bpm > 0:
            heart_rates.append(bpm)
    if not heart_rates:
        return "NA"
    return display(math.floor(sum(heart_rates) / len(heart_rates) + 0.5))


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
        rows.append({
            "index": index,
            "distance": display(lap.get("distanceMeters")),
            "distance_rounded_50": distance_rounded_to_50(lap.get("distanceMeters")),
            "duration": duration(lap.get("durationMillis")),
            "average_hr": lap_average_hr(lap, start_ms, end_ms, samples),
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
    for index, lap in enumerate(source_laps, 1):
        if not isinstance(lap, dict):
            continue
        distance_m = number(lap.get("distanceMeters"))
        duration_ms = number(lap.get("durationMillis"))
        if distance_m is None or distance_m <= 0 or duration_ms is None or duration_ms <= 0:
            continue
        z_pace, t_pace = lap_zone_paces(distance_m, duration_ms, athlete)
        zone = z_pace[1:] if z_pace.startswith("Z") and z_pace[1:].isdigit() else "1"
        rows.append({
            "index": index,
            "distance_m": distance_m,
            "seconds": duration_ms / 1000.0,
            "zone": zone,
            "t_key": _watch_t_key(t_pace),
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
            "segment": segment,
            "zone": row["zone"],
            "meters": row["distance_m"],
            "seconds": row["seconds"],
            "t_key": row["t_key"],
            "race": False,
        })
    return loads


def type_b_description(laps, athlete=None):
    """Model B: recognize repeated distance reps split by short/long recoveries."""
    if not isinstance(laps, list):
        return ""
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
    groups = [group for group in groups if len(group) >= 3]
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
    cooldown_rows = [row for row in rows if row["index"] > candidate_rows[-1]["index"]]
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


def _model_b_ai_description(laps, athlete=None):
    """Ask the language model to identify nested interval structure for Watch B.

    The model only proposes structure from compact numeric lap facts.  The
    server validates the numeric ranges and builds the displayed description,
    so a model response cannot alter measured distance or time calculations.
    """
    api_key = (os.environ.get("OPENAI_API_KEY") or "").strip()
    if not api_key or not isinstance(laps, list):
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
        })
        elapsed_s += duration_ms / 1000
    if len(facts) < 6:
        return ""

    prompt = {
        "task": (
            "Recognize the performed running workout from manual laps. Find nested "
            "repeated structures such as 2 sets of (3x500m + 5x400m + 6x200m). "
            "Short slow laps are recoveries, not work. Include only clearly observed "
            "warmup, main work and cooldown. Do not force every lap into a block."
        ),
        "laps": facts,
        "output_schema": {
            "warmup_m": "integer or null",
            "cooldown_m": "integer or null",
            "sets": "positive integer",
            "segments": [
                {"count": "positive integer", "distance_m": "integer", "zone": "string", "pace": "mm:ss", "recovery_s": "integer or null"}
            ],
            "confidence": "number from 0 to 1",
        },
    }
    body = json.dumps({
        "model": (os.environ.get("OPENAI_MODEL") or "gpt-4o-mini").strip(),
        "temperature": 0.1,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": (
                "You are a conservative running-workout structure recognizer. "
                "Return only valid JSON matching the requested schema. Use measured "
                "lap facts, never invent distances, counts or a cooldown. The segments "
                "describe one repeated set; sets describes how many times that sequence "
                "is repeated. Use null for unknown recovery."
            )},
            {"role": "user", "content": json.dumps(prompt, ensure_ascii=False)},
        ],
    }).encode("utf-8")
    request = Request(
        "https://api.openai.com/v1/chat/completions", data=body,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=25) as response:
            payload = json.loads(response.read().decode("utf-8"))
        data = json.loads(payload["choices"][0]["message"]["content"])
    except (HTTPError, URLError, TimeoutError, OSError, ValueError, KeyError, IndexError, TypeError):
        return ""

    if not isinstance(data, dict):
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
    measured_total = sum(float(row["distance_m"]) for row in facts)
    if warmup_m + cooldown_m + sets * main_m > measured_total + 250:
        return ""

    # Keep the deterministic WU/CD boundary detection authoritative.  The
    # model is useful for nested Main patterns, but it may conservatively omit
    # a long leading or trailing easy block even when the laps make it clear.
    fixed_description = type_b_description(laps, athlete)
    fixed_wu = re.search(r"WU:\s+(\d+)\s+m\s+Z1", fixed_description or "")
    fixed_cd = re.search(r"CD:\s+(\d+)\s+m\s+Z1", fixed_description or "")
    if warmup_m < 500 and fixed_wu:
        warmup_m = int(fixed_wu.group(1))
    if cooldown_m < 500 and fixed_cd:
        cooldown_m = int(fixed_cd.group(1))
    if warmup_m + cooldown_m + sets * main_m > measured_total + 250:
        return ""

    def segment_text(item):
        count, distance_m, zone, segment_pace, recovery = item
        text = f"{count}×{distance_m} m"
        if zone:
            text += f" {zone}"
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


def translate_model_b(payload, interval, athlete=None):
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
                description = _model_b_ai_description(manual_laps, athlete) or type_b_description(manual_laps, athlete)
                if description:
                    result_parts[result_index]["description"] = description
                    result_parts[result_index]["description_label"] = "Generated description"
                    result_parts[result_index]["training_fields"] = type_a_training_fields(description)
            result_index += 1
    return result


@login_required
@require_http_methods(["GET", "POST"])
def polar_raw_view(request):
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
