"""Strength is free text, stored under the existing CORE2 segment type."""


def clear_strength_metrics(segment):
    segment.zone = segment.special = segment.t_type = ''
    segment.reps = 1
    segment.distance_m = segment.duration_s = segment.norm_distance_m = None
    segment.parse_ok = False
    segment.parse_message = ''
    return segment
