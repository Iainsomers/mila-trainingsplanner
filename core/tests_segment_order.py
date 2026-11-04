from datetime import timedelta
from django.test import TestCase
from django.contrib.auth import get_user_model
from django.template.loader import render_to_string
from django.utils import timezone
from core.models import Athlete,TrainingPlan,TrainingSlot,TrainingSegment,PlanMembership,CoachAccess
from core.segment_order import DEFAULT_SEGMENT_ORDER,normalize_segment_order


class SegmentOrderTests(TestCase):
    def setUp(self):
        self.coach=get_user_model().objects.create_user(username='order-coach',is_staff=True)
        self.athlete=Athlete.objects.create(owner=self.coach,name='Order Athlete',birth_year=2000,gender='X')
        self.plan=TrainingPlan.objects.create(owner=self.coach,name='Order trainer',plan_kind=TrainingPlan.PLAN_KIND_TRAINER)
        PlanMembership.objects.create(plan=self.plan,athlete=self.athlete)
        self.day=timezone.localdate()
        self.client.force_login(self.coach)
        self.custom=['CORE2','WU','CORE','MOB','CD','SPR','ALT']
        self.data={'plan':self.plan.id,'wu_text':'1000m z1','mob_text':'Drills','core2_text':'Squats 3x10',
                   'sprint_text':'4x60m z6','core_text':'2*1000m z2 + 3*200m z3','alt_text':"10' z1",'cd_text':'500m z1'}

    def url(self,index=1):
        return f'/slot-modal/{self.day.year}/{self.day.month}/{self.day.day}/{index}/'

    def test_default_order_in_form_and_existing_display_without_metadata(self):
        response=self.client.get(self.url(),{'plan':self.plan.id})
        self.assertEqual(response.context['segment_order_value'],','.join(DEFAULT_SEGMENT_ORDER))
        html=response.content.decode()
        names=['wu_text','mob_text','core2_text','sprint_text','core_text','alt_text','cd_text']
        self.assertEqual([html.index('name="'+n+'"') for n in names],sorted(html.index('name="'+n+'"') for n in names))
        slot=TrainingSlot.objects.create(plan=self.plan,date=self.day,slot_index=1)
        for index,kind in enumerate(reversed(DEFAULT_SEGMENT_ORDER)):
            slot.segments.create(type=kind,text=kind,order=index)
        self.assertEqual([s.type for s in slot.display_segments],DEFAULT_SEGMENT_ORDER)

    def test_custom_order_persists_across_all_form_sources_am_pm_and_keeps_main_parts(self):
        for source in ['', 'athlete_year','flex']:
            for index in (1,2):
                data={**self.data,'segment_order':','.join(self.custom)}
                if source:data.update(source=source,athlete=self.athlete.id)
                result=self.client.post(self.url(index),data)
                self.assertEqual(result.status_code,200)
                slot=TrainingSlot.objects.filter(date=self.day,slot_index=index).order_by('-updated_at','-id').first()
                slot.refresh_from_db()
                self.assertEqual(slot.segment_order,self.custom)
                expected=['CORE2','WU','CORE','CORE','MOB','CD','SPR','ALT']
                self.assertEqual([s.type for s in slot.segments.all()],expected)
                self.assertEqual([s.type for s in slot.display_segments],expected)
                self.assertEqual([s.text for s in slot.segments.filter(type='CORE')],['2*1000m z2','3*200m z3'])
                params={'plan':slot.plan_id}
                if source:params.update(source=source,athlete=self.athlete.id)
                reopened=self.client.get(self.url(index),params)
                self.assertEqual(reopened.context['segment_order_value'],','.join(self.custom))

    def test_ayc_direct_save_and_virtual_clone_keep_custom_order(self):
        from core.views.calendar import _clone_slot_for_display
        data={**self.data,'athlete':self.athlete.id,'date':self.day.isoformat(),'slot_index':2,'slot_text':'','segment_order':','.join(self.custom)}
        response=self.client.post('/athlete/year/',data)
        self.assertIn(response.status_code,[200,204])
        slot=TrainingSlot.objects.get(athlete=self.athlete,date=self.day,slot_index=2)
        self.assertEqual(slot.segment_order,self.custom)
        clone=_clone_slot_for_display(slot)
        self.assertEqual(clone.segment_order,self.custom)
        self.assertEqual([s.type for s in clone.display_segments],[s.type for s in slot.display_segments])
        html=render_to_string('core/partials/ayc_slot_segments.html',{'cell':{'slot':clone,'day':self.day,'slot_index':2}})
        self.assertLess(html.index('Squats 3x10'),html.index('1000m z1'))

    def test_invalid_order_is_rejected_without_removing_existing_training(self):
        self.client.post(self.url(),self.data)
        before=list(TrainingSegment.objects.values_list('id','text','order'))
        response=self.client.post(self.url(),{**self.data,'segment_order':'CORE,CORE'})
        self.assertEqual(response.status_code,400)
        self.assertEqual(list(TrainingSegment.objects.values_list('id','text','order')),before)
        for value in ['unknown', ['CORE']*7, {'CORE':1}]:
            with self.assertRaises(ValueError):normalize_segment_order(value)

    def test_saved_standard_retains_order_in_load_and_serialization(self):
        from core.models import SavedTrainingTemplate
        data={**self.data,'action':'save_template','template_name':'Custom order','segment_order':','.join(self.custom)}
        response=self.client.post(self.url(),data)
        self.assertEqual(response.status_code,200)
        template=SavedTrainingTemplate.objects.get(name='Custom order')
        self.assertIn('ORDER='+','.join(self.custom),template.text)
        loaded=self.client.post(self.url(),{'plan':self.plan.id,'action':'load_template','template_id':template.id})
        self.assertEqual(loaded.context['segment_order_value'],','.join(self.custom))

    def test_day_copy_paste_retains_order(self):
        self.client.post(self.url(),{**self.data,'segment_order':','.join(self.custom)})
        path=f'/slot-copy/{self.day.year}/{self.day.month}/{self.day.day}/1/?plan={self.plan.id}'
        self.assertEqual(self.client.post(path).status_code,200)
        target=self.day+timedelta(days=1)
        pasted=self.client.post(f'/slot-paste/{target.year}/{target.month}/{target.day}/1/?plan={self.plan.id}')
        self.assertEqual(pasted.status_code,200)
        self.assertEqual(TrainingSlot.objects.get(plan=self.plan,date=target,slot_index=1).segment_order,self.custom)

    def test_reordering_watch_training_keeps_main_measurements_and_strength(self):
        slot=TrainingSlot.objects.create(plan=self.plan,athlete=self.athlete,date=self.day,slot_index=1,source='watch_d',
                  watch_loads=[{'segment':'CORE','meters':1000,'seconds':240,'zone':'2'}])
        slot.segments.create(type='CORE',text='1000m z2',order=1)
        slot.segments.create(type='CORE2',text='Squats',order=2)
        result=self.client.post('/athlete/year/',{'athlete':self.athlete.id,'plan':self.plan.id,'date':self.day.isoformat(),
              'slot_index':1,'slot_text':'','core_text':'1000m z2','core2_text':'Squats','segment_order':','.join(self.custom)})
        self.assertIn(result.status_code,[200,204])
        slot.refresh_from_db()
        self.assertEqual(slot.source,'watch_d')
        self.assertEqual(slot.watch_loads,[{'segment':'CORE','meters':1000,'seconds':240,'zone':'2'}])
        self.assertEqual(slot.segment_order,self.custom)

    def test_view_only_coach_cannot_change_order(self):
        slot=TrainingSlot.objects.create(plan=self.plan,date=self.day,slot_index=1)
        slot.segments.create(type='CORE',text='1000m z2')
        viewer=get_user_model().objects.create_user(username='order-viewer',is_staff=True)
        CoachAccess.objects.create(owner=self.coach,grantee=viewer,can_edit=False)
        self.client.force_login(viewer)
        session=self.client.session
        session['active_coach_owner_id']=self.coach.id
        session.save()
        response=self.client.post(self.url(),{**self.data,'segment_order':','.join(self.custom)})
        self.assertEqual(response.status_code,403)
        slot.refresh_from_db()
        self.assertEqual(slot.segment_order,[])

    def test_week_copy_paste_retains_order_in_trainer_planner(self):
        self.client.post(self.url(),{**self.data,'segment_order':','.join(self.custom)})
        source=f'/week-copy/{self.day.year}/{self.day.month}/{self.day.day}/?plan={self.plan.id}'
        self.assertEqual(self.client.post(source).status_code,200)
        target=self.day+timedelta(days=7)
        destination=f'/week-paste/{target.year}/{target.month}/{target.day}/?plan={self.plan.id}'
        self.assertEqual(self.client.post(destination).status_code,200)
        self.assertEqual(TrainingSlot.objects.get(plan=self.plan,date=target,slot_index=1).segment_order,self.custom)

    def test_flex_week_copy_paste_keeps_order_and_rejects_invalid_metadata(self):
        import json
        payload={'days':[{'1':{'segment_order':self.custom,'segments':[{'type':'CORE','text':'1000m z2','zone':'2','distance_m':1000,'order':0}]}}]}
        params=f'?athlete={self.athlete.id}&source=flex'
        copied=self.client.post('/flex-week-copy/'+params,{'payload':json.dumps(payload),'source_week_start':self.day.isoformat()})
        self.assertEqual(copied.status_code,200)
        target=self.day+timedelta(days=7)
        pasted=self.client.post('/flex-week-paste/'+params,{'target_week_start':target.isoformat()})
        self.assertEqual(pasted.status_code,200)
        self.assertEqual(TrainingSlot.objects.get(athlete=self.athlete,date=target,slot_index=1).segment_order,self.custom)
        payload['days'][0]['1']['segment_order']=['CORE']
        self.assertEqual(self.client.post('/flex-week-copy/'+params,{'payload':json.dumps(payload)}).status_code,400)
