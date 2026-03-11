from django.http import HttpResponse
from django.shortcuts import render, get_object_or_404, redirect
from django.views.decorators.http import require_GET, require_http_methods

from core.models import TrainingPlan, Athlete, Group, PlanMembership
from .common import _plans_targeting_athlete, _ranges_overlap


@require_http_methods(["GET", "POST"])
def plan_targets_view(request, plan_id: int):
    plan = get_object_or_404(TrainingPlan, id=plan_id)

    request.session["selected_plan_id"] = plan.id
    request.session.modified = True

    errors = []

    if request.method == "POST":
        group_ids = request.POST.getlist("group_ids")
        athlete_ids = request.POST.getlist("athlete_ids")

        group_ids_int = [int(x) for x in group_ids if str(x).isdigit()]
        athlete_ids_int = [int(x) for x in athlete_ids if str(x).isdigit()]

        if not plan.start_date or not plan.end_date:
            errors.append("Dit plan heeft nog geen start- en einddatum. Vul eerst start_date en end_date in.")

        selected_group_athlete_ids = set(
            Athlete.objects.filter(groups__id__in=group_ids_int).values_list("id", flat=True)
        )
        desired_athlete_ids = set(athlete_ids_int) | selected_group_athlete_ids

        if plan.start_date and plan.end_date:
            for aid in sorted(desired_athlete_ids):
                other_plans = _plans_targeting_athlete(aid).exclude(id=plan.id)

                for op in other_plans:
                    if not op.start_date or not op.end_date:
                        a = Athlete.objects.filter(id=aid).first()
                        a_name = a.name if a else f"athlete_id={aid}"
                        errors.append(f"Overlap/conflict: {a_name} zit al in plan '{op.name}', maar dat plan heeft geen start/einddatum.")
                        continue

                    if _ranges_overlap(plan.start_date, plan.end_date, op.start_date, op.end_date):
                        a = Athlete.objects.filter(id=aid).first()
                        a_name = a.name if a else f"athlete_id={aid}"
                        errors.append(f"Overlap/conflict: {a_name} zit al in plan '{op.name}' ({op.start_date} t/m {op.end_date}).")

        if errors:
            groups = Group.objects.order_by("name")
            athletes = Athlete.objects.order_by("name")

            return render(
                request,
                "core/plan_targets.html",
                {
                    "plan": plan,
                    "groups": groups,
                    "athletes": athletes,
                    "selected_group_ids": set(group_ids_int),
                    "selected_athlete_ids": set(athlete_ids_int),
                    "errors": errors,
                },
            )

        plan.groups.set(Group.objects.filter(id__in=group_ids_int))

        existing_ids = set(PlanMembership.objects.filter(plan=plan).values_list("athlete_id", flat=True))
        desired_direct_ids = set(athlete_ids_int)

        to_remove = existing_ids - desired_direct_ids
        if to_remove:
            PlanMembership.objects.filter(plan=plan, athlete_id__in=to_remove).delete()

        to_add = desired_direct_ids - existing_ids
        for aid in to_add:
            PlanMembership.objects.create(plan=plan, athlete_id=aid)

        return redirect(f"/calendar/?plan={plan.id}")

    groups = Group.objects.order_by("name")
    athletes = Athlete.objects.order_by("name")

    selected_group_ids = set(plan.groups.values_list("id", flat=True))
    selected_athlete_ids = set(plan.athletes.values_list("id", flat=True))

    return render(
        request,
        "core/plan_targets.html",
        {
            "plan": plan,
            "groups": groups,
            "athletes": athletes,
            "selected_group_ids": selected_group_ids,
            "selected_athlete_ids": selected_athlete_ids,
            "errors": [],
        },
    )


@require_GET
def plan_targets_modal(request, plan_id: int):
    plan = get_object_or_404(TrainingPlan, id=plan_id)

    groups = plan.groups.prefetch_related("athletes").order_by("name")

    group_athlete_ids = set(
        Athlete.objects.filter(groups__plans=plan).values_list("id", flat=True)
    )
    direct_ids = set(plan.athletes.values_list("id", flat=True))

    extra_direct_ids = direct_ids - group_athlete_ids
    all_ids = group_athlete_ids | direct_ids

    athletes_all = Athlete.objects.filter(id__in=all_ids).order_by("name")
    athletes_extra = Athlete.objects.filter(id__in=extra_direct_ids).order_by("name")

    return render(
        request,
        "core/partials/plan_targets_modal.html",
        {
            "plan": plan,
            "groups": groups,
            "count_groups": groups.count(),
            "count_via_groups": len(group_athlete_ids),
            "count_direct": len(direct_ids),
            "count_extra_direct": len(extra_direct_ids),
            "count_total": len(all_ids),
            "athletes_all": athletes_all,
            "athletes_extra": athletes_extra,
        },
    )
