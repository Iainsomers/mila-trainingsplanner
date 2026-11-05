"""Duration-only previews for identified non-running watch activities."""
import math
import re

from core.garmin_details import number
from core.garmin_d import hr_zone


def alternative_part(athlete, metrics, duration_s):
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
    zone = hr_zone(athlete, average + 10) if average is not None and 0 < average < 300 else None
    part = {'description_label': 'Generated description', 'manual': [], 'auto': []}
    if seconds is None or seconds <= 0:
        part['description'] = label
        part['analysis_note'] = 'No activity duration is available. Alternative cannot be generated.'
        return part
    # Whole minutes, nearest minute, with at least one minute for short sessions.
    text = f"{label} {max(1, math.floor(seconds / 60 + .5))}'"
    part['description'] = text + (f' Z{zone}' if zone else '')
    if zone:
        part['training_fields'] = {'alt': part['description']}
        part['analysis_note'] = f'Alternative · Zone from average HR {average:g} + 10 = {average + 10:g} bpm.'
    else:
        part['analysis_note'] = ('Average HR is missing. Alternative cannot be assigned a zone.'
            if average is None or not 0 < average < 300 else
            'Average HR + 10 does not match a single configured HR zone. Check the athlete’s HR zones.')
    return part
