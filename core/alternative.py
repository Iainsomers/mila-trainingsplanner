"""Alternative duration belongs equally to all zones in a progression."""
import re
import math
from core.training_text import split_main_segments


def expand_time_notation(text):
    """Bounded Alternative time/zone grammar, including repeated mixed sets."""
    value = str(text or "").strip()
    start = re.search(r"\d|\(",value)
    if not start:
        return None
    value = value[start.start():]
    position = 0
    def whitespace():
        nonlocal position
        while position<len(value) and value[position].isspace():
            position += 1
    def term(depth):
        nonlocal position
        if depth>4:
            raise ValueError
        whitespace()
        prefix = re.match(r"[A-Za-z][A-Za-z _-]*?(?=\d|\()",value[position:])
        if prefix:
            position += prefix.end()
        repeated = re.match(r"(\d+)\s*[×x*]\s*",value[position:])
        if repeated:
            count = int(repeated[1])
            if not 1<=count<=60:
                raise ValueError
            position += repeated.end()
            result = term(depth+1)*count
        elif position<len(value) and value[position]=="(":
            position += 1
            result = sequence(depth+1)
            whitespace()
            if position>=len(value) or value[position]!=")":
                raise ValueError
            position += 1
        else:
            minutes = re.match(r"(\d+(?:[.,]\d+)?)\s*['′’](?:\s*(\d{1,2})(?:[\"″])?)?",value[position:])
            seconds = re.match(r"(\d+(?:[.,]\d+)?)\s*(?:s\b|sec\b|[\"″])",value[position:],re.I)
            if minutes:
                duration = float(minutes[1].replace(",", "."))*60+int(minutes[2] or 0)
                position += minutes.end()
            elif seconds:
                duration = float(seconds[1].replace(",", "."))
                position += seconds.end()
            else:
                raise ValueError
            whitespace()
            zone = re.match(r"Z([1-6])\b",value[position:],re.I)
            if not zone or not 0<duration<=86400:
                raise ValueError
            position += zone.end()
            result = [(zone[1],duration)]
        if len(result)>200:
            raise ValueError
        return result
    def sequence(depth):
        nonlocal position
        result = term(depth)
        while True:
            whitespace()
            separator = re.match(r"//|[+\-]",value[position:])
            if not separator:
                break
            position += separator.end()
            result += term(depth)
            if len(result)>200:
                raise ValueError
        return result
    try:
        result = sequence(0)
        whitespace()
        return result if position==len(value) else None
    except (ValueError,IndexError,OverflowError):
        return None


def _compact_pause_loads(text):
    compact_sequence = re.search(
        r"\b(\d+)\s*[×x*]\s*(?:\(([^)]+)\)|([^()]+?))\s*Z([1-6])"
        r"(?:\s*>\s*Z?([1-6]))?\s+p\s*(\d+(?:[.,]\d+)?)\s*(?:(['′’])(\d{1,2})?[\"″]?|([\"″]|s|sec))?\s*$",
        text or "", re.IGNORECASE,
    )
    if compact_sequence:
        reps = int(compact_sequence.group(1))
        atoms = re.split(r"\s*(?://+|-)\s*", (compact_sequence[2] or compact_sequence[3]).strip())
        seconds = []
        for atom in atoms:
            minute = re.fullmatch(r"(\d+(?:[.,]\d+)?)\s*['′’]", atom)
            second = re.fullmatch(r"(\d+(?:[.,]\d+)?)\s*(?:s|sec|[\"″])", atom, re.IGNORECASE)
            if minute:
                seconds.append(float(minute.group(1).replace(",", ".")) * 60)
            elif second:
                seconds.append(float(second.group(1).replace(",", ".")))
            else:
                seconds = []
                break
        pause = float(compact_sequence[6].replace(",", "."))
        if compact_sequence[7]:
            pause = pause * 60 + int(compact_sequence[8] or 0)
        elif not compact_sequence[9] and pause <= 10:
            pause *= 60
        if 1 <= reps <= 60 and seconds and all(0 < value <= 86400 for value in seconds) and 0 < pause <= 86400:
            start, end = int(compact_sequence[4]), int(compact_sequence[5] or compact_sequence[4])
            step = 1 if end >= start else -1
            zones = range(start, end + step, step)
            loads = [(str(zone), reps * sum(seconds) / len(zones)) for zone in zones]
            pauses = reps * len(seconds) - 1
            return loads + ([("1", pauses * pause)] if pauses else [])
    return []


def parse_alternative_text(text):
    from core.parser import ParseResult, parse_segment_text
    expanded = expand_time_notation(text) or _compact_pause_loads(text)
    if expanded:
        zones = {zone for zone,_ in expanded}
        return ParseResult(ok=True,duration_s=round(sum(seconds for _,seconds in expanded)),
            zone=int(next(iter(zones))) if len(zones)==1 else None,raw=text)
    return parse_segment_text(text,zone_required=False)


def segment_zone_durations(seg, duration_for_text):
    measured = getattr(seg,"watch_alternative_data",None) or {}
    if isinstance(measured,dict) and measured.get("text")==getattr(seg,"text",""):
        laps = measured.get("laps") or []
        if isinstance(laps,list) and laps:
            try:
                values = [(str(lap["zone"]),float(lap["seconds"])) for lap in laps]
                if all(zone in set("123456") and math.isfinite(seconds) and seconds>0 for zone,seconds in values):
                    return values
            except (TypeError,KeyError,ValueError,OverflowError):
                pass
    return zone_durations(getattr(seg,"text",""),getattr(seg,"zone",""),
                          float(getattr(seg,"duration_s",None) or 0),duration_for_text)


def split_alternative_segments(text):
    """Accept Main's top-level plus notation alongside existing double slashes."""
    return split_main_segments(text, split_hyphens=False)


def zone_durations(text, fallback_zone, stored_seconds, duration_for_text):
    expanded = expand_time_notation(text)
    if expanded:
        output = []
        for part in split_alternative_segments(text):
            grouped = []
            for zone,seconds in expand_time_notation(part) or []:
                if grouped and grouped[-1][0]==zone:
                    grouped[-1] = (zone,grouped[-1][1]+seconds)
                else:
                    grouped.append((zone,seconds))
            output.extend(grouped)
        return output
    parts = split_alternative_segments(text)
    output = []
    for part in parts or ['']:
        if compact := _compact_pause_loads(part):
            output.extend(compact)
            continue
        match = re.search(r'\bz\s*([1-6])\s*(?:>|-)\s*z?\s*([1-6])\b', part, re.I)
        if match:
            start, end = map(int, match.groups())
            step = 1 if end >= start else -1
            zones = [str(z) for z in range(start, end+step, step)]
        else:
            match = re.search(r'\bz\s*([1-6])\b', part, re.I)
            zones = [match.group(1)] if match else [str(fallback_zone or '')]
        repeated = re.search(r"\b(\d+)\s*(?:x|\*|×)\s*(\d+(?:[.,]\d+)?\s*(?:'|min\b|\"|sec\b|s\b))", part, re.I)
        seconds = (int(repeated.group(1))*duration_for_text(repeated.group(2))
                   if repeated else duration_for_text(part))
        seconds = seconds or (stored_seconds if len(parts) <= 1 else 0)
        if seconds > 0 and all(z in {'1','2','3','4','5','6'} for z in zones):
            output.extend((zone, seconds/len(zones)) for zone in zones)
    return output
