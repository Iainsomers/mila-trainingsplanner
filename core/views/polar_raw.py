"""Read-only Polar v4 inspection; never imports or modifies workouts."""
import json
import math
from datetime import date, timedelta
from urllib.parse import urlencode

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


def lap_rows(laps, athlete=None):
    rows = []
    for index, lap in enumerate(laps if isinstance(laps, list) else [], 1):
        if not isinstance(lap, dict):
            continue
        z_pace, t_pace = lap_zone_paces(
            lap.get("distanceMeters"), lap.get("durationMillis"), athlete
        )
        rows.append({
            "index": index,
            "distance": display(lap.get("distanceMeters")),
            "distance_rounded_50": distance_rounded_to_50(lap.get("distanceMeters")),
            "duration": duration(lap.get("durationMillis")),
            "pace": pace(
                number(lap.get("durationMillis")) / 1000
                if number(lap.get("durationMillis")) is not None else None,
                lap.get("distanceMeters"),
            ),
            "z_pace": z_pace,
            "t_pace": t_pace,
            "elapsed": duration(lap.get("splitTimeMillis")),
        })
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
    if not work_positions:
        return "No clear main section detected."

    first_work, last_work = work_positions[0], work_positions[-1]
    warmup = parsed[0] if first_is_warmup and first_work > 0 else None

    work_rows = [parsed[index] for index in work_positions]
    groups = []
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
        if recoveries:
            average = math.floor(sum(recoveries) / len(recoveries) + 0.5)
            segment += f" p{average}"
        segment_texts.append(segment)

    trailing = parsed[last_work + 1:]
    cooldown_distance = sum(row["distance_m"] for row in trailing if row["zone"] == 1)
    cooldown = cooldown_distance >= 1000 and trailing and all(row["zone"] == 1 for row in trailing)
    parts = [f"WU: {warmup['rounded_m']} m {warmup['zone_label']}" if warmup else "WU: none"]
    parts.append("Main: " + " + ".join(segment_texts))
    parts.append(f"CD: {int(math.floor(cooldown_distance / 50 + 0.5) * 50)} m Z1" if cooldown else "CD: none")
    return " · ".join(parts)


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
            parts.append({"index": index, "sport": item.get("sport", ""),
                          "distance": display(item.get("distanceMeters")),
                          "duration": duration(item.get("durationMillis")),
                          "manual": lap_rows(manual_laps, athlete),
                          "auto": lap_rows(laps.get("autoLaps") or laps.get("auto-laps"), athlete),
                          "description": type_a_description(manual_laps, athlete) if mode == "A" and manual_laps else "",
                          "samples": rows, "metadata": metadata, "truncated": truncated,
                          "processed": processed, "processing_notes": processing_notes})
        if mode == "A" and not parts:
            continue
        result.append({"name": session.get("name") or "Training session",
                       "start": session.get("startTime", ""),
                       "distance": display(session.get("distanceMeters")),
                       "duration": duration(session.get("durationMillis")), "parts": parts})
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
