"""Validate AI lap assignments; derive all displayed numbers from measurements."""
import math
from statistics import median
from collections import Counter


def representative_zones(labels):
    """Summary only: keep zones represented by at least 10% of the reps.

    Unknown reps remain in the denominator; if none meets the threshold,
    retain the observed zones rather than inventing or removing a label.
    """
    labels = list(labels)
    counts = Counter(label for label in labels if label in {'Z1','Z2','Z3','Z4','Z5'})
    retained = [label for label,count in counts.items() if count * 10 >= len(labels)]
    return sorted(retained or counts)


class ValidatedDescription(str):
    def __new__(cls, structure):
        value = super().__new__(cls, structure['description'])
        value.structure = structure
        return value


def _continuous_easy_prefix(rows):
    """A sustained easy block may end with a tiny recorded transition."""
    last = rows[-1]
    if 0 < last['distance_m'] <= 5 and 0 < last['duration_s'] <= 2 and last['zone'] in {'Z1', 'Z2'}:
        rows = rows[:-1]
    if len(rows) < 2 or sum(row['distance_m'] for row in rows) < 800:
        return False
    if any(row['zone'] != 'Z1' or row['duration_s'] <= 0 for row in rows):
        return False
    if (any(row.get('lap_intensity') in (1, 4, 5) for row in rows)
            or sum((row.get('paused_s') or 0) >= 15 for row in rows) >= 2):
        return False
    speeds = [row['distance_m'] / row['duration_s'] for row in rows]
    return all(map(math.isfinite, speeds)) and min(speeds) >= 2 and max(speeds) <= 1.25 * min(speeds)


def infer_easy_run_with_strides(facts, *, rep_zone=None):
    """Recognize an easy run followed by an unambiguous short interval series."""
    first_work = next((i for i, row in enumerate(facts) if row['zone'] in {'Z3', 'Z4', 'Z5'}), None)
    if not first_work or not _continuous_easy_prefix(facts[:first_work]):
        return None
    tail = facts[first_work:]
    if len(tail) % 2 == 0:
        finish = tail[-1]
        if not (0 < finish['duration_s'] <= 600 and finish['distance_m'] <= 600
                and finish['distance_m'] < 2 * finish['duration_s']):
            return None
    work = tail[::2]
    if len(work) < 3 or any(row['zone'] not in {'Z3','Z4','Z5'}
                            or not 70 <= row['distance_m'] <= 130
                            or not 10 <= row['duration_s'] <= 35 for row in work):
        return None
    proposal = {'continuous_main_laps': [row['lap'] for row in facts[:first_work]],
                'recovery_laps': [row['lap'] for row in tail[1::2]],
                'groups': [{'target_meters':100, 'reps':[[row['lap']] for row in work]}]}
    return validate_lap_structure({'confidence':1, 'lap_structure':proposal}, facts, rep_zone=rep_zone)


def infer_lap_structure(facts, *, rep_zone=None):
    """Propose clear mixed time groups locally, then use the same validator.

    Does not depend on AI consent, service availability or a model's answer.
    Missing pace zones or ambiguous boundaries deliberately yield no proposal.
    """
    try:
        if not facts or any(row['duration_s'] <= 0 for row in facts):
            return None
        def work(row):
            return row['zone'] in {'Z2','Z3','Z4','Z5'} and row['distance_m']/row['duration_s'] >= 2.5
        blocks, index = [], 0
        while index < len(facts):
            if not work(facts[index]):
                index += 1
                continue
            block = []
            while index < len(facts) and work(facts[index]):
                block.append(facts[index]['lap'])
                index += 1
            blocks.append(block)
        if len(blocks) < 4:
            return None
        by_id = {row['lap']:row for row in facts}
        first, last = blocks[0][0], blocks[-1][-1]
        groups = []
        for block in blocks:
            seconds = sum(by_id[i]['duration_s'] for i in block)
            target = int(math.floor(seconds/60+.5)*60)
            if not groups or groups[-1]['target_seconds'] != target:
                groups.append({'target_seconds':target, 'reps':[]})
            groups[-1]['reps'].append(block)
        if len(groups) < 2:
            return None
        proposal = {'warmup_laps':[], 'stop_laps':[], 'recovery_laps':[], 'cooldown_laps':[], 'groups':groups}
        assigned = {i for block in blocks for i in block}
        for row in facts:
            i, meters, seconds = row['lap'], row['distance_m'], row['duration_s']
            if i in assigned:
                continue
            if i < first:
                key = 'stop_laps' if seconds >= 600 and meters/seconds < 1 else 'warmup_laps'
            elif i > last and meters >= 800 and meters/seconds >= 2:
                key = 'cooldown_laps'
            else:
                key = 'recovery_laps'
            proposal[key].append(i)
        return validate_lap_structure({'confidence':1, 'lap_structure':proposal}, facts, rep_zone=rep_zone)
    except (KeyError, ValueError, TypeError, ZeroDivisionError, OverflowError):
        return None


