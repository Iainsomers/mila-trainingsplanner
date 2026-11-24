"""Conversational Garmin analysis; models assign laps, code owns measurements."""
from copy import deepcopy
import json
import math
import os
import re
from statistics import median
from urllib.request import Request, urlopen

from core.watch_ai_structure import description, representative_zones


SYSTEM = """You are MiLa, a thoughtful running-workout analyst talking with a coach or athlete.
Understand the WHOLE ordered recording before labeling it. Speak naturally in the user's language
(Dutch initially), explain your observations using lap numbers, answer questions and ask a focused
question when intent or evidence is ambiguous. Do not just repeat fixed rejection phrases.
Conversation and previous previews are context, never authority to invent measurements.
On initial analysis, return the COMPLETE proposal immediately whenever the measurements support
one. Do not ask 'shall I make this a proposal?' or wait for an apply/use message. The user reviews
it using the existing Use/Add buttons. Questions are only needed for real uncertainty, not to
turn a supported pattern into a usable result. Do not discuss JSON, server internals or inability
to create UI buttons in your reply; describe the training and any genuine data limitation.
Some recordings were combined with user-selected recording_role wu/main/cd. Respect that
composition when interpreting the complete lap order; discuss conflicts rather than losing laps.
Varying pace/zones do not break repeated distance patterns. Recognize mixed sets such as
9*(200m-100m) or 2*(1700m-1200m-850m). Slow laps between efforts are recovery even when their
distance resembles work. A final complete rep needs no subsequent recovery. Adjacent autolaps
without recovery can form a larger rep. Z2 warmup is suspicious: discuss whether it is Main.
For interval recognition first inspect the chronological alternation WORK - RECOVERY -
WORK - RECOVERY. Use repeated distances OR repeated durations and relative measured speed
to identify the roles. Assign zones only AFTER choosing rep boundaries. The same work
series may progress through Z1, Z2, Z3, Z4 or higher without becoming separate series.
Likewise recovery may still carry a high HR/pace zone: HR can lag after an effort and
absolute zones do not decide the role. For running recovery, verify that both neighboring
complete work reps are at least 20 percent faster than the recovery; do not label a lap
recovery merely because it alternates or has a low zone. A genuinely ambiguous alternating
sequence must remain ambiguous. Do not split one set at each zone change. Keep distinct
distance steps in a mixed set in their actual order. Never reorder laps by zone or distance.
Do not confuse ordinary continuous kilometre autolaps with intervals: repeated work-like
laps without measured recovery are one continuous effort. First/last work reps need only
the recovery actually present; never invent a missing final pause.
Prefer time targets when at least three consecutive work laps are all tightly clustered around
the same whole-minute duration while their measured distances vary. For example, eight laps of
exactly 3:00 measuring roughly 750-800m are 8x3 minutes, not alternating 750m/800m reps.
Ordinary kilometre autolaps in a continuous easy run are one continuous rep, not intervals.
Running laps slower than 10:00/km are rest, including long transfers before warmup or
after cooldown. Assign them to recovery, never warmup/cooldown or work. Their measured
duration may contribute to recovery pauses, but their distance is not running mileage.
Preserve unrelated parts when a user corrects only one block. Recount from original laps.
If the user accidentally ran one rep longer, discuss it; actual times always remain measured.
For an explanation/question return proposal:null. Do not say a training was saved or accepted.
Return JSON: {"reply":"natural helpful answer", "intent":"discuss" or "update",
"zone_basis":"auto" or "pace" or "hr", "proposal":null or
{"warmup_laps":[1], "cooldown_laps":[], "recovery_laps":[3], "ignored_laps":[],
"reps":[{"laps":[2],"target_meters":200},{"laps":[4],"target_meters":100}]}}.
When the user explicitly assigns a zone range to a distance group, the server can preserve that
literal correction in the checked preview. Do not invent this field from measurements. Return
proposal.zone_labels only for a user-stated correction, for example
[{"target_meters":250,"count":6,"label":"Z3>Z5"}].
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
pace, HR, totals, training text or URLs; the server calculates those from measurements.
Only the validated Alternative presentation schema below can request a supported summary zone.
For Alternative, an explicit user correction such as `45s Z1 and 30s Z2` labels every matching
measured-duration block in that chronological pattern. It does not by itself decide which laps
are work or recovery and never permits reordering. Return the complete assignment matching the
stated lap order; the server separately validates every source lap and duration.
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
When the user wants a compact Alternative notation, include proposal.format:"compact" and
optional proposal.presentation:{"warmup_seconds":900,"recovery_seconds":300,"work_zone":"2",
"recovery_zone":"1"}. Keep the complete source assignment. Work times come from each rep's
target_seconds. Boundary/recovery nominal times must fit max(30s,6%) of measured time.
Summary zones must be supported by at least half of the measured blocks of that role;
actual HR-derived zones and exact seconds remain separately preserved for totals.
For a strictly ascending or descending Alternative work sequence with equal recovery, work_zone
may be a measured range such as "2>3". Both boundary zones must occur and every work block must
fall inside that range. Then use one compact sequence with the shared pause, not repeated
Work/Recovery labels (for example 1×(12' - 10' - 8') Z2>Z3 p1).
Example 930s warmup, 604/601/601/601s work with 300/300/323/307s recoveries, and final
388s work can display 15' Z1 // 4×(10' Z2 - 5' Z1) // 6'28 Z2 when those zones are supported.
This is only an illustration, never a default workout.
CRITICAL: agreeing in prose does NOT change the usable preview. If the user corrects an
assignment, agrees to a proposed correction, says they cannot see the proposal, or asks to
use/apply it for AM/PM, return intent:update AND the complete updated proposal, preserving
all untouched laps. Never answer 'this is your AM proposal' with proposal:null.
For explanation-only answers use intent:discuss and proposal:null.
If the requested change cannot be supported, explain the specific mismatch; do not pretend
that the preview changed. Current checked fields remain authoritative until validation.
When the user explicitly asks to ignore measured transition/noise laps, put them in ignored_laps.
Ignored laps remain visible as source measurements but do not belong to WU, Main, recovery or CD
and do not count toward saved training totals. Never use ignored_laps merely to bypass a mismatch
in a requested work rep; only use it for laps the user explicitly excludes from the training.
Do not ask for another confirmation when the user has already agreed, except for the bounded
longer-time exception. Alternative defaults to chronological measured blocks. To change the
actual usable notation, supply format:compact with presentation and a complete assignment.
A compact spoken summary alone changes neither the preview nor measured HR-derived totals.
"""


