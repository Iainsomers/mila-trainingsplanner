"""Conversational Garmin analysis; models assign laps, code owns measurements."""
from copy import deepcopy
import json
import math
import os
from statistics import median
from urllib.request import Request, urlopen

from core.watch_ai_structure import description, representative_zones


SYSTEM = """You are MiLa, a thoughtful running-workout analyst talking with a coach or athlete.
Understand the WHOLE ordered recording before labeling it. Speak naturally in the user's language
(Dutch initially), explain your observations using lap numbers, answer questions and ask a focused
question when intent or evidence is ambiguous. Do not just repeat fixed rejection phrases.
Conversation and previous previews are context, never authority to invent measurements.
Varying pace/zones do not break repeated distance patterns. Recognize mixed sets such as
9*(200m-100m) or 2*(1700m-1200m-850m). Slow laps between efforts are recovery even when their
distance resembles work. A final complete rep needs no subsequent recovery. Adjacent autolaps
without recovery can form a larger rep. Z2 warmup is suspicious: discuss whether it is Main.
Ordinary kilometre autolaps in a continuous easy run are one continuous rep, not intervals.
Preserve unrelated parts when a user corrects only one block. Recount from original laps.
If the user accidentally ran one rep longer, discuss it; actual times always remain measured.
For an explanation/question return proposal:null. Do not say a training was saved or accepted.
Return JSON: {"reply":"natural helpful answer", "zone_basis":"auto" or "pace" or "hr", "proposal":null or
{"warmup_laps":[1], "cooldown_laps":[], "recovery_laps":[3],
"reps":[{"laps":[2],"target_meters":200},{"laps":[4],"target_meters":100}]}}.
For equal-distance sets (2x8x500m), add proposal.set_start_laps with the first work-lap
number of each set, including the first set. Sets must have equal sizes and measurably longer
recovery between sets. For mixed sets use the full chronological reps sequence; never group
all 200m reps before all 100m reps.
Use one-based original lap numbers. Every lap exactly once. Reps chronological, each containing
consecutive laps, never recovery. Targets: either integer target_meters (25..100000) or integer
target_seconds (30..1800), not both. Nominal meters must fit measured distance within max(30m,8%);
nominal seconds within max(15s,6%). If a request exceeds those bounds, explain what is supported
and ask about an alternative rather than forcing it. All WU before work, all CD after.
Exception: for exactly one accidentally LONGER timed rep, within max(60s,20%) above its target,
you may return confirmation_required:true alongside the full proposal. Explain the exact longer
measured time and ask for confirmation before using the nominal notation. Never claim it is
already applied. The server preserves all actual times and only permits this after explicit yes.
For continuous running put the consecutive running laps in ONE distance rep. Slow transfers
are recovery. Never infer unrecorded recovery duration. Your prose is not the usable training:
only a complete, checked lap assignment can update the preview. Do not output model-generated
pace, HR, zones, totals, training text or URLs; the server calculates those from measurements.
Users can say 'kijk naar snelheid ipv hr' or vice versa: set zone_basis accordingly and explain
the choice. Preserve the current basis unless asked to change it. auto uses end HR for reps
at least 400m OR 50s and pace for shorter reps. pace always uses speed, hr requests measured
end HR even on short reps. If HR is absent the server retains pace and reports that limitation.
For Alternative (elliptical, cycling, swimming, etc.) distance_m may be null. Discuss these just
as naturally. Use measured time and HR, never invent pace or distance. Propose the SAME schema,
but time targets only. Keep the recorded sport. All laps must still appear exactly once,
including warmup, cooldown and recovery. A whole continuous activity may be one time rep.
auto means HR for Alternative. If no speed was measured, explain that a speed-based zone
cannot be determined; offer HR/time instead. Preserve HR correction from current context.
Alternative time targets can be 1..86400 seconds, including one continuous long activity.
"""


