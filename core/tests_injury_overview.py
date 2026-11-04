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