def ask_model(facts, history, current=None, validation_error=None, *, timeout=20):
    key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not key:
        raise ValueError("Garmin E is not configured yet.")
    context = {"laps":facts, "current_checked_training":current, "validation_feedback":validation_error}
    body = {"model":os.environ.get("GARMIN_E_MODEL", "gpt-5.4-mini"),
            "reasoning_effort":"low", "store":False,
            "response_format":{"type":"json_object"},
            "messages":[{"role":"system", "content":SYSTEM},
                        {"role":"user", "content":json.dumps(context)}] + [
                            {"role":m["role"],"content":m["content"]} for m in history[-20:]]}
    request = Request("https://api.openai.com/v1/chat/completions", data=json.dumps(body).encode(),
                      headers={"Authorization":"Bearer "+key, "Content-Type":"application/json"})
    with urlopen(request, timeout=timeout) as response:
        result = json.loads(response.read(200000))
    answer = json.loads(result["choices"][0]["message"]["content"])
    if not isinstance(answer,dict) or not isinstance(answer.get("reply"),str) or not answer["reply"].strip():
        raise ValueError("Garmin E returned an incomplete answer. Please try again.")
    answer["reply"] = answer["reply"].strip()[:6000]
    return answer


def apply_explicit_zone_labels(proposal, message):
    """Attach literal user-stated lap, duration or distance zone labels to a proposal."""
    if not isinstance(proposal, dict) or not isinstance(message, str):
        return proposal, False
    lap_zone = re.search(r"\blap\s*(\d+)\b.{0,30}?\bz\s*([1-6])\b", message, re.I)
    if lap_zone:
        updated = deepcopy(proposal)
        overrides = dict(updated.get("explicit_lap_zones") or {})
        overrides[lap_zone[1]] = lap_zone[2]
        updated["explicit_lap_zones"] = overrides
        return updated, True
    duration_pattern = re.compile(
        r"(\d+(?:[.,]\d+)?)\s*(\"|″|s(?:ec(?:onden?)?)?|['′]|min(?:u(?:ut|ten)?)?)"
        r"\s*(?:=|is|:)?\s*z\s*([1-6])\b", re.I,
    )
    duration_zones = {}
    for duration, unit, zone in duration_pattern.findall(message):
        seconds = float(duration.replace(",", "."))
        if unit.lower().startswith("min") or unit in {"'", "′"}:
            seconds *= 60
        if 1 <= seconds <= 86400:
            duration_zones[str(round(seconds))] = zone
    if duration_zones:
        updated = deepcopy(proposal)
        existing = dict(updated.get("explicit_duration_zones") or {})
        existing.update(duration_zones)
        updated["explicit_duration_zones"] = existing
        return updated, True
    # Explicit boundary corrections are user input, not inferred HR facts.
    boundary = re.search(r"(?:eerste|1e|wu|warm[ -]?up).*?\bz\s*([1-6])\b", message, re.I)
    cooldown = re.search(r"(?:cd|cool[ -]?down).*?\bz\s*([1-6])\b", message, re.I)
    if (boundary or cooldown) and any(rep.get("target_seconds") for rep in proposal.get("reps", []) if isinstance(rep, dict)):
        updated = deepcopy(proposal)
        overrides = dict(updated.get("explicit_role_zones") or {})
        if boundary:
            overrides["Warmup"] = boundary[1]
        if cooldown:
            overrides["Cooldown"] = cooldown[1]
        updated["explicit_role_zones"] = overrides
        return updated, True

    # A literal short-sprint sequence identifies its work reps by order, not
    # by a single distance-group key. This lets a trainer correct mixed short
    # targets such as 60-70-80-70-60 m to Z6 even when a distance repeats or
    # some measured reps already carry Z6.
    short_sequence = re.search(
        r"(?:(\d+)\s*[×x*]\s*)?\(\s*([^()]*)\)\s*z\s*6\b",
        message,
        re.IGNORECASE,
    )
    if short_sequence:
        sequence_text = short_sequence.group(2)
        if re.fullmatch(r"\s*\d+\s*m?(?:\s*(?:[-–—]|//?)\s*\d+\s*m?)+\s*", sequence_text, re.I):
            distances = [int(value) for value in re.findall(r"\d+", sequence_text)]
            distances *= int(short_sequence.group(1) or 1)
            reps = proposal.get("reps") if isinstance(proposal.get("reps"), list) else []
            targets = [rep.get("target_meters") if isinstance(rep, dict) else None for rep in reps]
            if distances and all(25 <= value < 100 for value in distances):
                starts = [
                    index for index in range(len(targets) - len(distances) + 1)
                    if targets[index:index + len(distances)] == distances
                ]
                if len(starts) == 1:
                    updated = deepcopy(proposal)
                    overrides = dict(updated.get("explicit_lap_zones") or {})
                    selected = reps[starts[0]:starts[0] + len(distances)]
                    for rep in selected:
                        for lap in rep.get("laps", []):
                            overrides[str(lap)] = "6"
                    updated["explicit_lap_zones"] = overrides
                    updated["explicit_sprint_sequences"] = [{
                        "first_lap": selected[0]["laps"][0],
                        "targets": distances,
                        "zone": "6",
                    }]
                    return updated, True
    # An explicit follow-up about the already checked work blocks can set one
    # literal zone on every work rep. This is server-enforced user intent, not
    # a model inference. WU, recovery, cooldown, set starts and measurements
    # are deliberately left untouched.
    direct_work_zone = re.search(
        r"(?:maak|zet|verander|wijzig|corrigeer|pas|change|make|set|correct|update)"
        r".{0,100}?\bz\s*([1-6])\b",
        message,
        re.IGNORECASE,
    )
    work_reference = re.search(
        r"\b(?:werk(?:blokken?|reps?|stukken?)|hoofdblokken?|main|interval(?:len|blokken?)?|reps?)\b",
        message,
        re.IGNORECASE,
    )
    reps = proposal.get("reps") if isinstance(proposal.get("reps"), list) else []
    all_short_reps = reps and all(
            isinstance(rep, dict)
            and type(rep.get("target_meters")) is int
            and 25 <= rep["target_meters"] < 100
            and isinstance(rep.get("laps"), list)
            and rep["laps"]
            for rep in reps
        )
    # Keep the concise short-sprint correction introduced earlier: with an
    # all-short checked Main, "maak er Z6 van" is itself unambiguous.
    if direct_work_zone and reps and (work_reference or (direct_work_zone[1] == "6" and all_short_reps)):
        if all(
            isinstance(rep, dict)
            and isinstance(rep.get("laps"), list)
            and rep["laps"]
            for rep in reps
        ):
            updated = deepcopy(proposal)
            overrides = dict(updated.get("explicit_lap_zones") or {})
            for rep in reps:
                for lap in rep["laps"]:
                    overrides[str(lap)] = direct_work_zone[1]
            updated["explicit_lap_zones"] = overrides
            # A previous model-generated group range must not override the
            # trainer's later literal correction.
            updated["zone_labels"] = []
            return updated, True
    pattern = re.compile(
        r"(?:(\d+)\s*[×x*]\s*)?(\d+)\s*m\b.{0,24}?"
        r"\bZ\s*([1-6])(?:\s*(?:>|→|-|tot)\s*Z?\s*([1-6]))?\b",
        re.IGNORECASE,
    )
    labels = []
    for match in pattern.finditer(message):
        count, target, first, last = match.groups()
        labels.append({
            "target_meters": int(target),
            "count": int(count or 1),
            "label": f"Z{first}>Z{last}" if last else f"Z{first}",
        })
    if not labels:
        return proposal, False
    updated = deepcopy(proposal)
    remaining_labels = []
    lap_overrides = dict(updated.get("explicit_lap_zones") or {})
    proposal_reps = updated.get("reps") if isinstance(updated.get("reps"), list) else []
    for item in labels:
        if item["target_meters"] < 100 and item["label"] == "Z6":
            matching_reps = [
                rep for rep in proposal_reps
                if isinstance(rep, dict) and rep.get("target_meters") == item["target_meters"]
            ]
            if len(matching_reps) == item["count"]:
                for rep in matching_reps:
                    for lap in rep.get("laps", []):
                        lap_overrides[str(lap)] = "6"
                continue
        remaining_labels.append(item)
    if lap_overrides:
        updated["explicit_lap_zones"] = lap_overrides
    existing = updated.get("zone_labels") if isinstance(updated.get("zone_labels"), list) else []
    replaced = {(item["target_meters"], item["count"]) for item in remaining_labels}
    updated["zone_labels"] = [
        item for item in existing
        if isinstance(item, dict) and (item.get("target_meters"), item.get("count")) not in replaced
    ] + remaining_labels
    return updated, True