def ask_model(facts, history, current=None, validation_error=None, *, timeout=20):
    key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not key:
        raise ValueError("Garmin E is not configured yet.")
    context = {"laps":facts, "current_checked_training":current, "validation_feedback":validation_error}
    body = {"model":os.environ.get("GARMIN_E_MODEL", "gpt-5.4-mini"),
            "reasoning_effort":"medium", "store":False,
            "response_format":{"type":"json_object"},
            "messages":[{"role":"system", "content":SYSTEM},
                        {"role":"user", "content":json.dumps(context)}] + history[-20:]}
    request = Request("https://api.openai.com/v1/chat/completions", data=json.dumps(body).encode(),
                      headers={"Authorization":"Bearer "+key, "Content-Type":"application/json"})
    with urlopen(request, timeout=timeout) as response:
        result = json.loads(response.read(200000))
    answer = json.loads(result["choices"][0]["message"]["content"])
    if not isinstance(answer,dict) or not isinstance(answer.get("reply"),str) or not answer["reply"].strip():
        raise ValueError("Garmin E returned an incomplete answer. Please try again.")
    answer["reply"] = answer["reply"].strip()[:6000]
    return answer


def lap_facts(part):
    if (part.get("training_fields") or {}).get("alt"):
        facts = []
        for i,load in enumerate(part.get("alternative_laps") or [],1):
            seconds = float(load["seconds"])
            if not math.isfinite(seconds) or seconds <= 0:
                raise ValueError("Alternative contains incomplete lap durations.")
            facts.append(dict(lap=i,distance_m=None,duration_s=seconds,zone=None,
                              avg_hr=load.get("average_hr"),end_hr=load.get("end_hr")))
        return facts
    facts = []
    for i, load in enumerate(part.get("watch_loads") or [], 1):
        meters, seconds = float(load["meters"]), float(load["seconds"])
        if not math.isfinite(meters+seconds) or meters < 0 or seconds <= 0:
            raise ValueError("The recording contains incomplete lap measurements.")
        facts.append(dict(lap=i, distance_m=meters, duration_s=seconds,
            zone="Z"+str(load.get("zone") or ""), avg_hr=load.get("average_hr"),
            end_hr=load.get("average_hr_last_15")))
    return facts


