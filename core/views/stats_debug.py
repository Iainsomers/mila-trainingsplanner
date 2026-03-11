from datetime import date as date_cls

from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from core.models import Athlete
from core.stats import athlete_week_stats, group_week_stats
from core.views.common import _get_selected_plan, _week_start


@login_required
def stats_debug_view(request):
    plan = _get_selected_plan(request)

    athlete = None
    athlete_id = (request.GET.get("athlete") or "").strip()
    if athlete_id.isdigit():
        athlete = Athlete.objects.filter(id=int(athlete_id)).first()

    week_start = _week_start(date_cls.today())

    context = {
        "plan": plan,
        "week_start": week_start,
        "athlete": athlete,
        "athlete_stats": None,
        "group_stats": None,
    }

    if not plan:
        return render(request, "core/stats_debug.html", context)

    if athlete:
        context["athlete_stats"] = athlete_week_stats(plan, athlete, week_start)
    else:
        athlete_ids = plan.targeted_athlete_ids()
        athletes = list(Athlete.objects.filter(id__in=athlete_ids))
        context["group_stats"] = group_week_stats(plan, athletes, week_start)

    return render(request, "core/stats_debug.html", context)
