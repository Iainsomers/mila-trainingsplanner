from datetime import date
import json

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.template.loader import render_to_string

from core.models import Athlete, TrainingPlan, TrainingSlot, CoachAccess, TrainingPhoto, StandardStrengthProgram, AthleteBasePlanningBlock, AthleteBasePlanningSlot
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

    def import_watch(self, index=2, main="10*100m z4 p45", origin="watch_c"):
        return self.client.post(self.url(index), {"core_text": main, "watch_origin": origin,
            "watch_loads": json.dumps([{"segment": "CORE", "meters": 100, "seconds": 20, "zone": "4", "average_hr_last_15": 148}])})

    def add_protected_fields(self,slot):
        program=StandardStrengthProgram.objects.create(owner=self.coach,name=f'Gym {slot.pk}')
        photo=TrainingPhoto.objects.create(owner=self.coach,image=b'private-image',thumbnail=b'thumb')
        slot.segments.create(type='MOB',text='Drills and hurdles',order=1,standard_strength_program=program,photo_ids=[str(photo.pk)])
        slot.segments.create(type='SPR',text='5x60m strides',order=2,zone='6',reps=5,distance_m=60,parse_ok=True)
        slot.segments.create(type='CORE2',text='Three sets of squats',order=4,photo_ids=[str(photo.pk)])
        slot.segments.create(type='ALT',text="30' z1 cross trainer",order=5,zone='1',duration_s=1800)
        slot.segment_order=['CORE2','MOB','WU','CORE','SPR','ALT','CD']
        slot.save(update_fields=['segment_order'])
        return photo

    def test_all_watch_models_change_only_running_and_alternative_fields_in_both_dayparts(self):
        for index in (1,2):
            slot=self.original(index)
            photo=self.add_protected_fields(slot)
            protected=list(slot.segments.exclude(type__in=['WU','CORE','ALT','CD']).values())
            for origin in ('watch_a','watch_b','watch_c','watch_d'):
                response=self.client.post(self.url(index),dict(wu_text='900m z1',core_text='4*400m z3',
                    alt_text="20' z2 cycling",cd_text='600m z1',watch_origin=origin,
                    mob_text='discarded browser value',sprint_text='invalid running syntax',core2_text='',
                    remove_mob_photo=[str(photo.pk)],remove_strength_photo=[str(photo.pk)],
                    watch_loads=json.dumps([dict(segment='CORE',meters=400,seconds=80,zone='3')])) )
                self.assertEqual(response.status_code,200)
                slot.refresh_from_db()
                current=list(slot.segments.exclude(type__in=['WU','CORE','ALT','CD']).values())
                for rows in (protected,current):
                    for row in rows:row.pop('order',None)
                self.assertEqual(sorted(current,key=lambda row:row["id"]),sorted(protected,key=lambda row:row["id"]))
                self.assertEqual(slot.segment_order,['CORE2','MOB','WU','CORE','SPR','ALT','CD'])
                self.assertEqual(slot.segments.get(type='WU').text,'900m z1')
                self.assertEqual(slot.segments.get(type='CD').text,'600m z1')
                self.assertEqual(slot.segments.get(type='ALT').duration_s,1200)
                self.assertIn('4',slot.segments.get(type='CORE').text)
                for snapshot in (slot.watch_plan_snapshot,slot.watch_training_snapshot):
                    self.assertEqual({s['type'] for s in snapshot['segments']} & {'MOB','SPR','CORE2'},{'MOB','SPR','CORE2'})
            self.assertEqual(self.client.post(self.url(index),{'action':'select_watch_version','version':'plan'}).status_code,204)
            self.assertEqual(self.client.post(self.url(index),{'action':'select_watch_version','version':'watch'}).status_code,204)
            slot.refresh_from_db()
            self.assertEqual(slot.segments.get(type='CORE2').photo_ids,[str(photo.pk)])

    def test_watch_import_inherits_protected_fields_without_modifying_shared_plan(self):
        shared=TrainingSlot.objects.create(plan=self.plan,date=self.day,slot_index=2)
        shared.segments.create(type='CORE',text='6*200m z4',order=3)
        self.add_protected_fields(shared)
        before=list(shared.segments.values())
        response=self.import_watch(origin='watch_d')
        self.assertEqual(response.status_code,200)
        own=TrainingSlot.objects.get(plan=self.plan,date=self.day,slot_index=2,athlete=self.athlete)
        self.assertEqual(own.segments.get(type='MOB').text,'Drills and hurdles')
        self.assertEqual(own.segments.get(type='MOB').photo_ids,shared.segments.get(type='MOB').photo_ids)
        self.assertEqual(own.segments.get(type='SPR').reps,5)
        self.assertEqual(own.segments.get(type='CORE2').text,'Three sets of squats')
        self.assertEqual(own.segment_order,shared.segment_order)
        self.assertEqual(list(shared.segments.values()),before)

    def test_watch_import_keeps_protected_base_planning_trainer_fields(self):
        trainer=TrainingPlan.objects.create(owner=self.coach,name='Base trainer',plan_kind=TrainingPlan.PLAN_KIND_TRAINER)
        shared=TrainingSlot.objects.create(plan=trainer,date=self.day,slot_index=2)
        shared.segments.create(type='CORE',text='6*200m z4',order=3)
        self.add_protected_fields(shared)
        block=AthleteBasePlanningBlock.objects.create(athlete=self.athlete,start_month=1,start_day=1,end_month=12,end_day=31)
        AthleteBasePlanningSlot.objects.create(block=block,weekday=self.day.weekday(),slot_index=2,
            mode=AthleteBasePlanningSlot.MODE_TRAINER,trainer_plan=trainer)
        self.assertEqual(self.import_watch(origin='watch_c').status_code,200)
        own=TrainingSlot.objects.get(plan=self.plan,date=self.day,slot_index=2,athlete=self.athlete)
        self.assertEqual(own.segments.get(type='MOB').text,'Drills and hurdles')
        self.assertEqual(own.segments.get(type='CORE2').photo_ids,shared.segments.get(type='CORE2').photo_ids)
        self.assertEqual(own.segment_order,shared.segment_order)

    def test_empty_watch_boundaries_and_alternative_clear_only_the_allowed_fields(self):
        slot=self.original()
        self.add_protected_fields(slot)
        self.athlete.auto_wucd_enabled=True
        self.athlete.auto_wu_m=1500
        self.athlete.auto_cd_m=1000
        self.athlete.save()
        self.assertEqual(self.import_watch(origin='watch_d').status_code,200)
        slot.refresh_from_db()
        self.assertFalse(slot.segments.filter(type__in=['WU','CD','ALT']).exists())
        self.assertEqual(set(slot.segments.values_list('type',flat=True)),{'MOB','SPR','CORE2','CORE'})

    def test_strides_and_nested_sets_save_as_separate_main_segments(self):
        first = "3×50 m Z1>Z2 p142"
        second = "3×(200 m - 180 m - 140 m) Z3>Z5 p122 sp252"
        expected = f"{first} // {second}"
        for index, origin in ((1, "watch_c"), (2, "watch_d")):
            slot = self.original(index)
            slot.source = origin
            slot.save(update_fields=["source"])
            slot.segments.filter(type="CORE").delete()
            slot.segments.create(type="CORE", text=f"{first} - {second}", order=3)
            self.assertEqual(self.client.get(self.url(index)).context["core_text"], expected)
            clone = _clone_slot_for_display(slot)
            self.assertEqual([seg.text for seg in clone.segments.all() if seg.type == "CORE"], [first,second])
            response = self.client.post(self.url(index),{
                "core_text":f"{first} + {second}","watch_origin":origin,
            })
            self.assertEqual(response.status_code,200)
            segments = list(slot.segments.filter(type="CORE").order_by("order","id"))
            self.assertEqual([seg.text for seg in segments],[first,second])
            self.assertEqual([seg.norm_distance_m for seg in segments],[150,1560])
            self.assertNotEqual(segments[0].zone,segments[1].zone)
            self.assertEqual(self.client.get(self.url(index)).context["core_text"],expected)

    def test_running_add_preserves_alternative_and_imports_measured_reps(self):
        for index, origin in ((1, "watch_c"), (2, "watch_d")):
            if index == 1:
                original = self.original(index)
            else:
                original = TrainingSlot.objects.create(plan=self.plan,date=self.day,slot_index=index)
            self.add_protected_fields(original)
            alt = original.segments.get(type="ALT")
            before = list(original.segments.values())
            self.assertEqual(self.client.post(self.url(index),{
                "watch_fields":"running_add","watch_origin":origin,
            }).status_code,400)
            loads = [{"segment":"CORE","meters":400,"seconds":80,"zone":"3"}]
            response = self.client.post(self.url(index),{
                "watch_fields":"running_add","watch_origin":origin,
                "wu_text":"900m Z1","core_text":"1×400m Z3","cd_text":"600m Z1",
                "alt_text":"20' Z2 cycling","watch_loads":json.dumps(loads),
            })
            self.assertEqual(response.status_code,200)
            slot = TrainingSlot.objects.get(plan=self.plan,date=self.day,slot_index=index,athlete=self.athlete)
            saved_alt = slot.segments.get(type="ALT")
            self.assertEqual((saved_alt.text,saved_alt.duration_s,saved_alt.zone),(alt.text,1800,"1"))
            if index == 1:
                self.assertEqual(saved_alt.pk,alt.pk)
            else:
                self.assertEqual(list(original.segments.values()),before)
            self.assertEqual(slot.source,origin)
            self.assertEqual(slot.watch_loads,loads)
            self.assertEqual(slot.watch_main_reps[0]["measured_seconds"],80)
            self.assertEqual(slot.segments.get(type="WU").text,"900m Z1")
            self.assertEqual(slot.segments.get(type="CD").text,"600m Z1")
            self.assertIn(alt.text,[item["text"] for item in slot.watch_training_snapshot["segments"]])

    def test_alternative_use_replaces_running_fields_but_preserves_other_blocks(self):
        for index in (1,2):
            slot=self.original(index)
            self.add_protected_fields(slot)
            self.import_watch(index=index)
            slot.refresh_from_db()
            protected=list(slot.segments.filter(type__in=['MOB','SPR','CORE2']).values('type','text','photo_ids'))
            response=self.client.post(self.url(index),{'watch_fields':'alternative_replace',
                'alt_text':"Strength training 46' Z1",'watch_origin':'watch_d',
                'wu_text':'1000m Z1','core_text':'4x400m Z3','cd_text':'1000m Z1','watch_loads':'[]'})
            self.assertEqual(response.status_code,200)
            slot.refresh_from_db()
            self.assertFalse(slot.segments.filter(type__in=['WU','CORE','CD']).exists())
            self.assertEqual(list(slot.segments.filter(type__in=['MOB','SPR','CORE2']).values('type','text','photo_ids')),protected)
            alt=slot.segments.get(type='ALT')
            self.assertEqual(alt.text,"Strength training 46' Z1")
            self.assertEqual(alt.duration_s,2760)
            self.assertEqual(slot.watch_loads,[])

    def test_alternative_add_import_preserves_everything_and_appends_segments(self):
        for index in (1,2):
            slot=self.original(index)
            self.add_protected_fields(slot)
            self.import_watch(index=index,origin='watch_d')
            slot.refresh_from_db()
            before=list(slot.segments.exclude(type='ALT').values())
            metadata=(slot.source,slot.watch_loads,slot.watch_main_reps,slot.watch_plan_snapshot,slot.segment_order)
            expected_alt_texts = list(slot.segments.filter(type='ALT').order_by('order','id').values_list('text',flat=True))
            for origin,text in [('watch_c',"Elliptical 90' Z2"),('watch_d',"Strength training 46' Z1")]:
                response=self.client.post(self.url(index),{'watch_fields':'alternative','alt_text':text,
                    'watch_origin':origin,'core_text':'invalid ignored running value','wu_text':'invalid',
                    'cd_text':'invalid','watch_loads':'[]','core2_text':'malicious replacement'})
                self.assertEqual(response.status_code,200)
                slot.refresh_from_db()
                after=list(slot.segments.exclude(type='ALT').values())
                for rows in (before,after):
                    for row in rows: row.pop('order',None)
                self.assertEqual(after,before)
                self.assertEqual((slot.source,slot.watch_loads,slot.watch_main_reps,slot.watch_plan_snapshot,slot.segment_order),metadata)
                expected_alt_texts.append(text)
                alternatives=list(slot.segments.filter(type='ALT').order_by('order','id'))
                self.assertEqual([alt.text for alt in alternatives],expected_alt_texts)
                alt=alternatives[-1]
                self.assertEqual(alt.text,text)
                self.assertEqual(alt.duration_s,5400 if origin=='watch_c' else 2760)
                self.assertEqual(alt.zone,'2' if origin=='watch_c' else '1')
                self.assertIsNone(alt.distance_m)
                self.assertIsNone(alt.norm_distance_m)
                snapshot_alt_texts=[item['text'] for item in slot.watch_training_snapshot['segments'] if item['type']=='ALT']
                self.assertEqual(snapshot_alt_texts,expected_alt_texts)

    def test_alternative_minutes_are_added_without_changing_measured_running_totals(self):
        from core.stats import athlete_week_stats
        from core.views.calendar import _ayc_slot_loads_for_totals
        from django.core.cache import cache
        self.original()
        self.import_watch(origin='watch_d')
        week=self.day.fromordinal(self.day.toordinal()-self.day.weekday())
        cache.clear()
        before=athlete_week_stats(self.plan,self.athlete,week)
        self.client.post(self.url(),{'watch_fields':'alternative','alt_text':"Elliptical 90' Z2",'watch_origin':'watch_c'})
        cache.clear()
        after=athlete_week_stats(self.plan,self.athlete,week)
        self.assertEqual(after['zones'],before['zones'])
        self.assertEqual(after['alt_zones']['2']['duration_s'],5400)
        own=TrainingSlot.objects.get(plan=self.plan,date=self.day,slot_index=2,athlete=self.athlete)
        loads=_ayc_slot_loads_for_totals(own,self.athlete)
        self.assertEqual([load for load in loads if load.get('kind')=='alt'],
                         [{'kind':'alt','zone':'2','seconds':5400}])

    def test_alternative_only_inherits_entire_shared_training_and_keeps_planned_source(self):
        shared=TrainingSlot.objects.create(plan=self.plan,date=self.day,slot_index=2)
        shared.segments.create(type='WU',text='1500m z1',order=0)
        shared.segments.create(type='CORE',text='4*400m z3',order=3)
        shared.segments.create(type='CD',text='800m z1',order=6)
        self.add_protected_fields(shared)
        before=list(shared.segments.values())
        response=self.client.post(self.url(),{'watch_fields':'alternative','alt_text':"Pilates 46' Z1",'watch_origin':'watch_d'})
        self.assertEqual(response.status_code,200)
        own=TrainingSlot.objects.get(plan=self.plan,date=self.day,slot_index=2,athlete=self.athlete)
        self.assertEqual(own.source,'planned')
        self.assertIsNone(own.watch_plan_snapshot)
        self.assertEqual(own.segment_order,shared.segment_order)
        self.assertEqual(list(own.segments.exclude(type='ALT').order_by('type').values_list('type','text','photo_ids')),
                         list(shared.segments.exclude(type='ALT').order_by('type').values_list('type','text','photo_ids')))
        self.assertEqual(list(shared.segments.values()),before)
        self.assertEqual(list(own.segments.filter(type='ALT').order_by('order','id').values_list('text',flat=True)),
                         ["30' z1 cross trainer","Pilates 46' Z1"])

    def test_two_alternative_activities_combine_in_one_daypart(self):
        for text, origin in [("Strength Training 61' Z1", 'watch_c'), ("Elliptical 30' Z1", 'watch_c')]:
            response=self.client.post(self.url(),{
                'watch_fields':'alternative','alt_text':text,'watch_origin':origin,
            })
            self.assertEqual(response.status_code,200)
        own=TrainingSlot.objects.get(plan=self.plan,date=self.day,slot_index=2,athlete=self.athlete)
        alternatives=list(own.segments.filter(type='ALT').order_by('order','id'))
        self.assertEqual([alt.text for alt in alternatives],["Strength Training 61' Z1","Elliptical 30' Z1"])
        self.assertEqual([alt.duration_s for alt in alternatives],[3660,1800])
        self.assertEqual([alt.zone for alt in alternatives],['1','1'])

    def test_alternative_only_import_into_empty_daypart(self):
        response=self.client.post(self.url(),{'watch_fields':'alternative','alt_text':"Elliptical 99' Z1",'watch_origin':'watch_c'})
        self.assertEqual(response.status_code,200)
        own=TrainingSlot.objects.get(plan=self.plan,date=self.day,slot_index=2,athlete=self.athlete)
        self.assertEqual(list(own.segments.values_list('type',flat=True)),['ALT'])
        self.assertEqual(own.segments.get().duration_s,5940)
        self.assertEqual(self.client.post(self.url(),{'watch_fields':'alternative','watch_origin':'watch_c'}).status_code,400)

    def test_garmin_d_preserves_plan_and_watch_roundtrip(self):
        slot = self.original()
        self.assertEqual(self.import_watch(origin="watch_d").status_code, 200)
        slot.refresh_from_db()
        self.assertEqual(slot.source, "watch_d")
        self.assertIsNotNone(slot.watch_plan_snapshot)
        loads = slot.watch_loads
        self.assertEqual(self.client.post(self.url(), {"action":"select_watch_version", "version":"plan"}).status_code,204)
        self.assertEqual(self.client.post(self.url(), {"action":"select_watch_version", "version":"watch"}).status_code,204)
        slot.refresh_from_db()
        self.assertEqual(slot.source,"watch_d")
        self.assertEqual(slot.watch_loads,loads)

    def test_mixed_minutes_keep_all_six_clock_reps_after_import(self):
        from core.tests_watch_ai_structure import WatchAIStructureTests
        from core.watch_ai_structure import validate_lap_structure, apply_lap_structure
        from core.watch_processing import processed_main_reps

        fixture = WatchAIStructureTests()
        fixture.setUp()
        part = {}
        apply_lap_structure(part, fixture.loads,
                            validate_lap_structure(fixture.proposal, fixture.facts))
        alternative = part['training_alternatives'][1]
        for index, source in ((1, 'watch_c'), (2, 'watch_d')):
            response = self.client.post(self.url(index), {
                'core_text': alternative['training_fields']['main'],
                'watch_origin': source,
                'watch_loads': json.dumps(alternative['watch_loads']),
            })
            self.assertEqual(response.status_code, 200)
            slot = TrainingSlot.objects.get(plan=self.plan, athlete=self.athlete,
                                            date=self.day, slot_index=index)
            for candidate in (slot, _clone_slot_for_display(slot)):
                self.assertEqual([r['measured_seconds'] for r in processed_main_reps(candidate)],
                                 [482, 481, 253, 240, 241, 242])
            # Existing imports may have retained both blocks in one record.
            slot.segments.all().delete()
            slot.segments.create(type='CORE', text="2×8' Z2 p91 - 4×4' Z2 p61", order=3)
            self.assertEqual([r['measured_seconds'] for r in processed_main_reps(slot)],
                             [482, 481, 253, 240, 241, 242])

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

    def test_watch_import_keeps_existing_segment_order_in_both_versions(self):
        slot=self.original()
        plan_order=['CORE2','WU','MOB','SPR','CORE','ALT','CD']
        watch_order=['CORE','WU','MOB','CORE2','SPR','CD','ALT']
        slot.segment_order=plan_order
        slot.save()
        response=self.client.post(self.url(),{'core_text':'10*100m z4 p45','watch_origin':'watch_c','segment_order':','.join(watch_order),
            'watch_loads':json.dumps([{'segment':'CORE','meters':100,'seconds':20,'zone':'4'}])})
        self.assertEqual(response.status_code,200)
        slot.refresh_from_db()
        self.assertEqual(slot.segment_order,plan_order)
        self.assertEqual(self.client.post(self.url(),{'action':'select_watch_version','version':'plan'}).status_code,204)
        slot.refresh_from_db()
        self.assertEqual(slot.segment_order,plan_order)
        self.assertEqual(self.client.post(self.url(),{'action':'select_watch_version','version':'watch'}).status_code,204)
        slot.refresh_from_db()
        self.assertEqual(slot.segment_order,plan_order)
