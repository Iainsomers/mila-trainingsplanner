"""End HR over measured rep time, including reconstructed multi-lap reps."""
import math


def _positive(value):
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    return value if math.isfinite(value) and value > 0 else None


def tail_hr(loads):
    durations = [_positive(load.get('seconds')) for load in loads]
    if not durations or any(s is None for s in durations):
        return None
    total = sum(durations)
    if total < 15:
        averages = [_positive(load.get('average_hr')) for load in loads]
        if all(hr is not None for hr in averages):
            return math.floor(sum(hr*s for hr,s in zip(averages,durations))/total + .5)
    window = min(total, max(15, total * .1))
    start, offset, values = total-window, 0, []
    for load, seconds in zip(loads,durations):
        for point in load.get('hr_samples') or []:
            try:
                t, hr = float(point[0]), _positive(point[1])
            except (TypeError, ValueError, IndexError):
                continue
            if 0 <= t < seconds and start <= offset+t < total and hr is not None:
                values.append(hr)
        offset += seconds
    if values:
        return math.floor(sum(values)/len(values) + .5)
    # Older saved loads can only provide this exact window when it is 15s.
    if window == 15 and durations[-1] >= 15:
        return _positive(loads[-1].get('average_hr_last_15'))
    return None


def lap_hr_load(lap, start_ms, end_ms, samples, average_hr):
    points = []
    local = lap.get('heartRateSamples')
    if isinstance(local,list):
        for item in local:
            try:
                t, hr = float(item['timeMillis']), _positive(item['heartRate'])
            except (TypeError, ValueError, KeyError):
                continue
            if start_ms <= t < end_ms and hr is not None:
                points.append([(t-start_ms)/1000, hr])
    else:
        streams = samples.get('samples') if isinstance(samples,dict) else []
        stream = next((item for item in streams or [] if isinstance(item,dict) and str(item.get('type') or '').upper()=='HEART_RATE'),None)
        interval = _positive(stream.get('intervalMillis')) if stream else None
        if interval:
            for i, value in enumerate(stream.get('values') or []):
                hr = _positive(value)
                if start_ms <= i*interval < end_ms and hr is not None:
                    points.append([(i*interval-start_ms)/1000,hr])
    load = {'seconds':(end_ms-start_ms)/1000, 'average_hr':average_hr, 'hr_samples':points}
    load['hr_tail'] = tail_hr([load])
    return load
