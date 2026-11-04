"""Alternative duration belongs equally to all zones in a progression."""
import re


def zone_durations(text, fallback_zone, stored_seconds, duration_for_text):
    parts = [part.strip() for part in (text or '').split('//') if part.strip()]
    output = []
    for part in parts or ['']:
        match = re.search(r'\bz\s*([1-6])\s*(?:>|-)\s*z?\s*([1-6])\b', part, re.I)
        if match:
            start, end = map(int, match.groups())
            step = 1 if end >= start else -1
            zones = [str(z) for z in range(start, end+step, step)]
        else:
            match = re.search(r'\bz\s*([1-6])\b', part, re.I)
            zones = [match.group(1)] if match else [str(fallback_zone or '')]
        repeated = re.match(r"^\s*(\d+)\s*(?:x|\*|×)\s*(\d+(?:[.,]\d+)?\s*(?:'|min\b|\"|sec\b|s\b))", part, re.I)
        seconds = (int(repeated.group(1))*duration_for_text(repeated.group(2))
                   if repeated else duration_for_text(part))
        seconds = seconds or (stored_seconds if len(parts) <= 1 else 0)
        if seconds > 0 and all(z in {'1','2','3'} for z in zones):
            output.extend((zone, seconds/len(zones)) for zone in zones)
    return output