def checked_proposal(part, proposal, *, athlete=None, zone_basis="auto", confirmed_overrun=False):
    """Only measured, complete, chronologically bound proposals become usable."""
    if (part.get("training_fields") or {}).get("alt"):
        return checked_alternative(part,proposal,athlete=athlete,zone_basis=zone_basis,
                                   confirmed_overrun=confirmed_overrun)
    if not isinstance(proposal,dict):
        raise ValueError("No complete lap assignment was supplied.")
    facts = lap_facts(part)
    if not 1 <= len(facts) <= 200:
        raise ValueError("Use a recording with 1–200 measured laps.")
    used = set()
    def ids(values):
        if (not isinstance(values,list) or any(type(i) is not int or not 1 <= i <= len(facts) for i in values)
                or values != sorted(set(values)) or used.intersection(values)):
            raise ValueError("Lap numbers must be unique, chronological and from this recording.")
        used.update(values)
        return values
    wu = ids(proposal.get("warmup_laps",[]))
    cd = ids(proposal.get("cooldown_laps",[]))
    recovery = ids(proposal.get("recovery_laps",[]))
    reps = proposal.get("reps")
    if not isinstance(reps,list) or not 1 <= len(reps) <= 60:
        raise ValueError("Supply the measured work repetitions.")
    blocks, last, overruns = [], 0, 0
    for rep in reps:
        lap_ids = ids(rep["laps"])
        if not lap_ids or lap_ids != list(range(lap_ids[0],lap_ids[-1]+1)) or lap_ids[0] <= last:
            raise ValueError("Each work rep must contain consecutive laps in recorded order.")
        last = lap_ids[-1]
        rows = [facts[i-1] for i in lap_ids]
        meters, seconds = sum(r["distance_m"] for r in rows), sum(r["duration_s"] for r in rows)
        distance, duration = rep.get("target_meters"), rep.get("target_seconds")
        if (distance is None) == (duration is None):
            raise ValueError("Each rep needs exactly one nominal distance or duration.")
        raw_target = distance if distance is not None else duration
        if type(raw_target) is not int:
            raise ValueError("Nominal targets must be whole numbers.")
        target, measured, tolerance = (distance,meters,max(30,(distance or 0)*.08)) if distance is not None else (
            duration,seconds,max(15,(duration or 0)*.06))
        if type(target) is not int or not (25 <= target <= 100000 if distance is not None else 30 <= target <= 1800):
            raise ValueError("The nominal target is outside the supported range.")
        if abs(measured-target) > tolerance:
            if (confirmed_overrun and duration is not None and target < measured <= target+max(60,target*.2)):
                overruns += 1
                if overruns > 1:
                    raise ValueError("Only one modestly longer timed rep may be confirmed.")
            else:
                raise ValueError(f"Laps {lap_ids}: measured {measured:.1f}, requested {target}; these do not match.")
        # Merging automatic splits must not swallow a walking/slow recovery.
        if any(r["distance_m"]/r["duration_s"] < 2 for r in rows):
            raise ValueError(f"Laps {lap_ids}: a work rep includes a slow recovery or stop.")
        fastest = max(r["distance_m"]/r["duration_s"] for r in rows)
        if any(r["zone"] in {"Z1","Z2"} and r["distance_m"] <= 600 and r["duration_s"] >= 15
               and fastest > 1.5*r["distance_m"]/r["duration_s"] for r in rows):
            raise ValueError(f"Laps {lap_ids}: a much slower recovery is merged into a work rep.")
        blocks.append(dict(ids=lap_ids,meters=meters,seconds=seconds,distance=distance,duration=duration))
    if used != set(range(1,len(facts)+1)):
        raise ValueError("The proposal leaves source laps unassigned.")
    if (wu and max(wu) >= blocks[0]["ids"][0]) or (cd and min(cd) <= last):
        raise ValueError("Warmup must precede work and cooldown must follow it.")
    for i in wu+cd:
        row = facts[i-1]
        if row["zone"] not in {"Z1","Z2","Z","ZNA"} or row["distance_m"]/row["duration_s"] < 2:
            raise ValueError(f"Lap {i} is not supported as warmup/cooldown.")
    for i in recovery:
        row = facts[i-1]
        speed = row["distance_m"]/row["duration_s"]
        if row["zone"] not in {"Z1","Z2","Z","ZNA"}:
            raise ValueError(f"Lap {i} is too fast to discard as recovery.")
        neighbors = [b for b in blocks if b["ids"][-1] < i]
        before = neighbors[-1:]
        after = [b for b in blocks if b["ids"][0] > i][:1]
        if speed >= 2 and any(b["meters"]/b["seconds"] < 1.2*speed for b in before+after):
            raise ValueError(f"Lap {i} is not clearly slower than its neighboring work reps.")
    result = deepcopy(part)
    loads = result["watch_loads"]
    for i, load in enumerate(loads,1):
        for key in ("ai_rep","ai_group","ai_nominal_m","ai_target_seconds","nominal_rep_m"):
            load.pop(key,None)
        load.update(segment="WU" if i in wu else "CD" if i in cd else "CORE",work_rep=False)
    missing_hr = False
    if zone_basis not in {"auto","pace","hr"}:
        raise ValueError("Choose pace, hr or auto as zone basis.")
    if zone_basis != "pace" and athlete is not None:
        from core.garmin_d import hr_zone
        from core.watch_hr import tail_hr
        for block in blocks:
            if zone_basis == "auto" and block["meters"] < 400 and block["seconds"] < 50:
                continue
            rep_loads = [loads[i-1] for i in block["ids"]]
            label = hr_zone(athlete,tail_hr(rep_loads))
            if label:
                for load in rep_loads:
                    load["zone"] = label.removeprefix("Z")
            else:
                missing_hr = True
    def zone(rows):
        labels = representative_zones("Z"+str(loads[i-1].get("zone") or "") for i in rows)
        return " "+(labels[0] if len(labels)==1 else labels[0]+">"+labels[-1]) if labels else ""
    def boundary(rows):
        return f"{round(sum(facts[i-1]['distance_m'] for i in rows)/50)*50} m"+zone(rows) if rows else ""
    texts, groups = [], []
    for block in blocks:
        key = (block["distance"],block["duration"])
        if not groups or groups[-1][0] != key:
            groups.append((key,[]))
        groups[-1][1].append(block)
    for group_index, ((distance,duration), group) in enumerate(groups):
        label = f"{distance} m" if distance is not None else (f"{duration//60}'" if duration%60==0 else f"{duration}s")
        text = (f"{len(group)}×" if len(group)>1 else "")+label+zone([i for b in group for i in b["ids"]])
        pauses = [sum(facts[i-1]["duration_s"] for i in recovery if left["ids"][-1] < i < right["ids"][0])
                  for left,right in zip(group,group[1:])]
        if pauses and all(pauses):
            text += f" p{round(median(pauses))}"
        starts = proposal.get("set_start_laps") or []
        if starts:
            first_laps = [b["ids"][0] for b in group]
            if (len(groups)!=1 or not isinstance(starts,list) or any(type(i) is not int for i in starts)
                    or starts != sorted(set(starts)) or len(starts)<2 or starts[0] != first_laps[0]
                    or any(i not in first_laps for i in starts)):
                raise ValueError("Set starts must identify equal-size sets in this work group.")
            positions = [first_laps.index(i) for i in starts]+[len(group)]
            sizes = [b-a for a,b in zip(positions,positions[1:])]
            if len(set(sizes))!=1 or min(sizes)<2:
                raise ValueError("Sets must contain the same number of measured reps.")
            between = [pauses[p-1] for p in positions[1:-1]]
            ordinary = [pause for i,pause in enumerate(pauses,1) if i not in positions[1:-1]]
            if not ordinary or not all(ordinary) or min(between)<1.5*median(ordinary):
                raise ValueError("The measurements do not confirm longer recoveries between sets.")
            text = f"{len(starts)}×({sizes[0]}×{label}{zone([i for b in group for i in b['ids']])} p{round(median(ordinary))}) sp{round(median(between))}"
        texts.append(text)
        for block in group:
            for i in block["ids"]:
                loads[i-1].update(work_rep=True,ai_rep=block["ids"][0],ai_group=group_index,
                    ai_nominal_m=distance or round(block["meters"]/50)*50,
                    ai_target_seconds=duration or round(block["seconds"]))
    main = " // ".join(texts)
    distances = [b["distance"] for b in blocks]
    if all(d is not None for d in distances):
        from core.watch_processing import match_repeating_distance_sets
        for width in range(2,len(distances)//2+1):
            if (len(distances)%width or len(set(distances[:width]))<2
                    or distances != distances[:width]*(len(distances)//width)):
                continue
            pattern = " - ".join(f"{d} m" for d in distances[:width])
            matched = match_repeating_distance_sets(f"{len(distances)//width}×({pattern})",loads)
            if matched:
                main = matched[0]
            break
    result["training_fields"] = {"wu":boundary(wu),"main":main,"cd":boundary(cd)}
    result["description"] = description(result["training_fields"])
    result["e_usable"] = True
    result["e_zone_basis"] = zone_basis
    result["ai_structure_status"] = "e_validated"
    result.pop("training_alternatives",None)
    for key in ("ai_structure_reason","ai_structure_model","ai_structure_warning"):
        result.pop(key,None)
    if any(facts[i-1]["zone"]=="Z2" for i in wu):
        result["ai_structure_warning"] = "Warmup contains Z2 running. Check whether it belongs in Main."
    if missing_hr:
        result["e_zone_note"] = "Some reps lack usable HR or configured HR limits; their pace zone is retained."
    else:
        result["e_zone_note"] = {"pace":"Zones use measured speed.", "hr":"Zones use measured end-of-rep HR.",
                                 "auto":"Zones use end HR from 400m or 50s; shorter reps use speed."}[zone_basis]
    from core.garmin_d import hr_zone
    for row, original in zip(result.get("manual") or [],part["watch_loads"]):
        row["pace_z_pace"] = "Z"+str(original.get("zone") or "")
        value = row.get("hr_tail")
        hr = hr_zone(athlete,value) if athlete is not None else None
        row["hr_zone"] = "Z"+hr if hr else "NA"
    return result


def checked_alternative(part, proposal, *, athlete=None, zone_basis="auto", confirmed_overrun=False):
    """Bind duration-only Alternative proposals, preserving every recorded second."""
    if not isinstance(proposal,dict):
        raise ValueError("No complete Alternative lap assignment was supplied.")
    if zone_basis not in {"auto","hr"}:
        raise ValueError("Deze Alternative bevat geen gemeten snelheid. Gebruik tijd en hartslag.")
    facts = lap_facts(part)
    if not 1 <= len(facts) <= 200:
        raise ValueError("Use 1–200 measured Alternative laps.")
    used = set()
    def ids(values):
        if (not isinstance(values,list) or any(type(i) is not int or not 1 <= i <= len(facts) for i in values)
                or values != sorted(set(values)) or used.intersection(values)):
            raise ValueError("Alternative lap numbers must be chronological and assigned exactly once.")
        used.update(values)
        return values
    wu,cd,recovery = (ids(proposal.get(key,[])) for key in ("warmup_laps","cooldown_laps","recovery_laps"))
    reps = proposal.get("reps")
    if not isinstance(reps,list) or not 1 <= len(reps) <= 60:
        raise ValueError("Supply the measured Alternative work blocks.")
    blocks, last, overruns = [],0,0
    for rep in reps:
        indices = ids(rep["laps"])
        if not indices or indices != list(range(indices[0],indices[-1]+1)) or indices[0] <= last:
            raise ValueError("Alternative work blocks must use consecutive source laps in order.")
        last = indices[-1]
        seconds = sum(facts[i-1]["duration_s"] for i in indices)
        target = rep.get("target_seconds")
        if rep.get("target_meters") is not None or type(target) is not int or not 1 <= target <= 86400:
            raise ValueError("Alternative work targets must be measured durations, not distances.")
        if abs(seconds-target)>max(15,target*.06):
            if confirmed_overrun and target < seconds <= target+max(60,target*.2):
                overruns += 1
                if overruns>1:
                    raise ValueError("Only one modest longer work block can be confirmed.")
            else:
                raise ValueError(f"Laps {indices}: measured {seconds:g}s does not match {target}s.")
        # Do not swallow an intervening low-HR recovery into a larger rep.
        hrs = [facts[i-1].get("avg_hr") for i in indices]
        if len(hrs)>1 and all(isinstance(hr,(int,float)) for hr in hrs) and max(hrs)-min(hrs)>20:
            raise ValueError("A merged Alternative rep contains substantially different HR; keep recovery separate.")
        blocks.append((indices,target))
    if used != set(range(1,len(facts)+1)):
        raise ValueError("The Alternative proposal omits recorded laps.")
    if (wu and max(wu)>=blocks[0][0][0]) or (cd and min(cd)<=last):
        raise ValueError("Alternative warmup must precede work and cooldown must follow it.")
    roles = {i:"Warmup" for i in wu}
    roles.update({i:"Cooldown" for i in cd})
    roles.update({i:"Recovery" for i in recovery})
    block_at = {indices[0]:indices for indices,_ in blocks}
    correction = max(0,int(getattr(athlete,"alternative_hr_correction",10) or 0))
    from core.garmin_d import hr_zone
    texts, missing = [],False
    i = 1
    while i <= len(facts):
        indices = block_at.get(i,[i])
        rows = [facts[n-1] for n in indices]
        seconds = sum(row["duration_s"] for row in rows)
        hr_values = [(row.get("end_hr") or row.get("avg_hr"),row["duration_s"]) for row in rows]
        if all(isinstance(hr,(int,float)) and math.isfinite(hr) and 0<hr<300 for hr,_ in hr_values):
            value = sum(hr*duration for hr,duration in hr_values)/seconds
            label = hr_zone(athlete,value+correction) if athlete is not None else None
        else:
            label = None
        missing = missing or label is None
        duration = f"{int(seconds)//60}'" if seconds%60==0 else f"{seconds:g}s"
        role = roles.get(i,"Work")
        texts.append(f"{part.get('alternative_label','Alternative')} {role} {duration}"+(f" Z{label}" if label else ""))
        i = indices[-1]+1
    result = deepcopy(part)
    text = " // ".join(texts)
    result.update(training_fields={"alt":text},description=text,watch_loads=[],
                  e_usable=True,e_zone_basis="hr",ai_structure_status="e_validated")
    result["e_zone_note"] = f"Alternative zones use measured end HR (average HR when unavailable) +{correction} bpm."
    if missing:
        result["e_zone_note"] += " Some blocks have no usable HR/limits; their zone is left empty."
    result.pop("training_alternatives",None)
    return result
