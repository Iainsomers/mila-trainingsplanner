"""Alternative descriptions for genuinely ambiguous measured interval groups."""
import math
import re
from copy import deepcopy
from statistics import median


_EXPLICIT_TIME_REQUEST_RE = re.compile(
    r"(?<!\w)\d+\s*[x×*]\s*\d+(?:[.,]\d+)?\s*(?:['′’]|min(?:uut|uten)?\b)",
    re.IGNORECASE,
)


def prefer_explicit_time_request(results, chat_messages):
    """Select time outright when the user's latest request states time reps."""
    if not chat_messages:
        return
    latest = str(chat_messages[-1].get("content") or "")
    if not _EXPLICIT_TIME_REQUEST_RE.search(latest):
        return
    for session in results:
        for part in session.get("parts") or []:
            options = part.get("training_alternatives") or []
            selected = next((option for option in options if option.get("label") == "Time"), None)
            if not selected:
                continue
            for key in ("training_fields", "description", "watch_loads"):
                part[key] = selected[key]
            # The request itself resolves the distance/time ambiguity. Keep a
            # single option so the UI does not ask the user to decide again.
            part["training_alternatives"] = [selected]


def single_time_option(core):
    """Recognize repeated whole-minute work bouts, independent of distance."""
    if len(core) < 5:
        return None
    work = core[::2]
    recovery = core[1::2]
    try:
        seconds = [float(l['seconds']) for l in work]
        target = int(math.floor(median(seconds) / 60 + .5)) * 60
        if not 120 <= target <= 1800 or any(
                not math.isfinite(s) or abs(s-target) > max(15, target*.06) for s in seconds):
            return None
        if any(not math.isfinite(float(l['meters'])) or float(l['meters']) / s < 2.5 for l, s in zip(work, seconds)):
            return None
        for i, lap in enumerate(recovery):
            m, s = float(lap['meters']), float(lap['seconds'])
            neighbors = work[i:i+2]
            if (not math.isfinite(m+s) or not 30 <= s <= 600 or not 0 <= m <= 600
                    or str(lap.get('zone')) not in {'1', '', 'None'}
                    or any(float(w['meters'])/float(w['seconds']) < 1.4*m/s for w in neighbors)):
                return None
        zones = sorted({'Z'+str(l.get('zone')) for l in work} & {'Z1','Z2','Z3','Z4','Z5'})
        zone = (' ' + (zones[0] if len(zones)==1 else zones[0]+'>'+zones[-1])) if zones else ''
        rests = [float(l['seconds']) for l in recovery[:len(work)-1]]
        pause = f' p{int(math.floor(median(rests)+.5))}'
        return f"{len(work)}×{target//60}'{zone}{pause}"
    except (KeyError, TypeError, ValueError, ZeroDivisionError, OverflowError):
        return None


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
            if part.get('training_alternatives'):
                continue
            loads = part.get('watch_loads') or []
            core = [l for l in loads if l.get('segment') == 'CORE']
            laps = [{'distanceMeters':l['meters'], 'durationMillis':l['seconds']*1000,
                     'zone':'Z'+str(l.get('zone') or '')} for l in core]
            options = long_interval_options(laps, lambda lap: lap['zone'])
            timed_loads = loads
            preferred = 'distance'
            if not options:
                timed = single_time_option(core)
                main = (part.get('training_fields') or {}).get('main')
                if timed and main:
                    options = {'distance':main, 'time':timed}
                    # This rule only succeeds when every work bout sits tightly
                    # around the same whole-minute duration. Time is therefore
                    # the stronger interpretation; keep Distance as an override.
                    preferred = 'time'
                    timed_loads = deepcopy(loads)
                    main_loads = [l for l in timed_loads if l.get('segment') == 'CORE']
                    target = int(re.search(r"×(\d+)'", timed)[1]) * 60
                    nominal = max(50, int(math.floor(median(float(l['meters']) for l in core[::2])/50+.5))*50)
                    for index, load in enumerate(main_loads):
                        load.update(work_rep=index % 2 == 0)
                        if index % 2 == 0:
                            load.update(ai_rep=index+1, ai_group=0, ai_target_seconds=target, ai_nominal_m=nominal)
            if not options:
                continue
            alternatives = []
            order = (('time','Time'), ('distance','Distance')) if preferred == 'time' else (
                ('distance','Distance'), ('time','Time'))
            for key, label in order:
                fields = dict(part.get('training_fields') or {})
                fields['main'] = options[key]
                alternatives.append({'label':label, 'training_fields':fields, 'watch_loads':timed_loads if key == 'time' else loads,
                    'description':f"WU: {fields.get('wu') or 'none'} · Main: {fields['main']} · CD: {fields.get('cd') or 'none'}"})
            part['training_alternatives'] = alternatives
            part.update({key: alternatives[0][key] for key in ('training_fields','description')})
