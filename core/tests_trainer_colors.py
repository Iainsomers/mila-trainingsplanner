from datetime import date
import shutil
import subprocess
from unittest import skipUnless
from django.contrib.auth import get_user_model
from django.test import TestCase
from core.models import TrainingPlan,TrainingSlot


class TrainerProgressiveColorTests(TestCase):
    @skipUnless(shutil.which('node'),'Node is required to execute rendered planner JavaScript')
    def test_rendered_trainer_planner_colors_every_zone_like_flex(self):
        coach=get_user_model().objects.create_user(username='trainer-colors',is_staff=True)
        plan=TrainingPlan.objects.create(owner=coach,name='Colors',plan_kind=TrainingPlan.PLAN_KIND_TRAINER,
                                        start_date=date(2026,12,7),end_date=date(2026,12,13))
        slot=TrainingSlot.objects.create(plan=plan,date=date(2026,12,10),slot_index=1)
        slot.segments.create(type='CORE',text='12*400m z2>z4',zone='2')
        self.client.force_login(coach)
        response=self.client.get(f'/planning/trainer/{plan.id}/?date=2026-12-07&weeks=1')
        self.assertEqual(response.status_code,200)
        html=response.content.decode()
        self.assertIn('12*400m z2&gt;z4',html)
        start=html.index('function flexNormalizeTKey(')
        end=html.index('function cleanupTrainerModalBackdrop(',start)
        functions=html[start:end]
        script='''const assert=require('assert');
let elements=[];
const document={querySelectorAll:()=>elements};
'''+functions+'''
for(const [text,colors] of [
 ['12*400m z2>z4',['#f7c6d0','#f06f5f','#bfe7bf']],
 ['12*400m z4>z2',['#bfe7bf','#f06f5f','#f7c6d0']],
 ['12*400m z2>z3',['#f7c6d0','#f06f5f']],
 ['2*(400m z2-200m z3-100m z4)',['#f7c6d0','#f06f5f','#bfe7bf']],
 ['4*400m z2',[]]]) {
 elements=[{textContent:text,style:{}}];
 applyFlexProgressivePillColors();
 const background=elements[0].style.background||'';
 assert.equal((background.match(/#[0-9a-f]{6}/g)||[]).length,colors.length*2,text);
 colors.forEach((color,i)=>assert.equal((background.match(/#[0-9a-f]{6}/g)||[])[i*2],color,text));
 if(colors.length===3){assert(background.includes('33.333%'));assert(background.includes('66.667%'));}
}
assert.deepEqual(flexProgressiveTKeys('TM>T5'),['TM','THM','10000','5000']);
console.log('Trainer colors match all intermediate zones and T ranges.');
'''
        result=subprocess.run([shutil.which('node'),'-'],input=script,text=True,capture_output=True,timeout=15)
        self.assertEqual(result.returncode,0,result.stderr)
