from datetime import date
import json

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.template.loader import render_to_string

from core.models import Athlete, TrainingPlan, TrainingSlot, CoachAccess
from core.views.calendar import _clone_slot_for_display


class WatchOriginalPlanTests(TestCase):
    def setUp(self):
        self.coach = get_user_model().objects.create_user(username="original-coach", is_staff=True)
        self.athlete = Athlete.objects.create(owner=self.coach, name="Original Runner", birth_year=2000, gender="X")
        self.plan = TrainingPlan.objects.create(owner=self.coach, name="Flex Planner original")
        self.day = date(2026, 10, 30)
        self.client.force_login(self.coach)

    def url(self, index=2):
        return f"/slot-modal/2026/10/30/{index}/?plan={self.plan.pk}&athlete={self.athlete.pk}&source=athlete_year"

    def import_watch(self, index=2, main="10*100m z4 p45"):
        return self.client.post(self.url(index), {"core_text": main, "watch_origin": "watch_c",
            "watch_loads": json.dumps([{"segment": "CORE", "meters": 100, "seconds": 20, "zone": "4", "average_hr_last_15": 148}])})

    def original(self, index=2):
        slot = TrainingSlot.objects.create(plan=self.plan, athlete=self.athlete, date=self.day, slot_index=index)
        slot.segments.create(type="WU", text="1500m z1", order=0, distance_m=1500)
        slot.segments.create(type="CORE", text="6*200m z4", order=3, distance_m=200, reps=6, zone="4")
        slot.segments.create(type="CORE", text="1000m z2", order=4, distance_m=1000, zone="2")
        slot.segments.create(type="CD", text="800m z1", order=6, distance_m=800)
        return slot

    def test_am_and_pm_preserve_first_plan_across_repeated_imports_and_restore(self):
        for index in (1, 2):
            slot = self.original(index)
            before = list(slot.segments.values("type", "text", "order", "distance_m", "reps", "zone"))
            self.assertEqual(self.import_watch(index).status_code, 200)
            slot.refresh_from_db()
            snapshot = slot.watch_plan_snapshot
            self.assertEqual(slot.source, "watch_c")
            self.assertIsNotNone(snapshot)
            self.assertEqual(self.import_watch(index, "4*300m z3").status_code, 200)
            slot.refresh_from_db()
            self.assertEqual(slot.watch_plan_snapshot, snapshot)
            self.assertEqual(self.client.post(self.url(index), {"action": "restore_watch_plan"}).status_code, 204)
            slot.refresh_from_db()
            self.assertEqual(list(slot.segments.values("type", "text", "order", "distance_m", "reps", "zone")), before)
            self.assertEqual(slot.source, "planned")
            self.assertEqual(slot.watch_loads, [])
            self.assertEqual(slot.watch_plan_snapshot, snapshot)

    def test_empty_original_can_be_restored(self):
        self.assertEqual(self.import_watch().status_code, 200)
        self.assertEqual(self.client.post(self.url(), {"action": "restore_watch_plan"}).status_code, 204)
        self.assertFalse(TrainingSlot.objects.get().segments.exists())

    def test_switch_both_ways_keeps_watch_training_laps_and_clock_results(self):
        for index in (1, 2):
            slot = self.original(index)
            self.import_watch(index)
            slot.refresh_from_db()
            watch = slot.watch_training_snapshot
            self.assertTrue(watch["watch_main_reps"])
            self.assertEqual(watch["watch_main_reps"][0]["average_hr_last_15"], 148)
            for version in ("plan", "watch", "plan", "watch"):
                self.assertEqual(self.client.post(self.url(index), {
                    "action": "select_watch_version", "version": version}).status_code, 204)
                slot.refresh_from_db()
                self.assertEqual(slot.watch_training_snapshot, watch)
                clone = _clone_slot_for_display(slot)
                self.assertEqual(clone.watch_main_reps, watch["watch_main_reps"])
                self.assertEqual(clone.watch_display_source, "watch_c")
                if version == "watch":
                    self.assertEqual(slot.watch_loads, watch["watch_loads"])
                    self.assertEqual(slot.source, "watch_c")
                    self.assertEqual(slot.watch_main_reps, watch["watch_main_reps"])
                    self.assertEqual([seg.text for seg in slot.segments.all()], [seg["text"] for seg in watch["segments"]])
                else:
                    self.assertEqual(slot.source, "planned")
                    self.assertEqual(slot.watch_loads, [])
                    html = render_to_string("core/partials/ayc_slot_segments.html", {
                        "cell": {"slot": clone, "day": self.day, "slot_index": index, "plan_id": self.plan.pk},
                        "selected_athlete_id": self.athlete.pk})
                    self.assertIn("watch-source-indicator", html)
                    self.assertIn('data-current-version="plan"', html)
                    self.assertIn(">p/w</button>", html)

    def test_existing_watch_import_archives_results_on_first_switch(self):
        slot = self.original()
        self.import_watch()
        slot.refresh_from_db()
        results = slot.watch_main_reps
        slot.watch_training_snapshot = None  # Simulate an import before migration 0136.
        slot.save()
        self.assertEqual(self.client.post(self.url(), {"action": "select_watch_version", "version": "plan"}).status_code, 204)
        self.assertEqual(self.client.post(self.url(), {"action": "select_watch_version", "version": "watch"}).status_code, 204)
        slot.refresh_from_db()
        self.assertEqual(slot.watch_main_reps, results)

    def test_restore_requires_snapshot_and_edit_access(self):
        self.original()
        self.assertEqual(self.client.post(self.url(), {"action": "restore_watch_plan"}).status_code, 409)
        self.import_watch()
        other = get_user_model().objects.create_user(username="original-other", is_staff=True)
        self.client.force_login(other)
        self.assertEqual(self.client.post(self.url(), {"action": "restore_watch_plan"}).status_code, 403)
        CoachAccess.objects.create(owner=self.coach, grantee=other, can_edit=False)
        session = self.client.session
        session["active_coach_owner_id"] = self.coach.pk
        session.save()
        self.assertEqual(self.client.post(self.url(), {"action": "restore_watch_plan"}).status_code, 403)
        self.assertEqual(TrainingSlot.objects.get().source, "watch_c")

    def test_athlete_can_restore_own_plan_but_cannot_change_other_athlete(self):
        own_slot = self.original()
        self.import_watch()
        other = Athlete.objects.create(owner=self.coach, name="Other Original Runner", birth_year=2000, gender="X")
        other_slot = TrainingSlot.objects.create(plan=self.plan, athlete=other, date=self.day, slot_index=2,
            source="watch_c", watch_plan_snapshot={"segments": []})
        user = get_user_model().objects.create_user(username="Original_Runner")
        self.client.force_login(user)
        response = self.client.post(self.url().replace(f"athlete={self.athlete.pk}", f"athlete={other.pk}"),
                                    {"action": "restore_watch_plan"})
        self.assertIn(response.status_code, (204, 403, 409))
        other_slot.refresh_from_db()
        self.assertEqual(other_slot.source, "watch_c")
        # If the endpoint resolves the login's own athlete, the own plan has
        # already been restored; otherwise restoring it directly must work.
        own_slot.refresh_from_db()
        if own_slot.source == "watch_c":
            self.assertEqual(self.client.post(self.url(), {"action": "restore_watch_plan"}).status_code, 204)

    def test_snapshot_survives_display_clone_and_restore_link_is_rendered(self):
        slot = self.original()
        self.import_watch()
        slot.refresh_from_db()
        clone = _clone_slot_for_display(slot)
        self.assertEqual(clone.watch_plan_snapshot, slot.watch_plan_snapshot)
        html = render_to_string("core/partials/ayc_slot_segments.html", {
            "cell": {"slot": clone, "day": self.day, "slot_index": 2, "plan_id": self.plan.pk},
            "selected_athlete_id": self.athlete.pk})
        self.assertIn('data-version-url="/slot-modal/2026/10/30/2/', html)
