"""Strength is free text, stored under the existing CORE2 segment type."""


def clear_strength_metrics(segment):
    segment.zone = segment.special = segment.t_type = ''
    segment.reps = 1
    segment.distance_m = segment.duration_s = segment.norm_distance_m = None
    segment.parse_ok = False
    segment.parse_message = ''
    return segment


def ordered_training_segments(segments):
    items = list(segments)
    strength = [s for s in items if s.type == 'CORE2']
    if not strength:
        return items
    items = [s for s in items if s.type != 'CORE2']
    main = [i for i, s in enumerate(items) if s.type == 'CORE']
    position = main[-1]+1 if main else next((i for i,s in enumerate(items) if s.type in {'ALT','CD'}),len(items))
    return items[:position] + strength + items[position:]
