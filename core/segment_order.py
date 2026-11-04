"""One segment order for forms, stored sessions and all planner views."""
DEFAULT_SEGMENT_ORDER = ['WU', 'MOB', 'CORE2', 'SPR', 'CORE', 'ALT', 'CD']


def normalize_segment_order(value):
    if not value:
        return list(DEFAULT_SEGMENT_ORDER)
    values = value.split(',') if isinstance(value, str) else value
    if not isinstance(values, (list, tuple)):
        raise ValueError('Invalid training segment order.')
    values = [str(item).strip().upper() for item in values]
    if len(values) != len(DEFAULT_SEGMENT_ORDER) or set(values) != set(DEFAULT_SEGMENT_ORDER):
        raise ValueError('Invalid training segment order.')
    return values


def ordered_training_segments(segments, order=None):
    ranks = {kind: index for index, kind in enumerate(normalize_segment_order(order))}
    return sorted(segments, key=lambda segment: ranks.get(segment.type, len(ranks)))


def apply_segment_order(slot, order):
    slot.segment_order = normalize_segment_order(order)
    slot.save(update_fields=['segment_order'])
    segments = ordered_training_segments(slot.segments.all(), slot.segment_order)
    for index, segment in enumerate(segments):
        segment.order = index
    if segments:
        type(segments[0]).objects.bulk_update(segments, ['order'])
