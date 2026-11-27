"""Strength is free text, stored under the existing CORE2 segment type."""

import re


_STRENGTH_MINUTES_RE = re.compile(
    r"(?:(\d+)\s*(?:x|\*|×)\s*)?(\d+(?:[.,]\d+)?)\s*(?:['’′](?:([0-5]?\d)[\"″])?|min(?:ute)?s?)(?![A-Za-z])",
    re.IGNORECASE,
)


def strength_duration_s(text):
    """Sum explicit minute values in Strength text, including repetitions."""
    total_seconds = 0.0
    for match in _STRENGTH_MINUTES_RE.finditer(str(text or "")):
        repetitions = int(match.group(1) or 1)
        minutes = float(match.group(2).replace(",", "."))
        total_seconds += repetitions * (minutes * 60 + int(match.group(3) or 0))
    return int(round(total_seconds))


def clear_strength_metrics(segment):
    segment.zone = segment.special = segment.t_type = ''
    segment.reps = 1
    segment.distance_m = segment.duration_s = segment.norm_distance_m = None
    segment.parse_ok = False
    segment.parse_message = ''
    return segment
