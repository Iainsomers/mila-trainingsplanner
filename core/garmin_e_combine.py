"""Compose E recordings by server-owned source IDs, never submitted lap data."""
from copy import deepcopy
import hashlib
import json
import math


def append_watch_loads(existing, incoming):
    """Keep lap and group identities distinct between recordings."""
    rep_offset = max(len(existing), max((load["ai_rep"] for load in existing
                                         if type(load.get("ai_rep")) is int), default=0))
    group_offset = 1 + max((load.get("ai_group", -1) for load in existing
                            if type(load.get("ai_group")) is int), default=-1)
    added = deepcopy(incoming)
    for load in added:
        if type(load.get("ai_rep")) is int:
            load["ai_rep"] += rep_offset
        if type(load.get("ai_group")) is int:
            load["ai_group"] += group_offset
    return [*existing, *added]


def combine_recordings(results, selection):
    if not isinstance(selection,list) or not 2<=len(selection)<=5:
        raise ValueError("Select two to five activities.")
    if any(not isinstance(item,dict) or set(item)!={"start","role"} for item in selection):
        raise ValueError("Choose the activity and WU/Sprint/Main/CD role.")
    starts = [item["start"] for item in selection]
    roles = [item["role"] for item in selection]
    if any(not isinstance(value,str) for value in starts+roles):
        raise ValueError("Invalid activity selection.")
    role_order = ("wu", "sprint", "main", "cd")
    if (len(set(starts))!=len(starts) or any(roles.count(role)>1 for role in ("wu", "sprint", "cd"))
            or not 1 <= roles.count("main") <= 2
            or any(role not in role_order for role in roles)):
        raise ValueError("Select one or two Main recordings and at most one WU, Sprint and CD.")
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
        if item["role"] == "sprint" and (not part.get("e_usable") or not fields.get("main")):
            raise ValueError("Analyze the selected Sprint recording first.")
        if "sprint" in roles and item["role"] == "main" and not part.get("e_usable"):
            raise ValueError("Analyze the selected Main recording first.")
        if roles.count("main") == 2 and item["role"] == "main":
            if not part.get("e_usable"):
                raise ValueError("Analyze both Main recordings before combining.")
            ordered_mains = sorted(starts[i] for i, role in enumerate(roles) if role == "main")
            if ((fields.get("wu") and "sprint" not in roles and item["start"] != ordered_mains[0])
                    or (fields.get("cd") and item["start"] != ordered_mains[-1])):
                raise ValueError("Warmup must precede both Main blocks and cooldown must follow them.")
        chosen.append((item,source))
    chosen.sort(key=lambda pair:pair[0]["start"])
    if [item["role"] for item,_ in chosen]!=sorted(roles, key=role_order.index):
        raise ValueError("Use chronological order: WU, Sprint, Main, CD.")
    ordered = [item for item,_ in chosen]
    identity = hashlib.sha256(json.dumps(ordered,sort_keys=True).encode()).hexdigest()
    fields = {"wu":"","main":"","cd":""}
    loads = []
    manual = []
    ranges = {}
    for item,source in chosen:
        part,role = source["parts"][0],item["role"]
        recording_loads = []
        for load in part["watch_loads"]:
            meters,seconds = float(load["meters"]),float(load["seconds"])
            if not math.isfinite(meters+seconds) or meters<0 or seconds<=0:
                raise ValueError("A recording has incomplete lap measurements.")
            copy = deepcopy(load)
            copy.pop("combined_outer",None)
            copy.update(recording_role=role,recording_start=item["start"])
            if role == "sprint" and copy.get("segment") != "IGNORE":
                if copy.get("segment") != "WU" or "wu" in roles:
                    copy["segment"] = "SPR"
            elif role == "main" and "sprint" in roles and copy.get("segment") == "WU":
                copy.update(segment="CORE", work_rep=False)
            elif role in ("wu", "cd"):
                copy["segment"] = role.upper()
            recording_loads.append(copy)
        ranges.setdefault(role, []).extend(range(len(loads)+1, len(loads)+len(recording_loads)+1))
        loads = append_watch_loads(loads, recording_loads)
        for row in part.get("manual") or []:
            row = deepcopy(row)
            row["index"] = len(manual)+1
            manual.append(row)
        if role == "sprint":
            fields["sprint"] = part["training_fields"]["main"]
            if "wu" not in roles:
                fields["wu"] = part["training_fields"].get("wu", "")
        elif role=="main":
            source_fields = part["training_fields"]
            fields["main"] = " // ".join(filter(None, (fields["main"], source_fields["main"])))
            for boundary in ("wu", "cd"):
                if boundary == "wu" and "sprint" in roles:
                    continue
                if source_fields.get(boundary):
                    fields[boundary] = source_fields[boundary]
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