def explicit_alternative_compact_proposal(facts, message):
    """Translate a user-written WU–repeated pair–optional tail–CD notation.

    This parses explicit intent, not a particular workout pattern. Every atom
    must still match the next measured lap before the ordinary validator runs.
    """
    if not isinstance(facts, list) or not isinstance(message, str):
        return None
    notation = re.search(
        r"\b(?:wu|warm[ -]?up)\b\s*[-–—/]\s*(\d+)\s*[×x*]\s*\(([^()]*)\)"
        r"(.*?)\s*[-–—/]\s*\b(?:cd|cool[ -]?down)\b",
        message, re.I,
    )
    if not notation:
        return None
    count = int(notation[1])
    if not 1 <= count <= 60:
        return None

    atom_pattern = re.compile(
        r"^\s*(\d+(?:[.,]\d+)?)\s*(\"|″|s(?:ec(?:onden?)?)?|['′]|min(?:u(?:ut|ten)?)?)"
        r"\s*z\s*([1-6])\s*$", re.I,
    )
    def atom(value):
        match = atom_pattern.match(value)
        if not match:
            return None
        seconds = float(match[1].replace(",", "."))
        if match[2].lower().startswith("min") or match[2] in {"'", "′"}:
            seconds *= 60
        if not 1 <= seconds <= 86400:
            return None
        return round(seconds), match[3]

    pair_values = re.split(r"\s*[-–—/]\s*", notation[2].strip())
    pair = [atom(value) for value in pair_values]
    if len(pair) != 2 or any(value is None for value in pair):
        return None
    tail_text = notation[3].strip().strip("-–—/ ")
    tail_values = [] if not tail_text else re.split(r"\s*[-–—/]\s*", tail_text)
    tail = [atom(value) for value in tail_values]
    if any(value is None for value in tail):
        return None

    expected = [pair[index % 2] for index in range(count * 2)] + tail
    if len(facts) != len(expected) + 2:
        return None
    for fact, (target, _zone) in zip(facts[1:-1], expected):
        try:
            measured = float(fact["duration_s"])
        except (KeyError, TypeError, ValueError):
            return None
        if not math.isfinite(measured) or abs(measured - target) > max(2, target * .06):
            return None

    work_laps = list(range(2, 2 + count * 2, 2))
    recovery_laps = list(range(3, 2 + count * 2, 2))
    tail_laps = list(range(2 + count * 2, len(facts)))
    proposal = {
        "warmup_laps": [1], "cooldown_laps": [len(facts)],
        "recovery_laps": recovery_laps, "ignored_laps": [],
        "reps": [
            {"laps": [lap], "target_seconds": pair[0][0]} for lap in work_laps
        ] + [
            {"laps": [lap], "target_seconds": target[0]}
            for lap, target in zip(tail_laps, tail)
        ],
        "format": "compact",
        "presentation": {
            "warmup_seconds": round(float(facts[0]["duration_s"])),
            "cooldown_seconds": round(float(facts[-1]["duration_s"])),
            "work_zone": pair[0][1], "recovery_zone": pair[1][1],
        },
        "explicit_duration_zones": {},
    }
    for seconds, zone in [*pair, *tail]:
        existing = proposal["explicit_duration_zones"].get(str(seconds))
        if existing is not None and existing != zone:
            return None
        proposal["explicit_duration_zones"][str(seconds)] = zone
    return proposal


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
        if load.get("recording_role"):
            facts[-1]["recording_role"] = load["recording_role"]
    return facts


