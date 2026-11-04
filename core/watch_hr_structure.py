"""Conservative fallback for repeated distance work hidden by all-Z1 pace labels."""
from copy import deepcopy
import math
from statistics import median
from core.garmin_d import hr_zone
from core.watch_hr import tail_hr


def apply_hr_distance_structure(part, loads, athlete):
    if not loads or any(not isinstance(l, dict) or str(l.get('zone')) != '1' for l in loads):
        return False
    try:
        rows = [(float(l['meters']), float(l['seconds']), tail_hr([l])) for l in loads]
        if any(not math.isfinite(m+s) or m < 0 or s <= 0 or hr is None for m,s,hr in rows):
            return False
        zones = [hr_zone(athlete, hr) for _,_,hr in rows]
        if any(z is None for z in zones):
            return False
        work = [i for i,(m,s,hr) in enumerate(rows) if zones[i] in {'2','3','4','5'}]
        if len(work) < 4:
            return False
        nominal = int(math.floor(median(rows[i][0] for i in work)/100+.5)*100)
        if not 800 <= nominal <= 6000 or any(
                abs(rows[i][0]-nominal) > nominal*.05 or rows[i][1] < 120
                or not 2.5 <= rows[i][0]/rows[i][1] <= 8 for i in work):
            return False
        durations = [rows[i][1] for i in work]
        if max(durations) > min(durations)*1.15:
            return False
        rests = []
        for left,right in zip(work,work[1:]):
            gap = list(range(left+1,right))
            if not gap or any(zones[i] != '1' or rows[i][2] > min(rows[left][2],rows[right][2])-15 for i in gap):
                return False
            meters,seconds = sum(rows[i][0] for i in gap),sum(rows[i][1] for i in gap)
            if (not 30 <= seconds <= 900 or meters > nominal*1.25
                    or min(rows[left][0]/rows[left][1],rows[right][0]/rows[right][1]) < 1.15*meters/seconds):
                return False
            rests.append(seconds)
        if any(zones[i] != '1' or rows[i][0]/rows[i][1] < 2 for i in range(work[0])):
            return False
        if any(zones[i] != '1' for i in range(work[-1]+1,len(rows))):
            return False
        cooldown = next((i for i in range(work[-1]+1,len(rows)) if rows[i][0] >= 800 and rows[i][0]/rows[i][1] >= 2),len(rows))
        if any(rows[i][0]/rows[i][1] < 2 for i in range(cooldown,len(rows))):
            return False
        def boundary(indices):
            meters = sum(rows[i][0] for i in indices)
            return f'{int(math.floor(meters/50+.5)*50)} m Z1' if meters else ''
        fields = {'wu':boundary(range(work[0])), 'main':f'{len(work)}×{nominal} m Z1 p{int(math.floor(median(rests)+.5))}',
                  'cd':boundary(range(cooldown,len(rows)))}
        updated = deepcopy(loads)
        for i,load in enumerate(updated):
            load.update(segment='WU' if i < work[0] else 'CD' if i >= cooldown else 'CORE',work_rep=i in work)
            if i in work:
                load.update(ai_rep=i+1,ai_group=0,ai_target_seconds=int(round(rows[i][1])),ai_nominal_m=nominal)
        from core.watch_ai_structure import description
        part.update(training_fields=fields,description=description(fields),watch_loads=updated)
        part.pop('training_alternatives',None)
        return True
    except (KeyError,TypeError,ValueError,ZeroDivisionError,OverflowError):
        return False
