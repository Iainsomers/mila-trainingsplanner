"""Reduce Garmin Activity Details to measured lap facts, without GPS or tokens."""
from datetime import datetime, timezone
import math
import bisect


def number(value):
    if isinstance(value, bool):
        return None
    try:
        result = float(value)
    except (ValueError, TypeError):
        return None
    return result if math.isfinite(result) else None


def activity_metrics(summary, heart_samples):
    metrics = {'heart_rate_sample_count':len(heart_samples)}
    sport = summary.get('activityType')
    if isinstance(sport,str) and sport.strip():
        metrics['sport'] = sport.strip()[:100]
    for source,key,upper in (('averageHeartRateInBeatsPerMinute','average_hr',300),
                             ('maxHeartRateInBeatsPerMinute','max_hr',300),
                             ('activeKilocalories','active_kcal',100000)):
        value = number(summary.get(source))
        if value is not None and 0 < value < upper:
            metrics[key] = round(value,1)
    if heart_samples:
        hrs = [point['heart_rate'] for point in heart_samples]
        if 'average_hr' not in metrics:
            metrics['sample_average_hr'] = round(sum(hrs)/len(hrs),1)
        if 'max_hr' not in metrics:
            metrics['sample_max_hr'] = max(hrs)
    return metrics


def lap_data(item):
    summary = item.get("summary") or {}
    start = number(summary.get("startTimeInSeconds"))
    distance = number(summary.get("distanceInMeters"))
    duration = number(summary.get("durationInSeconds"))
    if start is None or duration is None or (distance is not None and distance < 0) or duration <= 0:
        raise ValueError("Missing activity totals")
    samples = item.get("samples") or []
    laps = item.get("laps") or []
    if not isinstance(samples, list) or not isinstance(laps, list) or len(samples) > 100000 or len(laps) > 10000:
        raise ValueError("Invalid activity details")
    if distance is None:
        return time_only_data(summary, samples, laps, start, duration)
    points = sorted((number(sample.get("startTimeInSeconds")), number(sample.get("totalDistanceInMeters")))
                    for sample in samples if isinstance(sample, dict)
                    and number(sample.get("startTimeInSeconds")) is not None
                    and number(sample.get("totalDistanceInMeters")) is not None)
    timing_points = {}
    for field in ("clockDurationInSeconds", "timerDurationInSeconds", "movingDurationInSeconds"):
        timing_points[field] = sorted((number(sample.get("startTimeInSeconds")), number(sample.get(field)))
            for sample in samples if isinstance(sample, dict)
            and number(sample.get("startTimeInSeconds")) is not None and number(sample.get(field)) is not None)
        if any(right[1] < left[1] for left, right in zip(timing_points[field], timing_points[field][1:])):
            timing_points[field] = []

    def timing_at(field, timestamp):
        values = timing_points[field]
        index = bisect.bisect_left(values, (timestamp, float("-inf")))
        if index < len(values) and values[index][0] == timestamp:
            return values[index][1]
        if index == 0 or index >= len(values):
            return None
        left, right = values[index - 1], values[index]
        if right[1] < left[1]:
            return None  # A reset counter cannot provide a reliable duration.
        return left[1] + (right[1] - left[1]) * (timestamp - left[0]) / (right[0] - left[0])
    end = max(start + duration, points[-1][0] if points else start + duration)
    boundaries = sorted({number(lap.get("startTimeInSeconds")) for lap in laps if isinstance(lap, dict)
                         and number(lap.get("startTimeInSeconds")) is not None
                         and start <= number(lap.get("startTimeInSeconds")) < end})

    def meters_at(timestamp):
        if timestamp == start:
            return 0.0
        if timestamp == end:
            return distance
        index = bisect.bisect_left(points, (timestamp, float("-inf")))
        if index < len(points) and points[index][0] == timestamp:
            return points[index][1]
        if index == 0 or index >= len(points):
            return None
        left, right = points[index - 1], points[index]
        return left[1] + (right[1] - left[1]) * (timestamp - left[0]) / (right[0] - left[0])

    normalized_laps = []
    heart_samples = []
    for sample in samples:
        if not isinstance(sample, dict):
            continue
        timestamp, hr = number(sample.get("startTimeInSeconds")), number(sample.get("heartRate"))
        if timestamp is not None and start <= timestamp <= end and hr is not None and 0 < hr < 300:
            heart_samples.append({"timestamp": datetime.fromtimestamp(timestamp, timezone.utc).isoformat(), "heart_rate": hr})
    hr_points = sorted((datetime.fromisoformat(sample["timestamp"]).timestamp(), sample["heart_rate"]) for sample in heart_samples)
    hr_times = [point[0] for point in hr_points]
    hr_sums = [0.0]
    for _, hr_value in hr_points:
        hr_sums.append(hr_sums[-1] + hr_value)
    for index, timestamp in enumerate(boundaries):
        lap_end = boundaries[index + 1] if index + 1 < len(boundaries) else end
        first, last = meters_at(timestamp), meters_at(lap_end)
        if first is None or last is None or last < first:
            continue  # Incomplete sample coverage must not invent a lap distance.
        hr_start, hr_end = bisect.bisect_left(hr_times, timestamp), bisect.bisect_left(hr_times, lap_end)
        lap = {"start_time": datetime.fromtimestamp(timestamp, timezone.utc).isoformat(),
               "distance": last - first, "elapsed_time": lap_end - timestamp}
        for field, key in (("clockDurationInSeconds", "clock_time"),
                           ("timerDurationInSeconds", "timer_time"),
                           ("movingDurationInSeconds", "moving_time")):
            first_time, last_time = timing_at(field, timestamp), timing_at(field, lap_end)
            if first_time is not None and last_time is not None and 0 <= last_time - first_time <= lap_end - timestamp + 1:
                lap[key] = last_time - first_time
        if "timer_time" in lap:
            lap["paused_time"] = max(0, lap["elapsed_time"] - lap["timer_time"])
        if hr_end > hr_start:
            lap["avg_heart_rate"] = (hr_sums[hr_end] - hr_sums[hr_start]) / (hr_end - hr_start)
        normalized_laps.append(lap)
    if not boundaries:
        lap_status = "no_lap_markers"
    elif len(normalized_laps) != len(boundaries) or boundaries[0] != start:
        lap_status = "incomplete_lap_coverage"
        normalized_laps = []  # Do not offer an incomplete activity as a complete workout.
    else:
        lap_status = "available"
    # Garmin summary duration is the recorded activity time; timestamps can
    # span additional stopped time. Never distribute that difference over laps.
    timer_total = number(summary.get('timerDurationInSeconds'))
    if timer_total is None:
        timer_total = duration
    if not 0 < timer_total <= end - start + 1:
        timer_total = None
    if len(normalized_laps) == 1 and timer_total is not None and 'timer_time' not in normalized_laps[0]:
        normalized_laps[0]['timer_time'] = timer_total
        normalized_laps[0]['paused_time'] = max(0, normalized_laps[0]['elapsed_time'] - timer_total)
    return {"total_timer_s": timer_total, "laps": normalized_laps, "heart_rate_samples": heart_samples,
            "total_distance_m": distance, "total_elapsed_s": end - start,
            "activity_metrics": activity_metrics(summary, heart_samples),
            "lap_data_status": lap_status, "received_lap_count": len(laps),
            "received_sample_count": len(samples)}


