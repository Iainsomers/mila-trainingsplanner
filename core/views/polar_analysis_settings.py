from core.models import PolarAnalysisSettings
from .common import _can_edit_coach_owner
from .polar_analysis import hr_upper, validate_hr


def analysis_configuration(request, target, data, *, submitting=True):
    athlete = target.get("athlete") if target else None
    saved = PolarAnalysisSettings.objects.filter(athlete=athlete).first() if athlete else None
    profile = getattr(athlete, "zone_hr_bpm", {}) if athlete else {}
    profile = profile if isinstance(profile, dict) else {}
    profile_upper = [hr_upper(profile.get(str(index), profile.get(f"Z{index}"))) for index in range(1, 5)]
    if saved:
        values, estimated = saved.hr_upper_bpm, saved.estimated
        source = "Saved analysis limits"
    elif all(profile_upper):
        values, estimated = profile_upper, False
        source = "Athlete HR settings"
    else:
        values = [configured if configured is not None else preset for configured, preset in zip(profile_upper, [145, 160, 175, 185])]
        estimated = True
        source = "Estimated preset — review for this athlete"
    can_save = bool(athlete and ((getattr(request.user, "is_staff", False) or getattr(request.user, "is_superuser", False)) and _can_edit_coach_owner(request, athlete.owner_id) or target.get("user") == request.user))
    if request.method == "POST" and submitting:
        provided = [data.get(f"hr_upper_{index}") for index in range(1, 5)]
        if any(value is not None for value in provided):
            if data.get("hr_target") != (target.get("key") if target else None):
                raise ValueError("Athlete selection changed. Reload Type D to use that athlete's HR limits.")
            values = validate_hr(provided)
            estimated = data.get("hr_estimated") == "on"
            source = "Entered analysis limits"
        else:
            values = validate_hr(values)
        if data.get("save_hr_limits") == "on":
            if not can_save:
                raise ValueError("You do not have permission to save analysis limits for this athlete.")
            PolarAnalysisSettings.objects.update_or_create(athlete=athlete, defaults={"hr_upper_bpm": values, "estimated": estimated})
            source = "Saved analysis limits"
    return {"hr_fields": [{"zone": f"Z{index}", "index": index, "value": value} for index, value in enumerate(values, 1)],
            "hr_bounds": values, "hr_estimated": estimated, "hr_source": source, "can_save_hr": can_save}
