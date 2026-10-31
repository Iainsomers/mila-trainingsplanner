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


def lap_data(item):
    summary = item.get("summary") or {}
    start = number(summary.get("startTimeInSeconds"))
    distance = number(summary.get("distanceInMeters"))
    duration = number(summary.get("durationInSeconds"))
    if start is None or distance is None or duration is None or distance < 0 or duration <= 0:
        raise ValueError("Missing activity totals")
    samples = item.get("samples") or []
    laps = item.get("laps") or []
    if not isinstance(samples, list) or not isinstance(laps, list) or len(samples) > 100000 or len(laps) > 10000:
        raise ValueError("Invalid activity details")
    points = sorted((number(sample.get("startTimeInSeconds")), number(sample.get("totalDistanceInMeters")))
                    for sample in samples if isinstance(sample, dict)
                    and number(sample.get("startTimeInSeconds")) is not None
                    and number(sample.get("totalDistanceInMeters")) is not None)
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
        if hr_end > hr_start:
            lap["avg_heart_rate"] = (hr_sums[hr_end] - hr_sums[hr_start]) / (hr_end - hr_start)
        normalized_laps.append(lap)
    if len(normalized_laps) != len(boundaries) or (boundaries and boundaries[0] != start):
        normalized_laps = []  # Do not offer an incomplete activity as a complete workout.
    return {"laps": normalized_laps, "heart_rate_samples": heart_samples,
            "total_distance_m": distance, "total_elapsed_s": end - start}
