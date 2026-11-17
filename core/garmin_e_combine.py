"""Compose E recordings by server-owned source IDs, never submitted lap data."""
from copy import deepcopy
import hashlib
import json
import math


def combine_recordings(results, selection):
    if not isinstance(selection,list) or not 2<=len(selection)<=3:
        raise ValueError("Select two or three activities.")
    if any(not isinstance(item,dict) or set(item)!={"start","role"} for item in selection):
        raise ValueError("Choose the activity and WU/Main/CD role.")
    starts = [item["start"] for item in selection]
    roles = [item["role"] for item in selection]
    if any(not isinstance(value,str) for value in starts+roles):
        raise ValueError("Invalid activity selection.")
    if (len(set(starts))!=len(starts) or len(set(roles))!=len(roles) or "main" not in roles
            or any(role not in {"wu","main","cd"} for role in roles)):
        raise ValueError("Select one Main and use each activity and role only once.")
    chosen = []
    for item in selection:
        matches = [session for session in results if session.get("start")==item["start"]]
        if len(matches)!=1:
            raise ValueError("A selected recording is unavailable. Reopen Garmin E.")
        source = matches[0]
        if len(source.get("parts") or [])!=1:
            raise ValueError("Choose recordings with one complete lap table.")
        part = source["parts"][0]
        fields = part.get("training_fields") or {}
        if not part.get("watch_loads") or fields.get("alt") or fields.get("alternative"):
            raise ValueError("Combine supports running recordings with measured laps.")
        if item["role"]=="main" and not fields.get("main"):
            raise ValueError("Choose an activity with a Main description as Main.")
        chosen.append((item,source))
    chosen.sort(key=lambda pair:pair[0]["start"])
    if [item["role"] for item,_ in chosen]!=[role for role in ("wu","main","cd") if role in roles]:
        raise ValueError("Use chronological order: WU, Main, CD.")
    ordered = [item for item,_ in chosen]
    identity = hashlib.sha256(json.dumps(ordered,sort_keys=True).encode()).hexdigest()
    fields = {"wu":"","main":"","cd":""}
    loads = []
    manual = []
    ranges = {}
    for item,source in chosen:
        part,role = source["parts"][0],item["role"]
        offset = len(loads)
        indices = []
        for load in part["watch_loads"]:
            meters,seconds = float(load["meters"]),float(load["seconds"])
            if not math.isfinite(meters+seconds) or meters<0 or seconds<=0:
                raise ValueError("A recording has incomplete lap measurements.")
            copy = deepcopy(load)
            copy.pop("combined_outer",None)
            if role == "main" and type(copy.get("ai_rep")) is int:
                copy["ai_rep"] += offset
            copy.update(recording_role=role,recording_start=item["start"])
            if role!="main":
                copy["segment"] = role.upper()
            indices.append(len(loads)+1)
            loads.append(copy)
        ranges[role] = indices
        for row in part.get("manual") or []:
            row = deepcopy(row)
            row["index"] = len(manual)+1
            manual.append(row)
        if role=="main":
            fields.update(part["training_fields"])
    for role in ("wu","cd"):
        if role not in ranges:
            continue
        if fields[role]:
            raise ValueError(f"Main already contains {role.upper()}; choose another recording or adjust Main first.")
        selected = [loads[i-1] for i in ranges[role]]
        meters = sum(float(load["meters"]) for load in selected)
        weights = {}
        for load in selected:
            zone = str(load.get("zone") or "")
            if zone in set("12345"):
                weights[zone] = weights.get(zone,0)+float(load["meters"])
        zone = max(weights,key=weights.get) if weights else ""
        fields[role] = f"{round(meters/50)*50} m"+(f" Z{zone}" if zone else "")
    from core.watch_ai_structure import description
    seconds = sum(float(load["seconds"]) for load in loads)
    hours = int(seconds//3600)
    minutes = int(seconds%3600//60)
    session = dict(name="Combined training",start=chosen[0][0]["start"],e_session_id=identity,
        e_requires_fit=any(source.get("is_fit_upload") for _,source in chosen),
        e_requires_push=any(not source.get("is_fit_upload") for _,source in chosen),
        distance=sum(float(load["meters"]) for load in loads),
        duration=f"{hours:02d}:{minutes:02d}:{seconds%60:06.3f}",
        parts=[dict(description=description(fields),training_fields=fields,watch_loads=loads,
                    manual=manual,auto=[],e_usable=False)])
    return session,ordered,ranges


def shifted_main_proposal(proposal, ranges):
    result = deepcopy(proposal)
    offset = ranges["main"][0]-1
    for field in ("warmup_laps","cooldown_laps","recovery_laps","ignored_laps","set_start_laps"):
        if field in result:
            result[field] = [i+offset for i in result[field]]
    for rep in result["reps"]:
        rep["laps"] = [i+offset for i in rep["laps"]]
    if isinstance(result.get("explicit_lap_zones"), dict):
        result["explicit_lap_zones"] = {str(int(i)+offset):zone for i,zone in result["explicit_lap_zones"].items()}
    result["warmup_laps"] = ranges.get("wu",[])+result.get("warmup_laps",[])
    result["cooldown_laps"] = result.get("cooldown_laps",[])+ranges.get("cd",[])
    return result
