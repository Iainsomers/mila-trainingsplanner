from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase

from core.models import Athlete, TrainingPlan, TrainingSegment, TrainingSlot
from core.strength import strength_duration_s


class StrengthZoneSevenTests(TestCase):
    def test_strength_minutes_parser_sums_explicit_values_and_repetitions(self):
        self.assertEqual(
            strength_duration_s("Pilates 40' + circuit 2x15 min; HR<145"),
            70 * 60,
        )
        self.assertEqual(strength_duration_s("Weights without a duration"), 0)
        self.assertEqual(strength_duration_s("Core 12’ + mobility 8′"), 20 * 60)

    def test_strength_is_alt_z7_in_week_stats_and_diary_loads(self):
        from core.stats import athlete_week_stats
        from core.views.calendar import _ayc_slot_loads_for_totals

        trainer = get_user_model().objects.create_user(username="strength-z7", is_staff=True)
        athlete = Athlete.objects.create(
            owner=trainer, name="Strength Athlete", birth_year=2000, gender="X",
        )
        week_start = date.today() - timedelta(days=date.today().weekday())
        plan = TrainingPlan.objects.create(
            owner=trainer,
            name="Strength Z7 plan",
            start_date=week_start,
            end_date=week_start + timedelta(days=6),
        )
        slot = TrainingSlot.objects.create(
            plan=plan, athlete=athlete, date=week_start, slot_index=1,
        )
        TrainingSegment.objects.create(slot=slot, type="CORE2", text="Pilates 40'", order=1)
        TrainingSegment.objects.create(slot=slot, type="ALT", text="Bike 20' Z2", zone="2", order=2)

        loads = _ayc_slot_loads_for_totals(slot, athlete)
        self.assertIn({"kind": "alt", "zone": "7", "seconds": 2400}, loads)

        stats = athlete_week_stats(plan, athlete, week_start)
        self.assertEqual(stats["alt_zones"]["7"]["duration_s"], 2400)
        self.assertEqual(stats["alt_zones"]["2"]["duration_s"], 1200)
        self.assertTrue(all(zone["distance_m"] == 0 for zone in stats["zones"].values()))