def complete_partial_running_proposal(part, proposal):
    """Preserve measured-preview work reps when a model only changes boundaries.

    This does not recognize a new set pattern. It translates existing work-rep
    markers and keeps otherwise unassigned running-speed laps as individual reps,
    producing the complete assignment required by ``checked_proposal``.
    """
    if not isinstance(proposal, dict) or proposal.get("reps"):
        return proposal
    if not any(key in proposal for key in ("warmup_laps", "cooldown_laps")):
        return proposal
    if (part.get("training_fields") or {}).get("alt"):
        return proposal
    loads = part.get("watch_loads") or []
    if not loads:
        return proposal

    def clean_ids(key):
        values = proposal.get(key, [])
        if not isinstance(values, list) or any(type(value) is not int for value in values):
            return None
        return values

    warmup_supplied = "warmup_laps" in proposal
    cooldown_supplied = "cooldown_laps" in proposal
    warmup = clean_ids("warmup_laps")
    cooldown = clean_ids("cooldown_laps")
    supplied_recovery = clean_ids("recovery_laps")
    ignored = clean_ids("ignored_laps")
    if warmup is None or cooldown is None or supplied_recovery is None or ignored is None:
        return proposal
    if not warmup_supplied:
        warmup = [index for index, load in enumerate(loads, 1) if load.get("segment") == "WU"]
    if not cooldown_supplied:
        cooldown = [index for index, load in enumerate(loads, 1) if load.get("segment") == "CD"]
    boundaries = set(warmup + cooldown)
    ignored_set = set(ignored)
    if boundaries.intersection(ignored_set):
        return proposal

    groups = []
    for index, load in enumerate(loads, 1):
        if index in boundaries or index in ignored_set:
            continue
        is_measured_work = load.get("work_rep") is True
        meters, seconds = float(load.get("meters") or 0), float(load.get("seconds") or 0)
        # A fast, otherwise unassigned lap cannot honestly be called recovery.
        # Keep it as its own measured rep; do not infer a set or merge pattern.
        is_fast_unassigned = not is_measured_work and seconds > 0 and meters / seconds >= 2.5
        if not is_measured_work and not is_fast_unassigned:
            continue
        rep_key = load.get("ai_rep") if is_measured_work and type(load.get("ai_rep")) is int else index
        if (is_measured_work and groups and groups[-1][0] == rep_key
                and groups[-1][1][-1] == index - 1):
            groups[-1][1].append(index)
        else:
            groups.append((rep_key, [index]))
    if not groups:
        return proposal

    reps = []
    for _, lap_ids in groups:
        rows = [loads[index - 1] for index in lap_ids]
        target_seconds = next((row.get("ai_target_seconds") for row in rows
                               if type(row.get("ai_target_seconds")) is int), None)
        target_meters = next((row.get("ai_nominal_m") for row in rows
                              if type(row.get("ai_nominal_m")) is int), None)
        if target_meters is None:
            target_meters = next((row.get("nominal_rep_m") for row in rows
                                  if type(row.get("nominal_rep_m")) is int), None)
        if target_seconds is not None:
            reps.append({"laps": lap_ids, "target_seconds": target_seconds})
        else:
            measured = sum(float(row.get("meters") or 0) for row in rows)
            target_meters = target_meters or max(25, round(measured / 50) * 50)
            reps.append({"laps": lap_ids, "target_meters": target_meters})

    used = boundaries | ignored_set | {lap_id for rep in reps for lap_id in rep["laps"]}
    recovery = sorted(set(supplied_recovery) | (set(range(1, len(loads) + 1)) - used))
    completed = deepcopy(proposal)
    completed.update(
        warmup_laps=sorted(warmup),
        cooldown_laps=sorted(cooldown),
        recovery_laps=recovery,
        ignored_laps=sorted(ignored),
        reps=reps,
    )
    return completed


