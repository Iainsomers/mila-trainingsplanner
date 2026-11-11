"""Validate explicit chat distance blocks against consecutive source laps."""
from copy import deepcopy
import math
import re

from core.training_text import split_main_segments
from core.watch_ai_structure import description, representative_zones


def requested_distance_sequence(text):
    pieces = split_main_segments(text, split_hyphens=False)
    if not 2 <= len(pieces) <= 8:
        return None
    groups = []
    for piece in pieces:
        match = re.fullmatch(r"\s*(?:(\d+)\s*[×x*]\s*)?(\d+)\s*m(?:\s+z[1-5](?:>z[1-5])?)?\s*", piece, re.I)
        if not match:
            return None
        count, target = int(match[1] or 1), int(match[2])
        if not 1 <= count <= 30 or not 50 <= target <= 10000:
            return None
        groups.append((count, target))
    if groups[-1][0] < 2 or groups[-1][1] < 400:
        return None
    return groups if sum(count for count, _ in groups) <= 30 else None


def apply_distance_sequence(part, groups, rep_zone):
    """Only explicit requests can supply repetition context absent from laps."""
    loads = part.get("watch_loads") or []
    core = [(i, load) for i, load in enumerate(loads) if load.get("segment") == "CORE"]
    if not core or len(core) > 200:
        return None
    try:
        values = [(float(load["meters"]), float(load["seconds"])) for _, load in core]
        if any(not math.isfinite(m + s) or m <= 0 or s <= 0 for m, s in values):
            return None
        targets = [(group, target) for group, (count, target) in enumerate(groups) for _ in range(count)]
        solutions = []
        attempts = 0

        def match(position, rep, blocks):
            nonlocal attempts
            attempts += 1
            if len(solutions) > 1 or attempts > 2000:
                return
            # Tiny transitions and measured walking remain separate from work.
            while position < len(values):
                meters, seconds = values[position]
                if not ((meters <= 5 and seconds <= 2) or
                        (meters <= 600 and seconds <= 600 and meters / seconds < 2)):
                    break
                position += 1
            if rep == len(targets):
                if position == len(values):
                    solutions.append(blocks)
                return
            group, target = targets[rep]
            meters = seconds = 0
            for end in range(position, len(values)):
                m, s = values[end]
                if m / s < 2 or (m <= 5 and s <= 2):
                    break
                meters += m
                seconds += s
                if meters > target + max(30, target * .08):
                    break
                if abs(meters - target) <= max(30, target * .08):
                    match(end + 1, rep + 1, blocks + [(group, target, position, end, meters, seconds)])

        match(0, 0, [])
        if len(solutions) != 1 or attempts > 2000:
            return None
        result = deepcopy(part)
        updated = result["watch_loads"]
        for index, _ in core:
            updated[index]["work_rep"] = False
            for key in ("ai_rep", "ai_group", "ai_target_seconds", "ai_nominal_m", "nominal_rep_m"):
                updated[index].pop(key, None)
        texts = []
        for group, (count, target) in enumerate(groups):
            blocks = [block for block in solutions[0] if block[0] == group]
            zones = representative_zones(rep_zone(block[4], block[5]) for block in blocks)
            zone = (" " + (zones[0] if len(zones) == 1 else zones[0] + ">" + zones[-1])) if zones else ""
            texts.append((f"{count}×" if count > 1 else "") + f"{target} m{zone}")
            for _, _, start, end, meters, seconds in blocks:
                first = core[start][0] + 1
                for position in range(start, end + 1):
                    updated[core[position][0]].update(work_rep=True, ai_rep=first, ai_group=group,
                        ai_target_seconds=round(seconds), ai_nominal_m=target)
        result["training_fields"] = dict(result.get("training_fields") or {}, main=" // ".join(texts))
        result["description"] = description(result["training_fields"])
        result["chat_reply"] = ("De afstanden zijn aan de gemeten laps gekoppeld. "
                                "De herhalingsindeling volgt je suggestie. Niet-geregistreerde herstelduur is onbekend.")
        result["ai_structure_status"] = "measured_structure"
        result.pop("training_alternatives", None)
        return result
    except (KeyError, TypeError, ValueError, ZeroDivisionError, OverflowError):
        return None
