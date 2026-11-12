"""Duration-only previews for identified non-running watch activities."""
import math
import re
from statistics import median

from core.garmin_details import number
from core.garmin_d import hr_zone


def _time_only_intervals(laps):
    """Recognize conservative work/recovery timing from explicit lap presses."""
    if not isinstance(laps, list) or len(laps) < 5:
        return None
    try:
        durations = [float(lap['elapsed_time']) for lap in laps]
    except (KeyError, TypeError, ValueError):
        return None
    matches = []
    for start in range(len(durations)):
        for count in range(3, (len(durations) - start + 1) // 2 + 1):
            block = durations[start:start + count * 2 - 1]
            if len(block) != count * 2 - 1:
                continue
            work, recovery = block[::2], block[1::2]
            target = int(math.floor(median(work) / 60 + .5)) * 60
            if not 120 <= target <= 1800 or any(
                    abs(value-target) > max(15, target*.06) for value in work):
                continue
            if any(not 15 <= value <= min(600, target*.75) for value in recovery):
                continue
            matches.append((count, target, int(math.floor(median(recovery) + .5))))
    if not matches:
        return None
    count, target, pause = max(matches)
    return f"{count}×{target//60}' p{pause}"


def _duration_label(seconds):
    milliseconds = int(round(float(seconds) * 1000))
    hours, remainder = divmod(milliseconds, 3600000)
    minutes, remainder = divmod(remainder, 60000)
    secs, millis = divmod(remainder, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}.{millis:03d}"


def alternative_part(athlete, metrics, duration_s, laps=None):
    """None means the sport is running or not sufficiently identified."""
    sport = metrics.get('sport')
    if not isinstance(sport, str) or not re.fullmatch(r'[A-Za-z][A-Za-z _-]{0,99}', sport):
        return None
    sport = sport.strip().upper().replace('-', '_').replace(' ', '_')
    if 'RUN' in sport.split('_') or 'RUNNING' in sport.split('_') or sport in {
        '', 'UNKNOWN', 'OTHER', 'GENERIC', 'ALL', 'MULTISPORT', 'TRANSITION',
    }:
        return None
    label = {'ELLIPTICAL_FITNESS': 'Elliptical'}.get(sport, sport.replace('_', ' ').title())
    seconds = number(duration_s)
    average = number(metrics.get('average_hr'))
    if average is None:
        average = number(metrics.get('sample_average_hr'))
    correction = max(0, int(getattr(athlete, 'alternative_hr_correction', 10) or 0))
    corrected_hr = average + correction if average is not None else None
    zone = hr_zone(athlete, corrected_hr) if average is not None and 0 < average < 300 else None
    part = {'description_label': 'Generated description', 'manual': [], 'auto': []}
    if seconds is None or seconds <= 0:
        part['description'] = label
        part['analysis_note'] = 'No activity duration is available. Alternative cannot be generated.'
        return part
    # Whole minutes, nearest minute, with at least one minute for short sessions.
    intervals = _time_only_intervals(laps)
    text = f"{label} {intervals or str(max(1, math.floor(seconds / 60 + .5))) + chr(39)}"
    part['description'] = text + (f' Z{zone}' if zone else '')
    # Sport and duration are sufficient for a usable Alternative. Heart rate
    # only enriches it with a zone; missing/mismatching zones must not hide the
    # Use/Add actions for an otherwise valid non-running activity.
    part['training_fields'] = {'alt': part['description']}
    if zone:
        part['analysis_note'] = (
            f'Alternative · Zone from average HR {average:g} + {correction} = {corrected_hr:g} bpm.'
        )
    else:
        part['analysis_note'] = ('Average HR is missing. Alternative cannot be assigned a zone.'
            if average is None or not 0 < average < 300 else
            f'Average HR + {correction} does not match a single configured HR zone. Check the athlete’s HR zones.')
    if laps:
        part['manual'] = [{
            'index': index,
            'distance': 'NA', 'distance_rounded_50': 'NA',
            'duration': _duration_label(lap.get('elapsed_time')),
            'pace': 'NA', 'pace_z_pace': 'NA', 'z_pace': 'NA', 'hr_zone': 'NA', 't_pace': 'NA',
            'average_hr': round(lap['avg_heart_rate']) if lap.get('avg_heart_rate') is not None else 'NA',
            'hr_tail': round(lap['hr_tail']) if lap.get('hr_tail') is not None else 'NA',
        } for index, lap in enumerate(laps, 1) if lap.get('elapsed_time')]
    return part