def time_only_data(summary, samples, laps, start, duration):
    """Keep wall-clock boundaries separate from active time, including pauses."""
    fields = ("clockDurationInSeconds", "timerDurationInSeconds", "movingDurationInSeconds")
    timing = []
    heart = []
    timestamps = []
    for sample in samples:
        if not isinstance(sample, dict):
            continue
        timestamp = number(sample.get("startTimeInSeconds"))
        if timestamp is None or timestamp < start:
            continue
        timestamps.append(timestamp)
        point = {"startTimeInSeconds": timestamp}
        for field in fields:
            value = number(sample.get(field))
            if value is not None and value >= 0:
                point[field] = value
        if len(point) > 1:
            timing.append(point)
        hr = number(sample.get("heartRate"))
        if hr is not None and 0 < hr < 300:
            heart.append({"timestamp": datetime.fromtimestamp(timestamp, timezone.utc).isoformat(),
                          "heart_rate": hr})
    markers = [number(lap.get("startTimeInSeconds")) if isinstance(lap, dict) else None
               for lap in laps]
    boundaries = sorted({value for value in markers if value is not None and value >= start})
    clock = number(summary.get("clockDurationInSeconds"))
    end = max([start + duration] + timestamps + ([start + clock] if clock is not None and clock > 0 else []))
    timer_total = number(summary.get("timerDurationInSeconds"))
    if timer_total is None:
        timer_total = duration
    counters = {}
    for field in fields:
        values = sorted((point["startTimeInSeconds"], point[field])
                        for point in timing if field in point)
        # Conflicting duplicates and reset counters must never be interpolated.
        if any(b[1] < a[1] or (a[0] == b[0] and a[1] != b[1])
               for a, b in zip(values, values[1:])):
            values = []
        counters[field] = sorted(set(values))

    def at(field, timestamp):
        values = counters[field]
        index = bisect.bisect_left(values, (timestamp, float("-inf")))
        if index < len(values) and values[index][0] == timestamp:
            return values[index][1]
        if index == 0 or index == len(values):
            return None
        left, right = values[index - 1], values[index]
        # Sparse samples spanning stopped time cannot locate a lap's timer.
        wall = right[0] - left[0]
        if abs(right[1] - left[1] - wall) > 1e-6:
            return None
        return left[1] + timestamp - left[0]

    timer_present = any("timerDurationInSeconds" in point for point in timing)
    timer_invalid = timer_present and not counters["timerDurationInSeconds"]
    hr_points = sorted((datetime.fromisoformat(point["timestamp"]).timestamp(), point["heart_rate"])
                       for point in heart)
    hr_times = [point[0] for point in hr_points]
    hr_sums = [0.0]
    for _, value in hr_points:
        hr_sums.append(hr_sums[-1] + value)

    def mean_hr(first, last):
        left, right = bisect.bisect_left(hr_times, first), bisect.bisect_left(hr_times, last)
        return (hr_sums[right]-hr_sums[left])/(right-left) if right > left else None

    valid = (bool(boundaries) and boundaries[0] == start and boundaries[-1] < end
             and len(boundaries) == len(markers)
             and all(value is not None and value >= start for value in markers)
             and 0 < timer_total <= end - start + 1)
    paused = abs(end - start - timer_total) > 1
    normalized = []
    reason = ""
    if timer_invalid:
        valid = False
        reason = "timer_data_unavailable"
    if valid:
        for index, timestamp in enumerate(boundaries):
            lap_end = boundaries[index + 1] if index + 1 < len(boundaries) else end
            wall = lap_end - timestamp
            first, last = at("timerDurationInSeconds", timestamp), at("timerDurationInSeconds", lap_end)
            active = last - first if first is not None and last is not None else None
            if active is None and len(boundaries) == 1:
                active = timer_total
            if active is None and not paused:
                active = wall
            if active is None or not 0 < active <= wall + 1:
                valid = False
                reason = "timer_data_unavailable"
                break
            tail_start = max(timestamp, lap_end - max(15, active * .1))
            normalized.append({"start_time": datetime.fromtimestamp(timestamp, timezone.utc).isoformat(),
                               "distance": None, "elapsed_time": active, "timer_time": active,
                               "clock_time": wall, "paused_time": max(0, wall-active),
                               "avg_heart_rate": mean_hr(timestamp, lap_end) if wall-active <= 1 else None,
                               "hr_tail": mean_hr(tail_start, lap_end) if wall-active <= 1 else None})
        if valid and abs(sum(lap["timer_time"] for lap in normalized)-timer_total) > 1:
            valid = False
            reason = "inconsistent_timer_total"
    if not valid:
        normalized = []
    status = ("no_lap_markers" if not laps else "available_time_only" if valid
              else reason or "incomplete_lap_coverage")
    return {"laps": normalized, "heart_rate_samples": heart,
            "total_distance_m": None, "total_elapsed_s": end-start, "total_timer_s": timer_total,
            "activity_metrics": activity_metrics(summary, heart), "lap_data_status": status,
            "received_lap_count": len(laps), "received_sample_count": len(samples),
            "time_source": {"start": start, "duration": duration, "clock_duration": clock,
                            "timer_duration": number(summary.get("timerDurationInSeconds")),
                            "lap_starts": markers, "sample_times": timestamps, "counters": timing}}
