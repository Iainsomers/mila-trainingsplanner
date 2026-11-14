import json
from datetime import date

from django.contrib.auth import get_user_model
from django.test import TestCase

from core.models import Athlete, AthleteDayCheck, PlanMembership, TrainingPlan, TrainingSlot
from core.views.calendar import _ayc_slot_loads_for_totals


class FlexWeekLoadsTests(TestCase):
    def test_week_uses_diary_loads_once_including_recovery_and_both_dayparts(self):
        coach = get_user_model().objects.create_user(username="weekloads", is_staff=True)
        athlete = Athlete.objects.create(owner=coach, name="Runner", birth_year=2000, gender="X")
        plan = TrainingPlan.objects.create(owner=coach, name="Source")
        PlanMembership.objects.create(plan=plan, athlete=athlete)
        monday = date(2026, 11, 9)
        measured = TrainingSlot.objects.create(
            plan=plan, athlete=athlete, date=monday, slot_index=1, source="watch_d",
            watch_loads=[
                {"segment": "CORE", "zone": "3", "meters": 980, "seconds": 240},
                {"segment": "CORE", "zone": "4", "meters": 1020, "seconds": 230},
                {"segment": "RECOVERY", "zone": "1", "meters": 300, "seconds": 120},
            ],
        )
        measured.segments.create(type="CORE", text="1000m z3", zone="3", distance_m=1000)
        measured.segments.create(type="CORE", text="1000m z4", zone="4", distance_m=1000)
        planned = TrainingSlot.objects.create(plan=plan, athlete=athlete, date=monday, slot_index=2)
        planned.segments.create(type="CORE", text="5000m z1", zone="1", distance_m=5000)
        self.client.force_login(coach)
        url = f"/flex-planner/?start={monday}&weeks=1&athletes={athlete.pk}"
        page = self.client.get(url)
        row = page.context["week_rows"][0]["athlete_rows"][0]
        expected = (_ayc_slot_loads_for_totals(row["am_cells"][0]["slot"], athlete, row["pause_mode"])
                    + _ayc_slot_loads_for_totals(row["pm_cells"][0]["slot"], athlete, row["pause_mode"]))
        self.assertEqual(json.loads(row["week_loads_json"]), expected)
        self.assertEqual(sum(load.get("meters", 0) for load in expected), 7300)
        self.assertContains(page, "data-flex-week-loads=")
        AthleteDayCheck.objects.create(athlete=athlete, date=monday, slot_index=2, updated_by=coach,
                                       status=AthleteDayCheck.STATUS_NOT_DONE)
        page = self.client.get(url)
        loads = json.loads(page.context["week_rows"][0]["athlete_rows"][0]["week_loads_json"])
        self.assertEqual(sum(load.get("meters", 0) for load in loads), 2300)