def parse_structure_suggestion(text):
    """Parse bounded numeric intent, never forward free-form instructions to AI."""
    import re
    text = str(text).lower().replace('\u00d7', 'x').replace('*', 'x')
    if not text.strip() or len(text) > 160:
        raise ValueError('Use a structure such as 16x500m or 2x(8x500m).')
    text = re.sub(r'(\d+)\s*x\s*(\d+)\s*x\s*(\d+\s*(?:m|min))(?=\s*(?:\+|$))', r'\1x(\2x\3)', text)
    groups = []
    for piece in text.split('+'):
        match = re.fullmatch(r"\s*(?:(\d+)\s*x\s*\(\s*)?(\d+)\s*x\s*(\d+)\s*(m|min|')\s*(\))?\s*", piece)
        if not match or bool(match[1]) != bool(match[5]):
            raise ValueError('Use a structure such as 16x500m or 2x(8x500m).')
        sets, count, value = int(match[1] or 1), int(match[2]), int(match[3])
        distance = match[4] == 'm'
        if not (1 <= sets <= 15 and count >= 2 and 3 <= sets*count <= 30
                and (100 <= value <= 10000 and value % 50 == 0 if distance else 2 <= value <= 30)):
            raise ValueError('Structure is outside the supported repetition or target range.')
        groups.append(dict(sets=sets, count=count, target_meters=value if distance else None,
                           target_seconds=None if distance else value*60))
    if len(groups) > 8:
        raise ValueError('Too many groups.')
    return groups


