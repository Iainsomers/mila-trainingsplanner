from django.contrib.auth import get_user_model
from django.test import TestCase

from core.models import Athlete, Group, PlanMembership, TrainingPlan, TrainingSlot


class SlotModalSaveTests(TestCase):
    def _user_plan_and_athlete(self):
        user = get_user_model().objects.create_user(
            username="coach",
            password="secret",
            is_staff=True,
        )
        plan = TrainingPlan.objects.create(owner=user, name="Plan")
        athlete = Athlete.objects.create(
            owner=user,
            name="Athlete",
            birth_year=2000,
            gender="X",
            auto_wucd_enabled=True,
            auto_wu_m=1500,
            auto_cd_m=1000,
        )
        PlanMembership.objects.create(plan=plan, athlete=athlete)
        self.client.force_login(user)
        return user, plan, athlete

    def test_cd_is_saved_after_all_split_core_segments(self):
        user = get_user_model().objects.create_user(
            username="coach",
            password="secret",
        )
        plan = TrainingPlan.objects.create(owner=user, name="Plan")
        self.client.force_login(user)

        response = self.client.post(
            f"/slot-modal/2026/01/05/1/?plan={plan.id}",
            {
                "plan": str(plan.id),
                "core_text": "1000m z3 // 1000m z4 // 1000m z5",
                "cd_text": "10min z1",
            },
        )

        self.assertEqual(response.status_code, 200)
        slot = TrainingSlot.objects.get(plan=plan, date="2026-01-05", slot_index=1)
        segments = list(slot.segments.order_by("order", "id"))

        self.assertEqual([seg.type for seg in segments], ["CORE", "CORE", "CORE", "CD"])
        cd_order = next(seg.order for seg in segments if seg.type == "CD")
        core_orders = [seg.order for seg in segments if seg.type == "CORE"]
        self.assertGreater(cd_order, max(core_orders))

    def test_auto_wucd_is_applied_when_core_is_present(self):
        _, plan, athlete = self._user_plan_and_athlete()

        response = self.client.post(
            f"/slot-modal/2026/01/06/1/?plan={plan.id}&athlete={athlete.id}",
            {
                "plan": str(plan.id),
                "athlete": str(athlete.id),
                "core_text": "1000m z3",
            },
        )

        self.assertEqual(response.status_code, 200)
        slot = TrainingSlot.objects.get(plan=plan, athlete=athlete, date="2026-01-06", slot_index=1)
        segments = list(slot.segments.order_by("order", "id"))
        self.assertEqual([seg.type for seg in segments], ["WU", "CORE", "CD"])
        self.assertEqual(segments[0].text, "1500m z1")
        self.assertEqual(segments[-1].text, "1000m z1")

    def test_auto_wucd_is_not_applied_without_core(self):
        _, plan, athlete = self._user_plan_and_athlete()

        response = self.client.post(
            f"/slot-modal/2026/01/07/1/?plan={plan.id}&athlete={athlete.id}",
            {
                "plan": str(plan.id),
                "athlete": str(athlete.id),
                "mob_text": "drills",
            },
        )

        self.assertEqual(response.status_code, 200)
        slot = TrainingSlot.objects.get(plan=plan, athlete=athlete, date="2026-01-07", slot_index=1)
        segments = list(slot.segments.order_by("order", "id"))
        self.assertEqual([seg.type for seg in segments], ["MOB"])

    def test_auto_wucd_is_not_applied_for_z1_z2_only_core(self):
        _, plan, athlete = self._user_plan_and_athlete()

        response = self.client.post(
            f"/slot-modal/2026/01/09/1/?plan={plan.id}&athlete={athlete.id}",
            {
                "plan": str(plan.id),
                "athlete": str(athlete.id),
                "core_text": "1000m z1 // 1000m z2",
            },
        )

        self.assertEqual(response.status_code, 200)
        slot = TrainingSlot.objects.get(plan=plan, athlete=athlete, date="2026-01-09", slot_index=1)
        segments = list(slot.segments.order_by("order", "id"))
        self.assertEqual([seg.type for seg in segments], ["CORE", "CORE"])

    def test_group_auto_wucd_is_applied_for_base_plan_training(self):
        user = get_user_model().objects.create_user(
            username="groupcoach",
            password="secret",
            is_staff=True,
        )
        athlete = Athlete.objects.create(
            owner=user,
            name="Group Athlete",
            birth_year=2000,
            gender="X",
        )
        group = Group.objects.create(
            owner=user,
            name="Group",
            auto_wucd_enabled=True,
            auto_wu_m=1200,
            auto_cd_m=800,
        )
        group.athletes.add(athlete)
        plan = TrainingPlan.objects.create(owner=user, name="Group Plan")
        plan.groups.add(group)
        self.client.force_login(user)

        response = self.client.post(
            f"/slot-modal/2026/01/10/1/?plan={plan.id}",
            {
                "plan": str(plan.id),
                "core_text": "1000m z3",
            },
        )

        self.assertEqual(response.status_code, 200)
        slot = TrainingSlot.objects.get(plan=plan, athlete__isnull=True, date="2026-01-10", slot_index=1)
        segments = list(slot.segments.order_by("order", "id"))
        self.assertEqual([seg.type for seg in segments], ["WU", "CORE", "CD"])
        self.assertEqual(segments[0].text, "1200m z1")
        self.assertEqual(segments[-1].text, "800m z1")

    def test_athlete_auto_wucd_overrides_group_base_training(self):
        user = get_user_model().objects.create_user(
            username="mixedcoach",
            password="secret",
            is_staff=True,
        )
        group = Group.objects.create(
            owner=user,
            name="Mixed Group",
            auto_wucd_enabled=True,
            auto_wu_m=700,
            auto_cd_m=700,
        )
        group_athlete = Athlete.objects.create(
            owner=user,
            name="Group Setting Athlete",
            birth_year=2000,
            gender="X",
        )
        athlete_setting_athlete = Athlete.objects.create(
            owner=user,
            name="Athlete Setting Athlete",
            birth_year=2000,
            gender="X",
            auto_wucd_enabled=True,
            auto_wu_m=1500,
            auto_cd_m=1000,
        )
        group.athletes.add(group_athlete, athlete_setting_athlete)
        plan = TrainingPlan.objects.create(owner=user, name="Mixed Plan")
        plan.groups.add(group)
        self.client.force_login(user)

        response = self.client.post(
            f"/slot-modal/2026/01/11/1/?plan={plan.id}",
            {
                "plan": str(plan.id),
                "core_text": "1000m z3",
            },
        )

        self.assertEqual(response.status_code, 200)
        base_slot = TrainingSlot.objects.get(plan=plan, athlete__isnull=True, date="2026-01-11", slot_index=1)
        base_segments = list(base_slot.segments.order_by("order", "id"))
        self.assertEqual(base_segments[0].text, "700m z1")
        self.assertEqual(base_segments[-1].text, "700m z1")

        athlete_slot = TrainingSlot.objects.get(plan=plan, athlete=athlete_setting_athlete, date="2026-01-11", slot_index=1)
        athlete_segments = list(athlete_slot.segments.order_by("order", "id"))
        self.assertEqual([seg.type for seg in athlete_segments], ["WU", "CORE", "CD"])
        self.assertEqual(athlete_segments[0].text, "1500m z1")
        self.assertEqual(athlete_segments[-1].text, "1000m z1")
        self.assertFalse(TrainingSlot.objects.filter(plan=plan, athlete=group_athlete, date="2026-01-11", slot_index=1).exists())

    def test_athlete_year_can_create_training_without_existing_slot(self):
        _, plan, athlete = self._user_plan_and_athlete()

        response = self.client.post(
            f"/athlete/year/?year=2026&athlete={athlete.id}",
            {
                "date": "2026-01-08",
                "slot_index": "1",
                "plan": str(plan.id),
                "slot_text": "1000m z3",
                "core_text": "1000m z3",
            },
        )

        self.assertEqual(response.status_code, 200)
        slot = TrainingSlot.objects.get(plan=plan, athlete=athlete, date="2026-01-08", slot_index=1)
        segments = list(slot.segments.order_by("order", "id"))
        self.assertEqual([seg.type for seg in segments], ["WU", "CORE", "CD"])
        self.assertEqual(segments[1].text, "1000m z3")
