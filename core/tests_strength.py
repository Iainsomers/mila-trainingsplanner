from datetime import timedelta
from django.test import TestCase
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.template.loader import render_to_string
from core.models import Athlete, TrainingPlan, TrainingSlot, TrainingSegment, PlanMembership
from core.views.calendar import _virtual_slot_from_base_training, _ayc_slot_loads_for_totals
from core.stats import base_week_stats


class StrengthTrainingTests(TestCase):
    def setUp(self):
        self.coach=get_user_model().objects.create_user(username='strength-coach',is_staff=True)
        self.athlete=Athlete.objects.create(owner=self.coach,name='Strength Athlete',birth_year=2000,gender='X')
        self.plan=TrainingPlan.objects.create(owner=self.coach,name='Strength trainer plan',plan_kind=TrainingPlan.PLAN_KIND_TRAINER)
        PlanMembership.objects.create(plan=self.plan,athlete=self.athlete)
        self.day=timezone.localdate()
        self.client.force_login(self.coach)

    def url(self,index=1):
        return f'/slot-modal/{self.day.year}/{self.day.month}/{self.day.day}/{index}/'

    def assert_free_text(self,segment,text):
        self.assertEqual(segment.text,text)
        self.assertEqual(segment.zone,'')
        self.assertIsNone(segment.distance_m)
        self.assertIsNone(segment.duration_s)
        self.assertIsNone(segment.norm_distance_m)

    def test_strength_only_saves_in_trainer_ayc_and_flex_forms_for_am_and_pm(self):
        text='Base strength: 3 sets of 10 squats\nCore stability + bands'
        for source in ['', 'athlete_year','flex']:
            for index in (1,2):
                with self.subTest(source=source,index=index):
                    data={'plan':self.plan.id,'core2_text':text}
                    if source:
                        data.update(source=source,athlete=self.athlete.id)
                    response=self.client.post(self.url(index),data)
                    self.assertEqual(response.status_code,200)
                    self.assertTrue(TrainingSegment.objects.filter(type='CORE2',text=text,slot__date=self.day,slot__slot_index=index).exists())
                    segment=TrainingSegment.objects.filter(type='CORE2',text=text,slot__date=self.day,slot__slot_index=index).order_by('-id').first()
                    self.assert_free_text(segment,text)
                    self.assertEqual(_ayc_slot_loads_for_totals(segment.slot),[])

    def test_existing_numeric_strength_is_cleared_when_saved(self):
        slot=TrainingSlot.objects.create(plan=self.plan,date=self.day,slot_index=1)
        segment=slot.segments.create(type='CORE2',text='1000m z2',zone='2',distance_m=1000,duration_s=300,norm_distance_m=1000)
        response=self.client.post(self.url(),{'plan':self.plan.id,'core2_text':'Gym: squats and lunges'})
        self.assertEqual(response.status_code,200)
        segment.refresh_from_db()
        self.assert_free_text(segment,'Gym: squats and lunges')

    def test_ayc_direct_edit_preserves_free_text_and_escapes_display(self):
        text='Strength <bands> 3x10\nNo zone needed'
        response=self.client.post('/athlete/year/',{'plan':self.plan.id,'athlete':self.athlete.id,'date':self.day.isoformat(),'slot_index':2,
                                                   'slot_text':'','core2_text':text})
        self.assertIn(response.status_code,[200,204,302])
        segment=TrainingSegment.objects.get(slot__athlete=self.athlete,type='CORE2')
        self.assert_free_text(segment,text)
        html=render_to_string('core/partials/segment_display.html',{'seg':segment})
        self.assertNotIn('Strength:',html)
        self.assertIn('&lt;bands&gt;',html)
        self.assertNotIn('pill-z',html)

    def test_order_and_labels_in_all_shared_training_display_templates(self):
        slot=TrainingSlot.objects.create(plan=self.plan,date=self.day,slot_index=1)
        # Legacy Strength was stored after CD; display must move it after all Main parts.
        for order,kind,text in [(1,'WU','WU text'),(2,'CORE','Main one'),(3,'CORE','Main two'),(4,'CD','CD text'),(9,'CORE2','Gym text')]:
            slot.segments.create(order=order,type=kind,text=text)
        self.assertEqual([s.type for s in slot.display_segments],['WU','CORE2','CORE','CORE','CD'])
        for template,context in [
                ('core/partials/trainer_planning_cell.html',{'slot':slot,'day':self.day,'slot_index':1,'selected_plan':self.plan}),
                ('core/partials/calendar_cell.html',{'slot':slot,'day':self.day,'slot_index':1,'selected_plan':self.plan}),
                ('core/partials/ayc_slot_segments.html',{'cell':{'slot':slot,'day':self.day,'slot_index':1}})]:
            html=render_to_string(template,context)
            self.assertLess(html.index('Gym text'),html.index('Main one'))
            self.assertLess(html.index('Gym text'),html.index('CD text'))
            self.assertNotIn('Main 2',html)

    def test_base_and_legacy_strength_do_not_add_running_loads(self):
        slot=_virtual_slot_from_base_training('CORE=1000m z2\nCORE2=30\' squats z3\nCD=500m z1')
        strength=next(s for s in slot.segments.all() if s.type=='CORE2')
        self.assert_free_text(strength,"30' squats z3")
        self.assertEqual(sum(l.get('meters',0) for l in _ayc_slot_loads_for_totals(slot)),1500)
        stored=TrainingSlot.objects.create(plan=self.plan,date=self.day,slot_index=1)
        stored.segments.create(type='CORE2',text="30' z2",zone='2',duration_s=1800,distance_m=1000,norm_distance_m=1000)
        self.assertEqual(_ayc_slot_loads_for_totals(stored),[])
        stats=base_week_stats(self.plan,self.day-timedelta(days=self.day.weekday()))
        self.assertTrue(all(z['distance_m']==0 for z in stats['zones'].values()))

    def test_all_modal_sources_label_strength_after_main(self):
        for source in ['', 'athlete_year','flex']:
            params={'plan':self.plan.id}
            if source: params.update(source=source,athlete=self.athlete.id)
            response=self.client.get(self.url(),params)
            self.assertEqual(response.status_code,200)
            html=response.content.decode()
            self.assertIn('<b>Strength</b>',html)
            self.assertNotIn('Main 2',html)
            self.assertLess(html.index('name="core2_text"'),html.index('name="core_text"'))

    def test_saved_standard_preserves_multiline_strength(self):
        from core.views.slots import _serialize_slot_template_text, _deserialize_slot_template_text
        text='Squats 3x10\nBands + mobility\nLoad = light'
        saved=_serialize_slot_template_text('', '', '', '1000m z2', text, '', '')
        self.assertEqual(_deserialize_slot_template_text(saved)['CORE2'],text)

    def test_modal_prefill_virtual_training_keeps_strength_visible_after_main(self):
        from core.views.slots import _virtual_slot_from_base_training_for_slot_reset
        slot=_virtual_slot_from_base_training_for_slot_reset('CORE=1000m z2\nCORE2=Gym free text\nCD=500m z1')
        self.assertEqual([s.type for s in slot.display_segments],['CORE2','CORE','CD'])
        html=render_to_string('core/partials/trainer_planning_cell.html',{'slot':slot,'day':self.day,'slot_index':1,'selected_plan':self.plan})
        self.assertIn('Gym free text',html)
        self.assertNotIn('Strength:',html)

    def test_strength_only_is_visible_in_core_only_display_mode(self):
        slot=TrainingSlot.objects.create(plan=self.plan,date=self.day,slot_index=1)
        slot.segments.create(type='CORE2',text='Gym only')
        html=render_to_string('core/partials/calendar_cell.html',{'slot':slot,'day':self.day,'slot_index':1,'selected_plan':self.plan,'display_mode':'core_only'})
        self.assertIn('Gym only',html)
        self.assertNotIn('Strength:',html)
