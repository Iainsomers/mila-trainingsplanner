from core.parser import parse_segment_text


def _meters_text(value):
    try:
        meters = int(value or 0)
    except (TypeError, ValueError):
        meters = 0
    if meters <= 0:
        return ""
    return f"{meters}m z1"


def _auto_wucd_texts_from_obj(obj):
    if not obj or not getattr(obj, "auto_wucd_enabled", False):
        return "", ""
    return _meters_text(getattr(obj, "auto_wu_m", 0)), _meters_text(getattr(obj, "auto_cd_m", 0))


def auto_wucd_texts_for_target(athlete=None, plan=None):
    auto_wu_text, auto_cd_text = _auto_wucd_texts_from_obj(athlete)
    if auto_wu_text or auto_cd_text:
        return auto_wu_text, auto_cd_text

    if not plan:
        return "", ""

    groups = plan.groups.all().order_by("name", "id")
    if athlete:
        groups = groups.filter(athletes=athlete)

    for group in groups:
        auto_wu_text, auto_cd_text = _auto_wucd_texts_from_obj(group)
        if auto_wu_text or auto_cd_text:
            return auto_wu_text, auto_cd_text

    return "", ""


def auto_wucd_texts_for_athlete(athlete):
    return auto_wucd_texts_for_target(athlete=athlete)


def core_text_needs_auto_wucd(core_text):
    text = (core_text or "").strip()
    if not text:
        return False

    for part in [p.strip() for p in text.split("//") if p.strip()]:
        parsed = parse_segment_text(part, zone_required=False)
        if parsed and (parsed.t_type or parsed.special):
            return True
        if parsed and parsed.zone:
            try:
                if int(parsed.zone) >= 3:
                    return True
            except (TypeError, ValueError):
                pass

    return False


def apply_auto_wucd_texts(athlete, plan, core_text, wu_text, cd_text):
    if not core_text_needs_auto_wucd(core_text):
        return wu_text, cd_text

    auto_wu_text, auto_cd_text = auto_wucd_texts_for_target(athlete=athlete, plan=plan)
    if auto_wu_text and not (wu_text or "").strip():
        wu_text = auto_wu_text
    if auto_cd_text and not (cd_text or "").strip():
        cd_text = auto_cd_text
    return wu_text, cd_text


def _non_wucd_signature(slot):
    if not slot:
        return []
    return [
        (seg.type, seg.text or "")
        for seg in slot.segments.order_by("order", "id")
        if seg.type not in ("WU", "CD")
    ]


def _copy_segment_to_slot(source_seg, target_slot, order):
    seg = target_slot.segments.create(
        type=source_seg.type,
        text=source_seg.text or "",
        order=order,
    )
    seg.zone = source_seg.zone or ""
    seg.reps = int(source_seg.reps or 1)
    seg.distance_m = source_seg.distance_m if source_seg.distance_m is not None else None
    seg.duration_s = source_seg.duration_s if source_seg.duration_s is not None else None
    seg.norm_distance_m = source_seg.norm_distance_m if source_seg.norm_distance_m is not None else None
    seg.parse_ok = bool(source_seg.parse_ok)
    seg.parse_message = source_seg.parse_message or ""
    seg.special = getattr(source_seg, "special", "") or ""
    if hasattr(seg, "t_type"):
        seg.t_type = getattr(source_seg, "t_type", "") or ""
    if getattr(source_seg, "parsed_at", None):
        seg.parsed_at = source_seg.parsed_at
    seg.save()
    return seg


def sync_athlete_auto_wucd_overrides(base_slot, plan, core_text):
    if not base_slot or not plan or getattr(base_slot, "athlete_id", None):
        return False
    if not core_text_needs_auto_wucd(core_text):
        return False

    from core.models import Athlete, TrainingSlot

    athlete_ids = plan.targeted_athlete_ids()
    if not athlete_ids:
        return False

    base_signature = _non_wucd_signature(base_slot)
    source_segments = [
        seg for seg in base_slot.segments.order_by("order", "id")
        if seg.type not in ("WU", "CD")
    ]

    changed = False
    athletes = Athlete.objects.filter(id__in=athlete_ids, auto_wucd_enabled=True).order_by("name", "id")
    for athlete in athletes:
        auto_wu_text, auto_cd_text = auto_wucd_texts_for_target(athlete=athlete, plan=plan)
        if not (auto_wu_text or auto_cd_text):
            continue

        override_slot = TrainingSlot.objects.filter(
            plan=plan,
            athlete=athlete,
            date=base_slot.date,
            slot_index=base_slot.slot_index,
        ).prefetch_related("segments").first()

        if override_slot and _non_wucd_signature(override_slot) != base_signature:
            continue

        if not override_slot:
            override_slot = TrainingSlot.objects.create(
                plan=plan,
                athlete=athlete,
                date=base_slot.date,
                slot_index=base_slot.slot_index,
            )

        override_slot.segments.all().delete()
        order = 0
        if auto_wu_text:
            create_parsed_wucd_segment(override_slot, "WU", auto_wu_text, order)
            order += 1

        for source_seg in source_segments:
            _copy_segment_to_slot(source_seg, override_slot, order)
            order += 1

        if auto_cd_text:
            create_parsed_wucd_segment(override_slot, "CD", auto_cd_text, order)

        changed = True

    return changed


def create_parsed_wucd_segment(slot, segment_type, text, order):
    clean_text = (text or "").strip()
    if not clean_text:
        return None

    parsed = parse_segment_text(clean_text)
    segment = slot.segments.create(
        order=order,
        type=segment_type,
        text=clean_text,
        zone=str(parsed.zone or "1"),
        reps=int(parsed.reps or 1),
        distance_m=parsed.rep_distance_m or parsed.distance_m,
        duration_s=parsed.duration_s,
        norm_distance_m=parsed.distance_m,
        parse_ok=bool(parsed.ok),
        parse_message=parsed.message or "",
    )
    segment.save()
    return segment
