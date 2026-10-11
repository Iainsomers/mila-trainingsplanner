"""Read-only Polar v4 inspection; never imports or modifies workouts."""
import json
import math
from datetime import date, timedelta
from urllib.parse import urlencode

from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from .coach import (_polar_targets_for_user, _polar_json_request,
                    _refresh_polar_v4_token, POLAR_V4_TRAINING_SESSIONS_URL)


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


def lap_rows(laps):
    return [{"index": i, "distance": display(lap.get("distanceMeters")),
             "duration": duration(lap.get("durationMillis")),
             "pace": pace(number(lap.get("durationMillis")) / 1000 if number(lap.get("durationMillis")) is not None else None, lap.get("distanceMeters")),
             "elapsed": duration(lap.get("splitTimeMillis"))}
            for i, lap in enumerate(laps if isinstance(laps, list) else [], 1)
            if isinstance(lap, dict)]


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


def translate(payload, interval, mode="A"):
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
            laps = item.get("laps") or {}
            laps = laps if isinstance(laps, dict) else {}
            rows, metadata, truncated = sample_rows(item, interval)
            processed, processing_notes = [], []
            if mode == "C":
                from .polar_processing import processed_rows
                processed, processing_notes = processed_rows(item, rows)
            parts.append({"index": index, "sport": item.get("sport", ""),
                          "distance": display(item.get("distanceMeters")),
                          "duration": duration(item.get("durationMillis")),
                          "manual": lap_rows(laps.get("laps") or laps.get("manualLaps") or laps.get("manual-laps")),
                          "auto": lap_rows(laps.get("autoLaps") or laps.get("auto-laps")),
                          "samples": rows, "metadata": metadata, "truncated": truncated,
                          "processed": processed, "processing_notes": processing_notes})
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
            context.update(results=translate(payload, interval, context["mode"]) if context["mode"] != "D" else [], fetched=True,
                           raw=json.dumps(payload, ensure_ascii=False, indent=2))
        except (ValueError, RuntimeError) as exc:
            context["error"] = str(exc) or "Choose a valid date and an interval between 1 and 3600 seconds."
    return render(request, "core/polar_raw.html", context)
