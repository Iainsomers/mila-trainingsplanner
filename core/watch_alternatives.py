"""Alternative descriptions for genuinely ambiguous measured interval groups."""
import math
import re
from copy import deepcopy
from statistics import median


_EXPLICIT_TIME_REQUEST_RE = re.compile(
    r"(?<!\w)(\d+)\s*[x×*]\s*(\d+)\s*(?:['′’]|min(?:uut|uten)?\b)",
    re.IGNORECASE,
)


def requested_time_reps(chat_messages):
    """Return the explicit (count, whole minutes) request from the last message."""
    if not chat_messages:
        return None
    match = _EXPLICIT_TIME_REQUEST_RE.search(str(chat_messages[-1].get("content") or ""))
    return (int(match[1]), int(match[2])) if match else None


def prefer_explicit_time_request(results, chat_messages):
    """Select time outright when the user's latest request states time reps."""
    requested = requested_time_reps(chat_messages)
    if not requested:
        return False
    from core.training_text import split_main_segments

    text = str(chat_messages[-1].get("content") or "")
    requested_blocks = split_main_segments(text, split_hyphens=False)
    selected_any = False
    for session in results:
        for part in session.get("parts") or []:
            options = part.get("training_alternatives") or []
            selected = next((candidate for option in options if option.get("label") == "Time"
                             if (candidate := _match_time_request(option, requested, requested_blocks))), None)
            if not selected:
                continue
            for key in ("training_fields", "description", "watch_loads"):
                part[key] = selected[key]
            # The request itself resolves the distance/time ambiguity. Keep a
            # single option so the UI does not ask the user to decide again.
            part["training_alternatives"] = [selected]
            part["ai_structure_status"] = "measured_structure"
            part["chat_reply"] = "The measured laps confirm the requested time repetitions."
            selected_any = True
    return selected_any


def _match_time_request(option, requested, requested_blocks):
    """Confirm all explicit blocks before returning a selectable preview."""
    from core.training_text import split_main_segments

    fields = option.get("training_fields") or {}
    blocks = split_main_segments(fields.get("main"), split_hyphens=False)
    if len(blocks) != len(requested_blocks):
        return None
    for index, (block, requested_text) in enumerate(zip(blocks, requested_blocks)):
        timed = _EXPLICIT_TIME_REQUEST_RE.match(block)
        asked = requested if index == 0 else requested_time_reps([{"content": requested_text}])
        if timed and asked == (int(timed[1]), int(timed[2])):
            continue
        distance = re.fullmatch(r"(?:1\s*[×x*]\s*)?(\d+)\s*m(?:\s+z[1-5])?", requested_text, re.I)
        if index != 1 or len(blocks) != 2 or not distance or not timed or timed[1] != "1":
            return None
        work = [load for load in option["watch_loads"] if load.get("ai_group") == 1 and load.get("work_rep")]
        target = int(distance[1])
        if len(work) != 1 or target <= 0 or abs(float(work[0]["meters"]) - target) > max(30, target * .08):
            return None
        selected = deepcopy(option)
        for load in selected["watch_loads"]:
            if load.get("ai_group") == 1 and load.get("work_rep"):
                load["ai_nominal_m"] = target
        blocks[index] = f"1×{target} m" + block[timed.end():]
        selected["training_fields"]["main"] = " + ".join(blocks)
        from core.watch_ai_structure import description
        selected["description"] = description(selected["training_fields"])
        return selected
    return option


def _valid_time_recovery(lap, neighbors):
    meters, seconds = float(lap['meters']), float(lap['seconds'])
    return (math.isfinite(meters + seconds) and 30 <= seconds <= 600 and 0 <= meters <= 600
            and str(lap.get('zone')) in {'1', '', 'None'}
            and all(float(work['meters']) / float(work['seconds']) >= 1.4 * meters / seconds
                    for work in neighbors))


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
        if any(not _valid_time_recovery(lap, work[i:i+2]) for i, lap in enumerate(recovery)):
            return None
        zones = sorted({'Z'+str(l.get('zone')) for l in work} & {'Z1','Z2','Z3','Z4','Z5'})
        zone = (' ' + (zones[0] if len(zones)==1 else zones[0]+'>'+zones[-1])) if zones else ''
        rests = [float(l['seconds']) for l in recovery[:len(work)-1]]
        pause = f' p{int(math.floor(median(rests)+.5))}'
        return f"{len(work)}×{target//60}'{zone}{pause}"
    except (KeyError, TypeError, ValueError, ZeroDivisionError, OverflowError):
        return None


def _time_option_with_finish(core):
    """Recognize a repeated timed prefix and one distinct final work lap."""
    if len(core) < 7 or len(core) % 2 == 0:
        return None
    prefix = single_time_option(core[:-2])
    if not prefix:
        return None
    try:
        last = core[-1]
        meters, seconds = float(last["meters"]), float(last["seconds"])
        if not math.isfinite(meters + seconds) or not 120 <= seconds <= 1815 or meters / seconds < 2.5:
            return None
        target = int(math.floor(seconds / 60 + .5)) * 60
        prefix_target = int(_EXPLICIT_TIME_REQUEST_RE.match(prefix)[2]) * 60
        if (target == prefix_target or abs(seconds - target) > max(15, target * .06)
                or not _valid_time_recovery(core[-2], [core[-3], last])):
            return None
        zone = str(last.get("zone") or "")
        zone_text = f" Z{zone}" if zone in {"1","2","3","4","5"} else ""
        return f"{prefix} + 1×{target//60}'{zone_text}", target
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
            finish = None
            if not options:
                timed = single_time_option(core)
                finish = _time_option_with_finish(core) if not timed else None
                if finish:
                    timed = finish[0]
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
                            if finish and index == len(main_loads) - 1:
                                finish_nominal = int(math.floor(float(load['meters'])/50+.5))*50
                                load.update(ai_rep=index+1, ai_group=1, ai_target_seconds=finish[1],
                                            ai_nominal_m=finish_nominal)
                            else:
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
            if finish:
                part['watch_loads'] = timed_loads
