"""Garmin C structure with athlete-configured, measured end-of-rep HR zones."""
from copy import deepcopy
import math
import re
from types import SimpleNamespace


def hr_zone(athlete, value):
    if isinstance(value, bool):
        return None
    try:
        hr = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(hr) or hr <= 0:
        return None
    configured = getattr(athlete, 'zone_hr_bpm', {}) or {}
    previous, ranges = 0, []
    for zone in range(1, 6):
        text = str(configured.get(str(zone), configured.get(f'Z{zone}', ''))).strip().lower()
        interval = re.fullmatch(r'(\d+)\s*[-–]\s*(\d+)', text)
        ceiling = re.fullmatch(r'(?:max\s*|<=\s*|≤\s*)?(\d+)', text)
        if interval:
            low, high = map(int, interval.groups())
        elif ceiling:
            low, high = previous + 1, int(ceiling.group(1))
        else:
            return None  # No estimated limits or guessed missing zones.
        if low <= previous or high < low:
            return None
        ranges.append((low, high, str(zone)))
        previous = high
    return next((zone for low, high, zone in ranges if low <= hr <= high), None)


def rep_hr_zone(athlete, meters, seconds, hr):
    return hr_zone(athlete, hr) if meters >= 400 or seconds >= 50 else None


def _replace_zone(text, zones):
    zones = sorted(set(zones))
    if not zones:
        return text
    label = 'Z' + zones[0] + ('>Z' + zones[-1] if len(zones) > 1 else '')
    return re.sub(r'\bz[1-5](?:\s*>\s*z?[1-5])?\b', label, text, flags=re.I)


def apply_garmin_d(results, athlete):
    from core.watch_processing import processed_main_reps
    from core.training_text import split_main_segments
    from core.views.calendar import _virtual_segment_from_text
    results = deepcopy(results)
    for session in results:
        for part in session.get('parts') or []:
            original = deepcopy(part.get('watch_loads') or [])
            if not original:
                continue
            loads = part['watch_loads']
            for load in loads:
                load['pace_zone'] = load.get('zone', '')
            fields = dict(part.get('training_fields') or {})
            main = str(fields.get('main') or '')
            for text in split_main_segments(main):
                segment = _virtual_segment_from_text('CORE', text)
                slot = SimpleNamespace(source='watch_c', watch_loads=original,
                                       segments=SimpleNamespace(all=lambda: [segment]))
                if not re.search(r'\bz[1-5]\b', text, re.I):
                    continue
                reps = processed_main_reps(slot)
                zones = []
                consumed = set()
                for rep in reps:
                    m, s = rep['measured_distance_m'], rep['measured_seconds']
                    zone = rep_hr_zone(athlete, m, s, rep.get('average_hr_last_15'))
                    if not zone:
                        zones.extend(re.findall(r'\bz([1-5])\b', text, re.I))
                        continue
                    zones.append(zone)
                    # Assign the full reconstructed rep (e.g. 1000+1000+rest)
                    # its end-HR zone. Recoveries retain their own measured data.
                    found = False
                    for start in range(len(original)):
                        if start in consumed or original[start].get('segment') != 'CORE':
                            continue
                        meters = seconds = 0
                        for end in range(start, len(original)):
                            if end in consumed or original[end].get('segment') != 'CORE':
                                break
                            meters += float(original[end].get('meters') or 0)
                            seconds += float(original[end].get('seconds') or 0)
                            if abs(meters - m) < .01 and abs(seconds - s) < .01:
                                for index in range(start, end + 1):
                                    loads[index]['zone'] = zone
                                    consumed.add(index)
                                found = True
                                break
                            if meters > m + .01 or seconds > s + .01:
                                break
                        if found:
                            break
                main = main.replace(text, _replace_zone(text, zones), 1)
            fields['main'] = main
            for key, kind in (('wu','WU'), ('cd','CD')):
                block = [load for load in original if load.get('segment') == kind]
                if fields.get(key) and block:
                    zone = rep_hr_zone(athlete, sum(float(l['meters']) for l in block),
                                       sum(float(l['seconds']) for l in block), block[-1].get('average_hr_last_15'))
                    if zone:
                        fields[key] = _replace_zone(fields[key], [zone])
                        for index, load in enumerate(original):
                            if load.get('segment') == kind:
                                loads[index]['zone'] = zone
            part['training_fields'] = fields
            if fields.get('main'):
                part['description'] = f"WU: {fields.get('wu') or 'none'} · Main: {main} · CD: {fields.get('cd') or 'none'}"
            for row, load in zip(part.get('manual') or [], loads):
                row['pace_z_pace'] = row.get('z_pace')
                if str(load.get('zone')) in {'1','2','3','4','5'}:
                    row['z_pace'] = 'Z' + str(load['zone'])
            if part.get('training_alternatives'):
                converted = []
                for alternative in part['training_alternatives']:
                    candidate = {**alternative, 'watch_loads': deepcopy(original)}
                    converted.append({**apply_garmin_d([{'parts':[candidate]}], athlete)[0]['parts'][0], 'label': alternative['label']})
                part['training_alternatives'] = converted
            part['analysis_note'] = 'D: Last 15s HR takes precedence at 400 m or 50 s; otherwise pace zones apply. Reconstructed reps use their final lap HR. Missing HR or configured limits keeps the pace zone.'
    return results
