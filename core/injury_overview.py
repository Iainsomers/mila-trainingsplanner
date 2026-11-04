"""Read the selected athlete session without creating or editing training slots."""
from datetime import timedelta
from core.models import TrainingPlan, TrainingSlot, AthleteBasePlanningSlot


def training_for_evaluation(check):
    from core.views.calendar import _virtual_slot_from_base_training, _calendar_race_slots, _slot_has_race, _slot_is_visually_empty
    from core.views.slots import _base_planning_slot_for_slot_reset
    athlete, day, index = check.athlete, check.date, check.slot_index
    slot = None
    fixed = blocked = False
    plans = TrainingPlan.objects.filter(owner=athlete.owner).exclude(name__startswith='Flex Planner').order_by('name')
    for plan in plans:
        if ((plan.start_date and plan.start_date > day) or (plan.end_date and plan.end_date < day)
                or athlete.id not in plan.targeted_athlete_ids()):
            continue
        candidates = TrainingSlot.objects.filter(plan=plan, date=day, slot_index=index).prefetch_related('segments')
        slot = candidates.filter(athlete=athlete).first()
        fixed = slot is not None
        if slot is None:
            slot = candidates.filter(athlete__isnull=True).first()
        break
    flex_plan = TrainingPlan.objects.filter(owner=athlete.owner, name__startswith='Flex Planner').order_by('id').first()
    override = (TrainingSlot.objects.filter(plan=flex_plan, athlete=athlete, date=day, slot_index=index)
                .prefetch_related('segments').first()) if flex_plan else None
    if override is not None:
        fixed = True
        if _slot_is_visually_empty(override):
            if not _slot_has_race(slot):
                slot, blocked = None, True
        else:
            slot = override
    if not fixed and not blocked:
        base = _base_planning_slot_for_slot_reset(athlete, day, index)
        if base:
            if base.mode == AthleteBasePlanningSlot.MODE_TRAINING:
                slot = _virtual_slot_from_base_training(base.training_text)
            elif base.mode == AthleteBasePlanningSlot.MODE_TRAINER and base.trainer_plan_id:
                candidates = TrainingSlot.objects.filter(plan_id=base.trainer_plan_id, date=day, slot_index=index)
                slot = candidates.filter(athlete=athlete).first()
                if slot is None:
                    slot = candidates.filter(athlete__isnull=True).first()
            elif base.mode == AthleteBasePlanningSlot.MODE_REST and not _slot_has_race(slot):
                slot = None
    if index == 2:
        race = _calendar_race_slots([athlete.id], day, day+timedelta(days=1)).get((athlete.id, day))
        if race and not _slot_has_race(slot):
            slot = race
    labels = {'WU':'WU', 'MOB':'Mob / Tech', 'SPR':'Sprint Z6', 'CORE':'Main', 'CORE2':'Main 2', 'ALT':'Alternative', 'CD':'CD'}
    output = []
    if slot:
        for segment in slot.segments.all():
            text = segment.text or ''
            program = getattr(segment, 'standard_strength_program', None)
            if program:
                text = '\n'.join(filter(None, [program.name, text]))
            if text:
                output.append({'label':labels.get(segment.type, segment.type), 'text':text})
    return output
