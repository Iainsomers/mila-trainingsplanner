"""Validate AI lap assignments; derive all displayed numbers from measurements."""
import math
from statistics import median


class ValidatedDescription(str):
    def __new__(cls, structure):
        value = super().__new__(cls, structure['description'])
        value.structure = structure
        return value


def infer_lap_structure(facts):
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
        return validate_lap_structure({'confidence':1, 'lap_structure':proposal}, facts)
    except (KeyError, ValueError, TypeError, ZeroDivisionError, OverflowError):
        return None


def validate_lap_structure(data, facts):
    """No omitted/duplicate laps, invented reps, or running discarded as stops."""
    try:
        if not .75 <= float(data.get('confidence', 0)) <= 1:
            return None
        proposal = data['lap_structure']
        by_id = {row['lap']: row for row in facts}
        if len(by_id) != len(facts) or set(by_id) != set(range(1, len(facts)+1)):
            return None
        used = set()

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
        for i in stops:
            row = by_id[i]
            if not (row['duration_s'] >= 600 and row['distance_m']/row['duration_s'] < 1):
                raise ValueError
        for i in warmup + cooldown + recovery:
            if by_id[i]['zone'] not in {'Z1', 'Z2', '', 'NA'}:
                raise ValueError
        if any(by_id[i]['distance_m']/by_id[i]['duration_s'] < 2 for i in warmup + cooldown):
            return None
        groups = proposal['groups']
        if not isinstance(groups, list) or not 1 <= len(groups) <= 8:
            return None
        blocks, last = [], 0
        for group_index, group in enumerate(groups):
            reps = group['reps']
            distance_target = group.get('target_meters')
            target = group.get('target_seconds')
            distance_based = distance_target is not None
            if distance_based and (type(distance_target) is not int or distance_target % 50 or not 100 <= distance_target <= 10000 or target is not None):
                raise ValueError
            if not distance_based and (type(target) is not int or target % 60 or not 120 <= target <= 1800):
                raise ValueError
            if not isinstance(reps, list) or not 2 <= len(reps) <= 30:
                raise ValueError
            for rep in reps:
                ids = indices(rep)
                if not ids or ids != list(range(ids[0], ids[-1]+1)) or ids[0] <= last:
                    raise ValueError
                rows = [by_id[i] for i in ids]
                meters = sum(row['distance_m'] for row in rows)
                seconds = sum(row['duration_s'] for row in rows)
                if (not math.isfinite(meters+seconds) or meters <= 0 or seconds <= 0
                        or (abs(meters-distance_target) > distance_target*.08 if distance_based
                            else abs(seconds-target) > max(15, target*.06))
                        or any(row['distance_m']/row['duration_s'] < 2 for row in rows)):
                    raise ValueError
                blocks.append({'ids':ids, 'group':group_index, 'target':target or max(1, round(seconds)), 'distance_target':distance_target, 'meters':meters, 'seconds':seconds})
                last = ids[-1]
        if used != set(by_id) or len(blocks) < 3:
            return None
        first, last = blocks[0]['ids'][0], blocks[-1]['ids'][-1]
        if any(i >= first for i in warmup) or any(i <= last for i in cooldown):
            return None
        if any(i < first and by_id[i]["distance_m"]/by_id[i]["duration_s"] >= 2 for i in recovery):
            return None
        if any(i > last+1 for i in recovery):
            return None
        # Every rep boundary needs real, slower recovery; stop markers alone
        # cannot turn a continuous easy run into a series of intervals.
        pauses = {}
        for left, right in zip(blocks, blocks[1:]):
            gap = list(range(left['ids'][-1]+1, right['ids'][0]))
            if not gap or any(i not in recovery for i in gap):
                return None
            meters = sum(by_id[i]['distance_m'] for i in gap)
            seconds = sum(by_id[i]['duration_s'] for i in gap)
            speed = min(left['meters']/left['seconds'], right['meters']/right['seconds'])
            if not 30 <= seconds <= 600 or meters > 600 or speed < 1.4*meters/seconds:
                return None
            pauses[left['ids'][0]] = seconds
        assignments = [{'segment':'WU' if i in warmup else 'CD' if i in cooldown else 'CORE',
                        'work_rep':False} for i in range(1,len(facts)+1)]
        distance_parts, time_parts = [], []
        distance_keys, time_keys = set(), set()
        for group_index in range(len(groups)):
            group_blocks = [block for block in blocks if block['group']==group_index]
            nominal = group_blocks[0]['distance_target'] or int(math.floor(median(b['meters'] for b in group_blocks)/100+.5)*100)
            if any(abs(b['meters']-nominal) > nominal*.08 for b in group_blocks):
                return None
            zones = sorted({by_id[i]['zone'] for b in group_blocks for i in b['ids']} & {'Z1','Z2','Z3','Z4','Z5'})
            zone = (' '+(zones[0] if len(zones)==1 else zones[0]+'>'+zones[-1])) if zones else ''
            starts = groups[group_index].get('set_start_laps', [])
            set_sizes, set_pauses = [], []
            if starts:
                rep_starts = [b['ids'][0] for b in group_blocks]
                if (not isinstance(starts,list) or any(type(i) is not int for i in starts)
                        or starts != sorted(set(starts)) or starts[0] != rep_starts[0]
                        or any(i not in rep_starts for i in starts) or len(starts) < 2):
                    return None
                positions = [rep_starts.index(i) for i in starts] + [len(group_blocks)]
                set_sizes = [right-left for left,right in zip(positions,positions[1:])]
                if len(set(set_sizes)) != 1 or min(set_sizes) < 2:
                    return None
                set_pauses = [pauses[group_blocks[pos-1]['ids'][0]] for pos in positions[1:-1]]
            rests = [pauses[b['ids'][0]] for b,next_b in zip(group_blocks,group_blocks[1:])
                     if next_b['ids'][0] not in starts]
            if set_pauses and (not rests or min(set_pauses) < 1.5*median(rests)):
                return None
            pause = f' p{math.floor(median(rests)+.5)}' if rests else ''
            count = len(group_blocks)
            # Both displayed alternatives must identify one unique stored
            # group; ambiguous duplicate labels cannot share clock bindings.
            if (count, nominal) in distance_keys or (count, group_blocks[0]['target']) in time_keys:
                return None
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
        fields = {'wu':boundary(warmup), 'main':' + '.join(distance_parts), 'cd':boundary(cooldown)}
        time_fields = None if any(g.get('target_meters') is not None for g in groups) else dict(fields, main=' + '.join(time_parts))
        return {'training_fields':fields, 'time_fields':time_fields, 'assignments':assignments,
                'description':description(fields)}
    except (KeyError, TypeError, ValueError, ZeroDivisionError, OverflowError):
        return None


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
