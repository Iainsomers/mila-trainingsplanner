from django.db import migrations


def backfill_planned_display_distances(apps, schema_editor):
    TrainingSlot = apps.get_model("core", "TrainingSlot")
    for slot in TrainingSlot.objects.filter(source__in=("watch_a", "watch_b", "watch_c")).iterator():
        processed = slot.watch_main_reps if isinstance(slot.watch_main_reps, list) else []
        if not processed:
            continue

        planned_distances = []
        for segment in slot.segments.filter(type="CORE").order_by("order", "id"):
            try:
                reps = max(1, int(segment.reps or 1))
                distance = float(segment.distance_m or 0)
            except (TypeError, ValueError):
                continue
            if distance > 0:
                planned_distances.extend([round(distance)] * reps)

        changed = False
        for index, rep in enumerate(processed):
            if not isinstance(rep, dict) or index >= len(planned_distances):
                continue
            if "measured_distance_m" not in rep and rep.get("distance_m") is not None:
                rep["measured_distance_m"] = rep["distance_m"]
            planned_distance = planned_distances[index]
            if rep.get("distance_m") != planned_distance:
                rep["distance_m"] = planned_distance
                changed = True
            if "measured_distance_m" in rep:
                changed = True
        if changed:
            TrainingSlot.objects.filter(pk=slot.pk).update(watch_main_reps=processed)


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0118_trainingslot_watch_main_reps"),
    ]

    operations = [
        migrations.RunPython(backfill_planned_display_distances, migrations.RunPython.noop),
    ]