def validate_lap_structure(data, facts, *, issues=None, minimum_confidence=.75, rep_zone=None, requested_structure=None, allow_exact_distance=False):
    """No omitted/duplicate laps, invented reps, or running discarded as stops."""
    reason = 'Invalid lap structure or confidence.'
    def reject():
        if issues is not None:
            issues.append(reason)
        return None
    try:
        if not isinstance(data,dict):
            return reject()
        score = data.get('confidence')
        if isinstance(score,bool) or not isinstance(score,(int,float)) or not math.isfinite(score):
            reason = 'AI confidence is missing or is not a finite number from 0 to 1.'
            return reject()
        if not minimum_confidence <= score <= 1:
            reason = f'AI confidence {score:.2f}; required range is {minimum_confidence:.2f} to 1.00.'
            return reject()
        reason = 'AI lap_structure is missing or has an invalid format.'
        proposal = data['lap_structure']
        by_id = {row['lap']: row for row in facts}
        if len(by_id) != len(facts) or set(by_id) != set(range(1, len(facts)+1)):
            return reject()
        used = set()

        reason = "Every source lap must be assigned exactly once; use only original lap numbers."
        def indices(values):
            if not isinstance(values, list) or any(type(i) is not int or i not in by_id for i in values):
                raise ValueError
            if len(values) != len(set(values)) or used.intersection(values):
                raise ValueError
            used.update(values)
            return values

        warmup = indices(proposal.get('warmup_laps', []))
        cooldown = indices(proposal.get('cooldown_laps', []))
        recovery = indices(proposal.get('recovery_laps', []))
        stops = indices(proposal.get('stop_laps', []))
        continuous = indices(proposal.get('continuous_main_laps', []))
        if continuous:
            reason = 'Continuous Main must be a consecutive easy running block before the interval series.'
            if (requested_structure or continuous != list(range(continuous[0], continuous[-1]+1))
                    or not _continuous_easy_prefix([by_id[i] for i in continuous])):
                return reject()
        # A boundary may include a recorded walking transition. Preserve that
        # source lap as non-work recovery instead of adding walking to WU/CD
        # or rejecting an otherwise valid AI-selected interval structure.
        from core.watch_processing import is_walking_load
        walking = [i for i in warmup + cooldown
                   if is_walking_load(by_id[i]['distance_m'],by_id[i]['duration_s'])]
        warmup = [i for i in warmup if i not in walking]
        cooldown = [i for i in cooldown if i not in walking]
        recovery = sorted(recovery + walking)
        reason = "Stop laps must last at least 600 seconds and average less than 1 m/s; classify other slow transitions as recovery_laps."
        for i in stops:
            row = by_id[i]
            if not (row['duration_s'] >= 600 and row['distance_m']/row['duration_s'] < 1):
                raise ValueError
        reason = "Warmup, cooldown and recovery must have easy pace zones; do not discard work laps."
        for i in warmup + cooldown + recovery:
            if by_id[i]['zone'] not in {'Z1', 'Z2', '', 'NA'}:
                role = 'warmup_laps' if i in warmup else 'cooldown_laps' if i in cooldown else 'recovery_laps'
                reason = (f"Lap {i} is {by_id[i]['zone']} but assigned to {role}. "
                          "Warmup, cooldown and recovery allow only Z1/Z2 or unknown zones. "
                          "Keep this work lap in a rep; adjacent autolaps without recovery may belong to the same rep.")
                raise ValueError
        reason = "Warmup/cooldown contain a lap slower than 2 m/s; classify slow transition laps as recovery_laps or valid stop_laps."
        if any(by_id[i]['distance_m']/by_id[i]['duration_s'] < 2 for i in warmup + cooldown):
            return reject()
        groups = proposal['groups']
        if not isinstance(groups, list) or not 1 <= len(groups) <= 8:
            return reject()
        reason = "Each group needs 2-30 observed reps and exactly one target: nominal target_meters or whole-minute target_seconds."
        if requested_structure:
            reason = 'No matching structure found: proposed targets, repetition counts or sets differ from your suggestion.'
            if len(groups) != len(requested_structure):
                return reject()
            for group, expected in zip(groups, requested_structure):
                starts = group.get('set_start_laps') or []
                if (group.get('target_meters') != expected['target_meters']
                        or group.get('target_seconds') != expected['target_seconds']
                        or len(group.get('reps') or []) != expected['sets']*expected['count']
                        or (len(starts) if starts else 1) != expected['sets']):
                    return reject()
        blocks, last = [], 0
        for group_index, group in enumerate(groups):
            reps = group['reps']
            distance_target = group.get('target_meters')
            target = group.get('target_seconds')
            distance_based = distance_target is not None
            if distance_based and (type(distance_target) is not int or (distance_target % 50 and not allow_exact_distance) or not (50 if allow_exact_distance else 100) <= distance_target <= 10000 or target is not None):
                reason = f"Group {group_index+1}: target_meters must be an integer multiple of 50 from 100 to 10000; target_seconds must be omitted or null when using distance."
                raise ValueError
            if not distance_based and (type(target) is not int or target % 60 or not 120 <= target <= 1800):
                reason = f"Group {group_index+1}: target_seconds must be whole minutes from 120 to 1800. For short fixed-distance reps (e.g. 300m in 55s), use target_meters, not measured seconds."
                raise ValueError
            if not isinstance(reps, list) or not 2 <= len(reps) <= 30:
                reason = f"Group {group_index+1}: provide 2-30 observed reps. Combine equal sets in one group with set_start_laps; each reps entry is one effort."
                raise ValueError
            for rep in reps:
                reason = "Reps must be chronological consecutive source laps and agree with target distance within max(30m, 8%) or target time within tolerance."
                ids = indices(rep)
                if not ids or ids != list(range(ids[0], ids[-1]+1)) or ids[0] <= last:
                    reason = f"Group {group_index+1}: rep lap IDs {ids[:20]} are not consecutive/chronological. Each reps entry is ONE work repetition, not a whole set."
                    raise ValueError
                rows = [by_id[i] for i in ids]
                meters = sum(row['distance_m'] for row in rows)
                seconds = sum(row['duration_s'] for row in rows)
                if not math.isfinite(meters+seconds) or meters <= 0 or seconds <= 0:
                    reason = f"Group {group_index+1}, laps {ids[:20]}: missing positive measured distance/time."
                    raise ValueError
                if distance_based and abs(meters-distance_target) > max(30, distance_target*.08):
                    reason = f"Group {group_index+1}, laps {ids[:20]}: measured {meters:.1f}m differs from target {distance_target}m by more than max(30m, 8%). A rep must not include recovery laps."
                    raise ValueError
                if not distance_based and abs(seconds-target) > max(15, target*.06):
                    reason = f"Group {group_index+1}, laps {ids[:20]}: measured {seconds:.2f}s does not match time target {target}s. Use target_meters for fixed-distance reps with variable duration."
                    raise ValueError
                if any(row['distance_m']/row['duration_s'] < 2 for row in rows):
                    reason = f"Group {group_index+1}, laps {ids[:20]}: work rep contains a slow recovery/stop lap. Assign recovery separately."
                    raise ValueError
                blocks.append({'ids':ids, 'group':group_index, 'target':target or max(1, round(seconds)), 'distance_target':distance_target, 'meters':meters, 'seconds':seconds})
                last = ids[-1]
        missing = sorted(set(by_id) - used)
        # Preserve unassigned measured walking as recovery, never invent a
        # work repetition or infer the role of an omitted running lap.
        missing_walking = [i for i in missing
                           if is_walking_load(by_id[i]['distance_m'],by_id[i]['duration_s'])]
        recovery = sorted(recovery + missing_walking)
        used.update(missing_walking)
        missing = sorted(set(by_id) - used)
        if missing:
            reason = f"Missing source lap IDs {missing[:50]}. Assign each to a work rep, running warmup or cooldown; do not discard running laps."
            return reject()
        if len(blocks) < 3:
            reason = f"Only {len(blocks)} work reps assigned; at least three measured work reps are required. Each reps entry is one repetition, not one set."
            return reject()
        reason = 'Warmup must precede work, cooldown must follow work; leading recovery must be slow and trailing recovery immediately follow work.'
        first, last = blocks[0]['ids'][0], blocks[-1]['ids'][-1]
        if continuous and (continuous[-1] >= first or any(i >= continuous[0] for i in warmup)):
            reason = 'Continuous Main must follow warmup and precede all repetitions.'
            return reject()
        if any(i >= first for i in warmup) or any(i <= last for i in cooldown):
            return reject()
        if any(i < first and by_id[i]["distance_m"]/by_id[i]["duration_s"] >= 2 for i in recovery):
            return reject()
        if any(i > last+1 for i in recovery):
            return reject()
        # Every rep boundary needs real, slower recovery; stop markers alone
        # cannot turn a continuous easy run into a series of intervals.
        reason = "Each rep boundary needs assigned recovery of 30-600 seconds (15s minimum between distance reps up to 600m and 90s), at most 600m; both neighboring work reps must be at least 20% faster than recovery."
        pauses = {}
        for left, right in zip(blocks, blocks[1:]):
            gap = list(range(left['ids'][-1]+1, right['ids'][0]))
            if not gap or any(i not in recovery for i in gap):
                return reject()
            meters = sum(by_id[i]['distance_m'] for i in gap)
            seconds = sum(by_id[i]['duration_s'] for i in gap)
            speed = min(left['meters']/left['seconds'], right['meters']/right['seconds'])
            # AI chooses the structure. Retain a measurable speed contrast,
            # allowing jogging recovery without accepting nearly equal pace.
            short_distance_reps = all(b['distance_target'] is not None and b['distance_target'] <= 600
                                      and b['seconds'] <= 90 for b in (left, right))
            minimum_rest = 15 if short_distance_reps else 30
            if not minimum_rest <= seconds <= 600 or meters > 600 or speed < 1.2*meters/seconds:
                return reject()
            pauses[left['ids'][0]] = seconds
        # Challenge an omitted opening effort; only AI may change the grouping.
        opening = blocks[0]
        if opening['distance_target'] is not None and len(blocks) >= 3:
            candidate_id = first - 2
            gap_id = first - 1
            if candidate_id in warmup and gap_id in recovery:
                candidate, gap = by_id[candidate_id], by_id[gap_id]
                target = opening['distance_target']
                reference_speed = median(b['meters']/b['seconds'] for b in blocks
                                         if b['group'] == opening['group'])
                candidate_speed = candidate['distance_m']/candidate['duration_s']
                if (abs(candidate['distance_m']-target) <= max(30, target*.08)
                        and .85 <= candidate_speed/reference_speed <= 1.15
                        and 30 <= gap['duration_s'] <= 600 and gap['distance_m'] <= 600
                        and min(candidate_speed, opening['meters']/opening['seconds'])
                            >= 1.2*gap['distance_m']/gap['duration_s']):
                    reason = (f"Lap {candidate_id} assigned to warmup matches the opening distance "
                              "group in distance and speed and has slower recovery before the next rep. "
                              "Reassess it as a possible first work rep regardless of Z1/Z2; "
                              "check longer pauses for equal sets without discarding a rep.")
                    return reject()
        assignments = [{'segment':'WU' if i in warmup else 'CD' if i in cooldown else 'CORE',
                        'work_rep':False} for i in range(1,len(facts)+1)]
        distance_parts, time_parts = [], []
        distance_keys, time_keys = set(), set()
        for group_index in range(len(groups)):
            group_blocks = [block for block in blocks if block['group']==group_index]
            reason = "Group repetitions must agree with the nominal distance within max(30m, 8%)."
            nominal = group_blocks[0]['distance_target'] or int(math.floor(median(b['meters'] for b in group_blocks)/100+.5)*100)
            if any(abs(b['meters']-nominal) > max(30, nominal*.08) for b in group_blocks):
                return reject()
            # Autolaps describe recording boundaries, not separate efforts.
            # Classify each complete measured rep before forming the group range.
            if rep_zone is not None:
                labels = [rep_zone(b['meters'], b['seconds']) for b in group_blocks]
            else:
                labels = {by_id[i]['zone'] for b in group_blocks for i in b['ids']}
            zones = (representative_zones(labels) if rep_zone is not None else
                     sorted(labels & {'Z1','Z2','Z3','Z4','Z5'}))
            zone = (' '+(zones[0] if len(zones)==1 else zones[0]+'>'+zones[-1])) if zones else ''
            reason = 'set_start_laps must list the first work lap of each equal-sized set, including the first rep; each set needs at least two reps and a longer measured set pause.'
            starts = groups[group_index].get('set_start_laps', [])
            set_sizes, set_pauses = [], []
            if starts:
                rep_starts = [b['ids'][0] for b in group_blocks]
                if (not isinstance(starts,list) or any(type(i) is not int for i in starts)
                        or starts != sorted(set(starts)) or starts[0] != rep_starts[0]
                        or any(i not in rep_starts for i in starts) or len(starts) < 2):
                    return reject()
                positions = [rep_starts.index(i) for i in starts] + [len(group_blocks)]
                set_sizes = [right-left for left,right in zip(positions,positions[1:])]
                if len(set(set_sizes)) != 1 or min(set_sizes) < 2:
                    return reject()
                set_pauses = [pauses[group_blocks[pos-1]['ids'][0]] for pos in positions[1:-1]]
            rests = [pauses[b['ids'][0]] for b,next_b in zip(group_blocks,group_blocks[1:])
                     if next_b['ids'][0] not in starts]
            if set_pauses and (not rests or min(set_pauses) < 1.5*median(rests)):
                return reject()
            pause = f' p{math.floor(median(rests)+.5)}' if rests else ''
            count = len(group_blocks)
            # Both displayed alternatives must identify one unique stored
            # group; ambiguous duplicate labels cannot share clock bindings.
            reason = "Identical count/distance groups are ambiguous; combine identical repeated sets into one group and use set_start_laps."
            if (count, nominal) in distance_keys or (count, group_blocks[0]['target']) in time_keys:
                return reject()
            distance_keys.add((count, nominal))
            time_keys.add((count, group_blocks[0]['target']))
            distance_text = f'{count}×{nominal} m{zone}{pause}'
            time_text = f"{count}×{group_blocks[0]['target']//60}'{zone}{pause}"
            if set_sizes:
                set_pause = f" sp{math.floor(median(set_pauses)+.5)}"
                distance_text = f'{len(set_sizes)}×({set_sizes[0]}×{nominal} m{zone}{pause}){set_pause}'
                time_text = f"{len(set_sizes)}×({set_sizes[0]}×{group_blocks[0]['target']//60}'{zone}{pause}){set_pause}"
            distance_parts.append(distance_text)
            time_parts.append(time_text)
            for block in group_blocks:
                for i in block['ids']:
                    assignments[i-1].update(work_rep=True, ai_rep=block['ids'][0],
                        ai_group=group_index, ai_target_seconds=block['target'], ai_nominal_m=nominal)
        def boundary(ids):
            if not ids:
                return ''
            meters = sum(by_id[i]['distance_m'] for i in ids)
            zones = sorted({by_id[i]['zone'] for i in ids} & {'Z1','Z2'})
            zone = (' '+(zones[0] if len(zones)==1 else zones[0]+'>'+zones[-1])) if zones else ''
            return f'{math.floor(meters/50+.5)*50} m{zone}'
        if continuous:
            meters = sum(by_id[i]['distance_m'] for i in continuous)
            seconds = sum(by_id[i]['duration_s'] for i in continuous)
            nominal = math.floor(meters/50+.5)*50
            distance_parts.insert(0, f'{nominal} m Z1')
            for i in continuous:
                assignments[i-1].update(work_rep=True, ai_rep=continuous[0], ai_group=len(groups),
                    ai_target_seconds=round(seconds), ai_nominal_m=nominal)
        fields = {'wu':boundary(warmup), 'main':' + '.join(distance_parts), 'cd':boundary(cooldown)}
        time_fields = None if continuous or any(g.get('target_meters') is not None for g in groups) else dict(fields, main=' + '.join(time_parts))
        return {'training_fields':fields, 'time_fields':time_fields, 'assignments':assignments,
                'description':description(fields)}
    except (KeyError, TypeError, ValueError, ZeroDivisionError, OverflowError):
        return reject()


def description(fields):
    return f"WU: {fields.get('wu') or 'none'} · Main: {fields['main']} · CD: {fields.get('cd') or 'none'}"


def apply_lap_structure(part, loads, structure):
    if len(loads) != len(structure['assignments']):
        return False
    for load, assignment in zip(loads, structure['assignments']):
        load.update(assignment)
    options = []
    for label, fields in [('Distance',structure['training_fields']), ('Time',structure['time_fields'])]:
        if fields is None:
            continue
        options.append({'label':label, 'training_fields':dict(fields), 'description':description(fields), 'watch_loads':loads})
    part.update(training_fields=dict(structure['training_fields']), description=structure['description'],
                watch_loads=loads, training_alternatives=options)
    return True
