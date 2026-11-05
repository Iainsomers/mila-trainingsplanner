from datetime import date
from django.contrib.auth import get_user_model
from django.test import TestCase
from core.models import TrainingPlan, TrainingSlot, RaceEvent, RaceEventDistance, CoachAccess


class TrainerChampionshipTests(TestCase):
    def setUp(self):
        users = get_user_model()
        self.coach = users.objects.create_user(username="champ-coach", is_staff=True)
        self.other = users.objects.create_user(username="champ-other", is_staff=True)
        self.plan = TrainingPlan.objects.create(owner=self.coach, name="Trainer group",
            plan_kind=TrainingPlan.PLAN_KIND_TRAINER,start_date=date(2026,11,2),end_date=date(2026,11,29))
        self.client.force_login(self.coach)

    def event(self,name,day,end=None,kind="championship",owner=None):
        return RaceEvent.objects.create(owner=owner or self.coach,name=name,date=day,end_date=end,race_type=kind)

    def read(self,plan=None,day="2026-11-02",weeks=1):
        return self.client.get(f"/planning/trainer/{(plan or self.plan).pk}/",{"date":day,"weeks":weeks})

    def test_all_championships_show_without_distance_or_athlete_selection_in_every_plan(self):
        event=self.event("National indoor",date(2026,11,4))
        RaceEventDistance.objects.create(race=event,distance="1500")
        self.event("Ordinary race",date(2026,11,4),kind="race_other")
        self.event("Foreign championship",date(2026,11,4),owner=self.other)
        self.event("Outside range",date(2026,12,4))
        second=TrainingPlan.objects.create(owner=self.coach,name="Other group",plan_kind=TrainingPlan.PLAN_KIND_TRAINER)
        for plan in (self.plan,second):
            response=self.read(plan)
            self.assertEqual(response.status_code,200)
            self.assertContains(response,"National indoor")
            self.assertContains(response,f'data-championship-id="{event.pk}"',count=1)
            self.assertNotContains(response,"Foreign championship")
            self.assertNotContains(response,"Ordinary race")
            self.assertNotContains(response,"Outside range")
            headers=response.context["week_rows"][0]["day_headers"]
            self.assertEqual([h['day'] for h in headers if h['championships']],[date(2026,11,4)])
        self.assertEqual(TrainingSlot.objects.count(),0)

    def test_inclusive_multiday_range_clips_visible_weeks_and_multiple_pills(self):
        left=self.event("Started before week",date(2026,10,31),date(2026,11,3))
        right=self.event("Over two weeks",date(2026,11,8),date(2026,11,10))
        extra=self.event("Second championship",date(2026,11,8))
        response=self.read(weeks=2)
        by_day={h['day']:[e.pk for e in h['championships']] for week in response.context['week_rows'] for h in week['day_headers']}
        self.assertEqual(by_day[date(2026,11,2)],[left.pk])
        self.assertEqual(by_day[date(2026,11,3)],[left.pk])
        self.assertEqual(by_day[date(2026,11,4)],[])
        self.assertEqual(set(by_day[date(2026,11,8)]),{right.pk,extra.pk})
        self.assertEqual(by_day[date(2026,11,10)],[right.pk])
        self.assertEqual(by_day[date(2026,11,11)],[])
        self.assertContains(response,f'data-championship-id="{right.pk}"',count=3)

    def test_shared_read_only_coach_uses_calendar_of_plan_owner(self):
        self.event("Owner championship",date(2026,11,4))
        self.event("Viewer championship",date(2026,11,4),owner=self.other)
        self.client.force_login(self.other)
        self.assertEqual(self.read().status_code,404)
        CoachAccess.objects.create(owner=self.coach,grantee=self.other,can_edit=False)
        session=self.client.session;session['active_coach_owner_id']=self.coach.pk;session.save()
        response=self.read()
        self.assertEqual(response.status_code,200)
        self.assertContains(response,"Owner championship")
        self.assertNotContains(response,"Viewer championship")

    def test_names_are_escaped_and_pills_wrap_for_narrow_day_columns(self):
        self.event('<script>alert(1)</script>',date(2026,11,4))
        response=self.read()
        self.assertContains(response,'&lt;script&gt;alert(1)&lt;/script&gt;')
        self.assertNotContains(response,'<script>alert(1)</script>')
        self.assertContains(response,'overflow-wrap: anywhere;')
        self.assertContains(response,'print-color-adjust: exact;')
