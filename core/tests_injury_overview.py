from datetime import timedelta
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from core.models import Athlete, AthleteDayCheck, CoachAccess, CoachSettings, CoachEvaluationSharing


class InjuryIssueOverviewTests(TestCase):
    def setUp(self):
        self.coach = get_user_model().objects.create_user(username='issue-coach', is_staff=True)
        self.athlete = Athlete.objects.create(owner=self.coach, name='Issue Athlete', birth_year=2000, gender='X')
        self.client.force_login(self.coach)
        self.today = timezone.localdate()

    def check(self, days, slot=1, **fields):
        return AthleteDayCheck.objects.create(athlete=self.athlete,date=self.today-timedelta(days=days),
                                               slot_index=slot,updated_by=self.coach,**fields)

    def page(self):
        response = self.client.get('/coach/daily-overview-other/', {'view':'injury_issues'})
        self.assertEqual(response.status_code,200)
        return response

    def test_latest_five_evaluations_in_session_order_not_update_order(self):
        self.check(50,pain='serious_pain')  # sixth: outside latest five
        old = self.check(40,pain='no_pain')
        self.check(3,pain='some_pain')
        self.check(2,pain='serious_pain')
        self.check(1,pain='no_pain')
        self.check(1,slot=2,comment='Evaluation without pain')
        self.check(0)  # blank entry is not an evaluation
        self.check(-1,pain='serious_pain')  # future entry excluded
        old.comment='Edited later'
        old.save()
        response=self.page()
        dots=response.context['injury_rows'][0]['dots']
        self.assertEqual([d['color'] for d in dots],['green','yellow','red','green','unknown'])
        self.assertIn('PM: Not provided',dots[-1]['label'])
        self.assertContains(response,'Injury/Issue Overview')

    def test_missing_entries_are_neutral_and_other_owner_is_excluded(self):
        stranger=get_user_model().objects.create_user(username='other-coach',is_staff=True)
        other=Athlete.objects.create(owner=stranger,name='Private Athlete',birth_year=2000,gender='X')
        AthleteDayCheck.objects.create(athlete=other,date=self.today,pain='serious_pain',updated_by=stranger)
        self.check(0,pain='some_pain')
        response=self.page()
        self.assertEqual([d['color'] for d in response.context['injury_rows'][0]['dots']],['unknown']*4+['yellow'])
        self.assertNotContains(response,'Private Athlete')

    def test_shared_coach_cannot_see_hidden_evaluations(self):
        viewer=get_user_model().objects.create_user(username='issue-viewer',is_staff=True)
        CoachAccess.objects.create(owner=self.coach,grantee=viewer,can_edit=False)
        CoachSettings.objects.create(user=self.coach,evaluation_sharing_enabled=True)
        sharing=CoachEvaluationSharing.objects.create(owner=self.coach,grantee=viewer,training=False)
        self.check(0,pain='serious_pain')
        self.client.force_login(viewer)
        session=self.client.session
        session['active_coach_owner_id']=self.coach.id
        session.save()
        response=self.page()
        self.assertFalse(response.context['injury_rows'][0]['visible'])
        self.assertNotContains(response,'PM: Serious issue')
        self.assertNotContains(response,'AM: Serious issue')
        sharing.training=True
        sharing.save()
        self.assertEqual(self.page().context['injury_rows'][0]['dots'][-1]['color'],'red')

    def test_disabled_reports_hide_indicators(self):
        self.check(0,pain='serious_pain')
        self.athlete.training_reports_enabled=False
        self.athlete.save()
        self.assertFalse(self.page().context['injury_rows'][0]['visible'])

    def test_history_is_limited_to_25_and_defaults_to_latest_five(self):
        for days in range(30):
            self.check(days,pain='no_pain',comment=f'Day {days}')
        response=self.page()
        row=response.context['injury_rows'][0]
        self.assertEqual(len(row['history_dots']),25)
        self.assertEqual([d['comment'] for d in row['dots']], [f'Day {i}' for i in range(4,-1,-1)])
        self.assertEqual(row['history_dots'][0]['comment'],'Day 24')
        self.assertNotContains(response,'data-comment="Day 25"')
        self.assertContains(response,'min="5" max="25" step="1" value="5"')

    def test_popup_has_comment_and_effective_status_with_safe_text(self):
        self.check(0,checked=True,comment='<script>alert("test")</script>\nSecond line',rpe=4)
        self.check(1,status='adjusted_ok',pain='some_pain',comment='Adjusted comment')
        self.check(2,status='not_done',pain='serious_pain',comment='Not done comment')
        response=self.page()
        dots=response.context['injury_rows'][0]['dots'][-3:]
        self.assertEqual([d['status'] for d in dots],['not_done','adjusted_ok','done_as_planned'])
        self.assertEqual(dots[-1]['rpe'],4)
        self.assertContains(response,'data-training-url="',count=3)
        self.assertContains(response,'&lt;script&gt;')
        self.assertNotContains(response,'<script>alert(')

    def test_hidden_reports_do_not_expose_popup_comments_or_status(self):
        self.check(0,status='not_done',pain='serious_pain',comment='Private issue detail')
        self.athlete.training_reports_enabled=False
        self.athlete.save()
        response=self.page()
        self.assertNotContains(response,'Private issue detail')
        self.assertNotContains(response,'data-training-url="')

    def training(self, check):
        return self.client.get('/coach/daily-overview-other/', {'view':'injury_issues','training_evaluation':check.id})

    def test_see_training_uses_correct_daypart_and_flex_override_without_writes(self):
        from core.models import TrainingPlan, TrainingSlot, PlanMembership
        plan=TrainingPlan.objects.create(owner=self.coach,name='Source')
        PlanMembership.objects.create(plan=plan,athlete=self.athlete)
        am=TrainingSlot.objects.create(plan=plan,date=self.today,slot_index=1)
        am.segments.create(type='CORE',text='3*1000m z2')
        pm=TrainingSlot.objects.create(plan=plan,date=self.today,slot_index=2)
        pm.segments.create(type='CORE2',text='5*200m z4')
        a=self.check(0,slot=1,pain='no_pain')
        b=self.check(0,slot=2,pain='no_pain')
        self.assertEqual(self.training(a).json()['segments'],[{'label':'Main','text':'3*1000m z2'}])
        self.assertEqual(self.training(b).json()['segments'],[{'label':'Main 2','text':'5*200m z4'}])
        flex=TrainingPlan.objects.create(owner=self.coach,name='Flex Planner')
        override=TrainingSlot.objects.create(plan=flex,athlete=self.athlete,date=self.today,slot_index=1,source='watch_d')
        override.segments.create(type='CORE',text='4*800m z2')
        counts=(TrainingSlot.objects.count(),TrainingPlan.objects.count())
        self.assertEqual(self.training(a).json()['segments'][0]['text'],'4*800m z2')
        self.assertEqual(counts,(TrainingSlot.objects.count(),TrainingPlan.objects.count()))
        override.segments.all().delete()
        self.assertEqual(self.training(a).json()['segments'],[])

    def test_training_private_and_invalid_ids_do_not_expose_data(self):
        c=self.check(0,pain='no_pain')
        self.athlete.training_reports_enabled=False
        self.athlete.save()
        self.assertEqual(self.training(c).status_code,404)
        self.assertEqual(self.client.get('/coach/daily-overview-other/',{'view':'injury_issues','training_evaluation':'abc'}).status_code,400)

    def test_comments_match_desired_improvements_identity_and_keep_other_authors(self):
        from core.models import InjuryIssueComment
        from core.coach_identity import decorate_coach_comment
        self.coach.first_name='Piet'
        self.coach.last_name='van Driel'
        self.coach.save()
        other=get_user_model().objects.create_user(username='Jan_Jansen',is_staff=True)
        InjuryIssueComment.objects.create(athlete=self.athlete,coach=other,comment='Other author')
        url='/coach/daily-overview-other/?view=injury_issues'
        for text in ['First note','Updated note']:
            result=self.client.post(url,{'athlete_id':self.athlete.id,'comment':text,'coach_id':other.id})
            self.assertEqual(result.status_code,302)
            self.assertEqual(InjuryIssueComment.objects.get(athlete=self.athlete,coach=self.coach).comment,text)
        self.assertEqual(InjuryIssueComment.objects.get(coach=other).comment,'Other author')
        comments=self.page().context['injury_rows'][0]['comments']
        own=next(c for c in comments if c.coach_id==self.coach.id)
        self.assertEqual(own.initials,'PD')
        self.assertEqual(own.coach_color,decorate_coach_comment(own).coach_color)
        self.assertNotEqual(comments[0].coach_color,comments[1].coach_color)
        self.client.post(url,{'athlete_id':self.athlete.id,'comment':''})
        self.assertFalse(InjuryIssueComment.objects.filter(coach=self.coach).exists())
        self.assertTrue(InjuryIssueComment.objects.filter(coach=other).exists())

    def test_view_only_coach_can_read_but_cannot_write_comments(self):
        from core.models import InjuryIssueComment
        viewer=get_user_model().objects.create_user(username='readonly-issues',is_staff=True)
        CoachAccess.objects.create(owner=self.coach,grantee=viewer,can_edit=False)
        InjuryIssueComment.objects.create(athlete=self.athlete,coach=self.coach,comment='Visible note')
        self.client.force_login(viewer)
        session=self.client.session
        session['active_coach_owner_id']=self.coach.id
        session.save()
        response=self.page()
        self.assertContains(response,'Visible note')
        self.assertFalse(response.context['injury_rows'][0]['can_comment'])
        result=self.client.post('/coach/daily-overview-other/?view=injury_issues',{'athlete_id':self.athlete.id,'comment':'Not permitted'})
        self.assertEqual(result.status_code,403)
        self.assertEqual(InjuryIssueComment.objects.count(),1)

    def test_comment_write_is_scoped_and_hidden_comments_are_not_rendered(self):
        from core.models import InjuryIssueComment
        self.athlete.training_reports_enabled=False
        self.athlete.save()
        InjuryIssueComment.objects.create(athlete=self.athlete,coach=self.coach,comment='Secret coach note')
        self.assertNotContains(self.page(),'Secret coach note')
        result=self.client.post('/coach/daily-overview-other/?view=injury_issues',{'athlete_id':self.athlete.id,'comment':'Denied'})
        self.assertEqual(result.status_code,404)

    def test_training_follows_base_text_and_explicit_rest(self):
        from core.models import AthleteBasePlanningBlock, AthleteBasePlanningSlot
        block=AthleteBasePlanningBlock.objects.create(athlete=self.athlete,start_month=1,start_day=1,end_month=12,end_day=31)
        base=AthleteBasePlanningSlot.objects.create(block=block,weekday=self.today.weekday(),slot_index=1,
              mode=AthleteBasePlanningSlot.MODE_TRAINING,training_text='WU=1000m z1\nCORE=4*800m z2\nCD=1000m z1')
        check=self.check(0,pain='no_pain')
        self.assertEqual([s['label'] for s in self.training(check).json()['segments']],['WU','Main','CD'])
        base.mode=AthleteBasePlanningSlot.MODE_REST
        base.save()
        self.assertEqual(self.training(check).json()['segments'],[])

    def test_other_athlete_training_and_comments_are_inaccessible(self):
        from core.models import InjuryIssueComment
        owner=get_user_model().objects.create_user(username='private-issue-owner',is_staff=True)
        other=Athlete.objects.create(owner=owner,name='Private other',birth_year=2000,gender='X')
        check=AthleteDayCheck.objects.create(athlete=other,date=self.today,updated_by=owner,pain='serious_pain')
        self.assertEqual(self.training(check).status_code,404)
        response=self.client.post('/coach/daily-overview-other/?view=injury_issues',{'athlete_id':other.id,'comment':'No access'})
        self.assertEqual(response.status_code,404)
        self.assertFalse(InjuryIssueComment.objects.filter(athlete=other).exists())
