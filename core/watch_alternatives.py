"""Alternative descriptions for genuinely ambiguous measured interval groups."""
import math
import re
from statistics import median


def long_interval_options(laps, zone_for_lap):
    try:
        rows = [(float(l['distanceMeters']), float(l['durationMillis']) / 1000) for l in laps]
    except (KeyError, TypeError, ValueError):
        return None
    if len(rows) < 8 or len(rows) % 2:
        return None
    groups = []
    for i in range(0, len(rows), 2):
        m, s = rows[i]
        rm, rs = rows[i + 1]
        if not (math.isfinite(m+s+rm+rs) and 800 <= m <= 6000 and s >= 120
                and 0 < rm <= 350 and 30 <= rs <= 600 and m/s >= 1.5*rm/rs
                and zone_for_lap(laps[i + 1]) in {'Z1', '', 'NA'}):
            return None
        if not groups or abs(m - median(rows[j][0] for j in groups[-1])) > m * .08:
            groups.append([])
        groups[-1].append(i)
    if len(groups) < 2 or any(len(g) < 2 for g in groups):
        return None
    distance_parts, time_parts = [], []
    for group in groups:
        nominal = int(math.floor(median(rows[i][0] for i in group) / 100 + .5) * 100)
        minutes = int(math.floor(median(rows[i][1] for i in group) / 60 + .5))
        if (minutes < 2 or any(abs(rows[i][0] - nominal) > nominal * .05
                or abs(rows[i][1] - minutes * 60) > max(5, minutes * 60 * .03) for i in group)):
            return None
        zones = sorted({zone_for_lap(laps[i]) for i in group} & {'Z1','Z2','Z3','Z4','Z5'})
        zone = (' ' + (zones[0] if len(zones)==1 else zones[0]+'>'+zones[-1])) if zones else ''
        rests = [rows[i+1][1] for i in group[:-1] if rows[i+1][1] < 180]
        recovery = f' p{int(math.floor(median(rests)+.5))}' if rests else ''
        distance_parts.append(f'{len(group)}×{nominal} m{zone}{recovery}')
        time_parts.append(f"{len(group)}×{minutes}'{zone}{recovery}")
    return {'distance': ' + '.join(distance_parts), 'time': ' + '.join(time_parts), 'groups': groups}


def add_training_alternatives(results):
    for session in results:
        for part in session.get('parts') or []:
            loads = part.get('watch_loads') or []
            core = [l for l in loads if l.get('segment') == 'CORE']
            laps = [{'distanceMeters':l['meters'], 'durationMillis':l['seconds']*1000,
                     'zone':'Z'+str(l.get('zone') or '')} for l in core]
            options = long_interval_options(laps, lambda lap: lap['zone'])
            if not options:
                continue
            alternatives = []
            for key, label in (('distance','Distance'), ('time','Time')):
                fields = dict(part.get('training_fields') or {})
                fields['main'] = options[key]
                alternatives.append({'label':label, 'training_fields':fields, 'watch_loads':loads,
                    'description':f"WU: {fields.get('wu') or 'none'} · Main: {fields['main']} · CD: {fields.get('cd') or 'none'}"})
            part['training_alternatives'] = alternatives
            part.update({key: alternatives[0][key] for key in ('training_fields','description')})