def prefer_measured_time_groups(part, proposal):
    """Canonicalize clear whole-minute work groups to time targets."""
    if not isinstance(proposal, dict) or not isinstance(proposal.get("reps"), list):
        return proposal, False
    if (part.get("training_fields") or {}).get("alt"):
        return proposal, False
    facts = lap_facts(part)
    reps = deepcopy(proposal["reps"])
    changed = False
    index = 0
    while index < len(reps):
        if not isinstance(reps[index], dict) or reps[index].get("target_meters") is None:
            index += 1
            continue
        run = []
        cursor = index
        while cursor < len(reps):
            rep = reps[cursor]
            if not isinstance(rep, dict):
                break
            lap_ids = rep.get("laps")
            if rep.get("target_meters") is None or not isinstance(lap_ids, list) or not lap_ids:
                break
            try:
                seconds = sum(float(facts[lap_id - 1]["duration_s"]) for lap_id in lap_ids)
                meters = sum(float(facts[lap_id - 1]["distance_m"]) for lap_id in lap_ids)
            except (IndexError, TypeError, ValueError):
                break
            minute_target = round(seconds / 60) * 60
            if minute_target < 60 or abs(seconds - minute_target) > max(2, minute_target * .02):
                break
            if run and minute_target != run[0][2]:
                break
            run.append((cursor, meters, minute_target))
            cursor += 1
        if len(run) >= 3:
            measured = [item[1] for item in run]
            median_meters = median(measured)
            if max(measured) - min(measured) >= max(30, median_meters * .04):
                for rep_index, _meters, target_seconds in run:
                    reps[rep_index].pop("target_meters", None)
                    reps[rep_index]["target_seconds"] = target_seconds
                changed = True
        index = max(cursor, index + 1)
    if not changed:
        return proposal, False
    result = deepcopy(proposal)
    result["reps"] = reps
    return result, True


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
    from core.watch_processing import is_walking_load
    resting = {row["lap"] if "lap" in row else index
               for index, row in enumerate(facts, 1)
               if row["distance_m"] == 0 or is_walking_load(row["distance_m"], row["duration_s"])}
    proposal = deepcopy(proposal)
    # Rest remains in the source assignment and pause durations, regardless
    # of an AI boundary label or an omitted long transfer.
    if resting:
        for key in ("warmup_laps", "cooldown_laps"):
            if isinstance(proposal.get(key), list):
                proposal[key] = [i for i in proposal[key] if i not in resting]
        reps = proposal.get("reps")
        if isinstance(reps, list):
            proposal["reps"] = [rep for rep in reps if not (
                isinstance(rep, dict) and isinstance(rep.get("laps"), list)
                and rep["laps"] and all(i in resting for i in rep["laps"]))]
        work_ids = {i for rep in proposal.get("reps", []) if isinstance(rep, dict)
                    for i in rep.get("laps", [])} if isinstance(proposal.get("reps"), list) else set()
        ignored_ids = proposal.get("ignored_laps", [])
        recoveries = proposal.get("recovery_laps", [])
        if isinstance(recoveries, list) and isinstance(ignored_ids, list):
            proposal["recovery_laps"] = sorted(set(recoveries) | (resting - work_ids - set(ignored_ids)))
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
    ignored = ids(proposal.get("ignored_laps",[]))
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
        explicit = (proposal.get("explicit_lap_zones") or {}).get(str(i))
        boundary_zone = "Z" + explicit if explicit in {"1", "2"} else row["zone"]
        if boundary_zone not in {"Z1","Z2","Z","ZNA"} or row["distance_m"]/row["duration_s"] < 2:
            raise ValueError(f"Lap {i} is not supported as warmup/cooldown.")
    for i in recovery:
        row = facts[i-1]
        if i in resting:
            continue
        speed = row["distance_m"]/row["duration_s"]
        # A role is supported by the measured work/recovery contrast, not
        # an absolute zone label. Recovery HR may remain high after work.
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
        load.update(segment="WU" if i in wu else "CD" if i in cd else "IGNORE" if i in ignored else "CORE",work_rep=False)
        explicit = (proposal.get("explicit_lap_zones") or {}).get(str(i))
        if explicit is not None:
            if str(explicit) not in set("123456"):
                raise ValueError("Invalid explicit lap zone.")
            load["zone"] = str(explicit)
            load["zone_source"] = "user"
    missing_hr = False
    if zone_basis not in {"auto","pace","hr"}:
        raise ValueError("Choose pace, hr or auto as zone basis.")
    if zone_basis != "pace" and athlete is not None:
        from core.garmin_d import hr_zone
        from core.watch_hr import tail_hr
        for block in blocks:
            if any(str(i) in (proposal.get("explicit_lap_zones") or {}) for i in block["ids"]):
                continue
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
    sequence_groups = {}
    sprint_sequences = proposal.get("explicit_sprint_sequences") or []
    if not isinstance(sprint_sequences, list):
        raise ValueError("Invalid explicit sprint sequence.")
    for sequence in sprint_sequences:
        if not isinstance(sequence, dict):
            raise ValueError("Invalid explicit sprint sequence.")
        first_lap = sequence.get("first_lap")
        targets = sequence.get("targets")
        sequence_zone = sequence.get("zone")
        if (type(first_lap) is not int or not isinstance(targets, list) or not targets
                or any(type(target) is not int or not 25 <= target < 100 for target in targets)
                or sequence_zone != "6"):
            raise ValueError("Invalid explicit sprint sequence.")
        start = next((index for index, block in enumerate(blocks) if block["ids"][0] == first_lap), None)
        selected_blocks = blocks[start:start + len(targets)] if start is not None else []
        if len(selected_blocks) != len(targets) or [block["distance"] for block in selected_blocks] != targets:
            raise ValueError("The explicit sprint sequence no longer matches the measured work reps.")
        group_indexes = [
            index for index, (_key, group) in enumerate(groups)
            if any(block is selected for block in group for selected in selected_blocks)
        ]
        if (not group_indexes or group_indexes != list(range(group_indexes[0], group_indexes[-1] + 1))
                or [block for index in group_indexes for block in groups[index][1]] != selected_blocks
                or any(index in sequence_groups for index in group_indexes)):
            raise ValueError("The explicit sprint sequence cannot be shown as one work block.")
        sequence_groups[group_indexes[0]] = {
            "end": group_indexes[-1],
            "text": "1×(" + " // ".join(f"{target} m" for target in targets) + ") Z6",
        }
    manual_zone_labels = {}
    zone_labels = proposal.get("zone_labels", [])
    if not isinstance(zone_labels, list):
        raise ValueError("Explicit zone labels must be a list.")
    for item in zone_labels:
        if not isinstance(item, dict):
            raise ValueError("Explicit zone labels must identify a measured work group.")
        target, count, label = item.get("target_meters"), item.get("count"), item.get("label")
        if (type(target) is not int or type(count) is not int or count < 1
                or not isinstance(label, str) or not re.fullmatch(r"Z[1-6](?:>Z[1-6])?", label)):
            raise ValueError("Explicit zone labels must contain distance, count and a Zx>Zy range.")
        matches = [index for index, ((distance, duration), group) in enumerate(groups)
                   if distance == target and duration is None and len(group) == count]
        if len(matches) != 1 or matches[0] in manual_zone_labels:
            raise ValueError("The explicit zone label does not identify exactly one measured work group.")
        manual_zone_labels[matches[0]] = label
    for group_index, ((distance,duration), group) in enumerate(groups):
        covering_sequence = next((value for start, value in sequence_groups.items()
                                  if start < group_index <= value["end"]), None)
        if covering_sequence:
            continue
        if group_index in sequence_groups:
            texts.append(sequence_groups[group_index]["text"])
            continue
        label = f"{distance} m" if distance is not None else (f"{duration//60}'" if duration%60==0 else f"{duration}s")
        zone_label = " "+manual_zone_labels[group_index] if group_index in manual_zone_labels else zone(
            [i for b in group for i in b["ids"]])
        text = (f"{len(group)}×" if len(group)>1 else "")+label+zone_label
        pauses = [sum(facts[i-1]["duration_s"] for i in recovery if left["ids"][-1] < i < right["ids"][0])
                  for left,right in zip(group,group[1:])]
        if pauses and all(pauses):
            text += f" p{round(median(pauses))}"
        starts = proposal.get("set_start_laps") or []
        if starts and len(groups) == 1:
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
    starts = proposal.get("set_start_laps") or []
    if starts and len(groups) > 1:
        first_laps = [block["ids"][0] for block in blocks]
        if (not isinstance(starts, list) or len(starts) < 2
                or any(type(i) is not int or i not in first_laps for i in starts)
                or starts != sorted(set(starts))):
            raise ValueError("Set starts must identify chronological measured work laps.")
        positions = [first_laps.index(i) for i in starts] + [len(blocks)]
        sets = [blocks[left:right] for left, right in zip(positions, positions[1:])]
        patterns = [[(b["distance"], b["duration"]) for b in group] for group in sets]
        if len(patterns[0]) < 2 or any(pattern != patterns[0] for pattern in patterns[1:]):
            raise ValueError("Sets must contain the same chronological measured pattern.")
        prefix = blocks[:positions[0]]
        prefix_text = texts[:len({b["distance"] for b in prefix})] if prefix else []
        pattern_text = " - ".join(
            (f"{distance} m" if distance is not None else f"{duration}s")
            for distance, duration in patterns[0])
        main = " // ".join(prefix_text + [f"{len(sets)}×({pattern_text})" + zone(
            [i for group in sets for block in group for i in block["ids"]])])
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
        else:
            # A repeated mixed prefix followed by a homogeneous tail should
            # retain the mixed pairs. Example:
            # 1750,850,1750,850,850,850,850 -> 2×(1750-850) // 3×850.
            for width in range(2, len(distances) // 2 + 1):
                pattern = distances[:width]
                if len(set(pattern)) < 2:
                    continue
                repeats = 1
                while distances[repeats * width:(repeats + 1) * width] == pattern:
                    repeats += 1
                prefix_count = repeats * width
                tail = distances[prefix_count:]
                if repeats < 2 or len(tail) < 2 or len(set(tail)) != 1:
                    continue
                pattern_parts = []
                for position, target in enumerate(pattern):
                    position_blocks = [blocks[repeat * width + position] for repeat in range(repeats)]
                    pattern_parts.append(
                        f"{target} m" + zone([lap_id for block in position_blocks for lap_id in block["ids"]])
                    )
                tail_blocks = blocks[prefix_count:]
                tail_text = f"{len(tail_blocks)}×{tail[0]} m" + zone(
                    [lap_id for block in tail_blocks for lap_id in block["ids"]]
                )
                tail_pauses = [
                    sum(facts[lap_id - 1]["duration_s"] for lap_id in recovery
                        if left["ids"][-1] < lap_id < right["ids"][0])
                    for left, right in zip(tail_blocks, tail_blocks[1:])
                ]
                if tail_pauses and all(tail_pauses):
                    tail_text += f" p{round(median(tail_pauses))}"
                main = f"{repeats}×(" + " - ".join(pattern_parts) + f") // {tail_text}"
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
    if manual_zone_labels:
        result["e_zone_note"] += " Explicit zone ranges stated by the user are shown as presentation labels; measured lap zones remain preserved."
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
    explicit_duration_zones = proposal.get("explicit_duration_zones") or {}
    if (not isinstance(explicit_duration_zones, dict)
            or any(not str(key).isdigit() or str(value) not in set("123456")
                   for key, value in explicit_duration_zones.items())):
        raise ValueError("Invalid explicit Alternative duration zone.")
    from core.garmin_d import hr_zone
    texts, entries, missing = [],[],False
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
        explicit = (proposal.get("explicit_role_zones") or {}).get(role)
        if explicit is not None:
            if role not in {"Warmup", "Cooldown"} or str(explicit) not in set("123456"):
                raise ValueError("Invalid explicit Alternative boundary zone.")
            label = str(explicit)
        duration_explicit = explicit_duration_zones.get(str(round(seconds)))
        if duration_explicit is not None and role in {"Work", "Recovery"}:
            label = str(duration_explicit)
            explicit = duration_explicit
        texts.append(f"{part.get('alternative_label','Alternative')} {role} {duration}"+(f" Z{label}" if label else ""))
        entries.append(dict(ids=indices,seconds=seconds,zone=label,role=role,
                            explicit_zone=bool(explicit),
                            target=next((target for block,target in blocks if block==indices),seconds)))
        i = indices[-1]+1
    result = deepcopy(part)
    text = " // ".join(texts)
    result.update(training_fields={"alt":text},description=text,watch_loads=[],
                  e_usable=True,e_zone_basis="hr",ai_structure_status="e_validated")
    result["e_zone_note"] = f"Alternative zones use measured end HR (average HR when unavailable) +{correction} bpm."
    if missing:
        result["e_zone_note"] += " Some blocks have no usable HR/limits; their zone is left empty."
    result.pop("training_alternatives",None)
    if proposal.get("format") == "compact":
        result = compact_alternative(part,result,entries,proposal.get("presentation") or {})
    return result


def compact_alternative(part, result, entries, presentation):
    """Compile compact, bounded notation without losing measured per-lap facts."""
    if not isinstance(presentation,dict):
        raise ValueError("Compact Alternative presentation must be an object.")
    if len(entries) == 1 and not entries[0]["zone"]:
        raise ValueError("Deze activiteit heeft geen bruikbare HR-zone; de gemeten tijd blijft behouden.")
    from core.alternative import expand_time_notation
    selected_zones = {}
    summary_zone_labels = {}
    for role,key in (("Work","work_zone"),("Recovery","recovery_zone")):
        if key not in presentation:
            continue
        selected = str(presentation[key]).upper().removeprefix("Z")
        observed = [e["zone"] for e in entries if e["role"]==role]
        zone_range = re.fullmatch(r"([1-6])\s*>\s*Z?([1-6])", selected)
        if zone_range:
            start, end = map(int, zone_range.groups())
            step = 1 if end >= start else -1
            supported = {str(zone) for zone in range(start, end + step, step)}
            if (not observed or any(zone not in supported for zone in observed)
                    or str(start) not in observed or str(end) not in observed):
                raise ValueError(f"The {role} summary zone is not supported by the measured blocks.")
            summary_zone_labels[role] = f"{start}>{end}"
            continue
        if selected not in set("123456") or not observed or observed.count(selected)*2<len(observed):
            raise ValueError(f"The {role} summary zone is not supported by the measured blocks.")
        selected_zones[role] = selected
        summary_zone_labels[role] = selected
    display = []
    for entry in entries:
        role,seconds = entry["role"],entry["seconds"]
        key = {"Warmup":"warmup_seconds","Cooldown":"cooldown_seconds","Recovery":"recovery_seconds"}.get(role)
        target = presentation.get(key,seconds) if key else entry["target"]
        if not isinstance(target,(int,float)) or isinstance(target,bool) or not math.isfinite(target) or target<=0:
            raise ValueError("Compact Alternative durations must be positive measured targets.")
        tolerance = max(15,target*.06) if role=="Work" else max(30,target*.06)
        if abs(target-seconds)>tolerance:
            raise ValueError(f"{role}: nominal {target:g}s does not fit measured {seconds:g}s.")
        # A literal duration-zone correction is more specific than the
        # repeated-role summary (e.g. a differently zoned trailing work atom).
        zone = entry["zone"] if entry.get("explicit_zone") else selected_zones.get(role,entry["zone"])
        display.append((target,zone,role))
    def atom(item):
        seconds,zone,_ = item
        seconds = round(seconds,3)
        if seconds%60==0:
            label = f"{int(seconds)//60}'"
        elif seconds>=60 and seconds==int(seconds):
            label = f"{int(seconds)//60}'{int(seconds)%60:02d}"
        else:
            label = f"{seconds:g}s"
        return label+(" Z"+zone if zone else "")
    def measured_load(start, end, text):
        measured = []
        for entry in entries[start:end]:
            for lap_id in entry["ids"]:
                raw = part["alternative_laps"][lap_id-1]
                measured.append(dict(lap=lap_id,seconds=raw["seconds"],zone=entry["zone"],
                    zone_source="user" if entry.get("explicit_zone") else "hr",
                    average_hr=raw.get("average_hr"),end_hr=raw.get("end_hr")))
        return dict(segment="ALT",meters=0,seconds=sum(lap["seconds"] for lap in measured),
                    alt_text=text,alt_laps=measured)

    # A monotone or otherwise varying Work sequence with equal recoveries is
    # one compact Main block, not a repetition of "Work" and "Recovery".
    first_main = next((index for index, entry in enumerate(entries)
                       if entry["role"] in {"Work", "Recovery"}), None)
    last_main = next((index for index in range(len(entries)-1, -1, -1)
                      if entries[index]["role"] in {"Work", "Recovery"}), None)
    if first_main is not None and last_main is not None:
        main_entries = entries[first_main:last_main+1]
        expected_roles = ["Work" if index % 2 == 0 else "Recovery"
                          for index in range(len(main_entries))]
        recovery_targets = [display[first_main+index][0] for index in range(1, len(main_entries), 2)]
        work_targets = [display[first_main+index][0] for index in range(0, len(main_entries), 2)]
        work_is_directional = (
            all(left > right for left, right in zip(work_targets, work_targets[1:]))
            or all(left < right for left, right in zip(work_targets, work_targets[1:]))
        )
        if (len(main_entries) >= 3 and len(main_entries) % 2 == 1
                and [entry["role"] for entry in main_entries] == expected_roles
                and work_is_directional
                and recovery_targets
                and max(recovery_targets) - min(recovery_targets) <= 1):
            work_atoms = [atom(display[first_main+index]).split(" Z", 1)[0]
                          for index in range(0, len(main_entries), 2)]
            work_zone = summary_zone_labels.get("Work")
            pause = atom((recovery_targets[0], None, "Recovery"))
            main_body = "1×(" + " - ".join(work_atoms) + ")"
            if work_zone:
                main_body += " Z" + work_zone.replace(">", ">Z")
            main_body += " p" + pause.rstrip("'")
            compact_entries = []
            for index in range(first_main):
                compact_entries.append((index, index+1, atom(display[index])))
            compact_entries.append((first_main, last_main+1, main_body))
            for index in range(last_main+1, len(entries)):
                compact_entries.append((index, index+1, atom(display[index])))
            texts, loads = [], []
            for start, end, body in compact_entries:
                text = part.get("alternative_label", "Alternative") + " " + body
                texts.append(text)
                loads.append(measured_load(start, end, text))
            text = " // ".join(texts)
            result.update(training_fields={"alt":text},description=text,watch_loads=loads)
            result["e_zone_note"] += " Compact notation uses nominal targets; totals retain measured time and HR zones."
            return result

    texts,loads = [],[]
    position = 0
    while position<len(display):
        count,width = 1,1
        best = 1
        for candidate_width in range(2,min(6,(len(display)-position)//2)+1):
            pattern = display[position:position+candidate_width]
            if any(item[2] not in {"Work","Recovery"} for item in pattern):
                continue
            repeats = 1
            while display[position+repeats*candidate_width:position+(repeats+1)*candidate_width]==pattern:
                repeats += 1
            if repeats>=2 and repeats*candidate_width>best:
                count,width,best = repeats,candidate_width,repeats*candidate_width
        end = position+count*width
        body = atom(display[position]) if count==1 else f"{count}×("+" - ".join(
            atom(item) for item in display[position:position+width])+")"
        text = part.get("alternative_label","Alternative")+" "+body
        expanded = expand_time_notation(text)
        if all(item[1] for item in display[position:end]) and (not expanded or len(expanded)!=end-position):
            raise ValueError("Compact Alternative notation could not be checked.")
        texts.append(text)
        loads.append(measured_load(position, end, text))
        position = end
    text = " // ".join(texts)
    result.update(training_fields={"alt":text},description=text,watch_loads=loads)
    result["e_zone_note"] += " Compact notation uses nominal targets; totals retain measured time and HR zones."
    return result
