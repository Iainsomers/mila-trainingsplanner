from datetime import date
from pathlib import Path
import json
import re
import shutil
import subprocess
from unittest import skipUnless
from django.test import TestCase
from django.contrib.auth import get_user_model
from core.models import Athlete, TrainingPlan, PlanMembership, TrainingSlot, AthleteDayCheck


class EvaluationSessionTests(TestCase):
    def setUp(self):
        self.coach=get_user_model().objects.create_user(username='eval-coach',is_staff=True)
        self.plan=TrainingPlan.objects.create(owner=self.coach,name='Evaluation plan')
        self.athlete=Athlete.objects.create(owner=self.coach,name='Evaluation Runner',birth_year=2000,gender='X')
        PlanMembership.objects.create(plan=self.plan,athlete=self.athlete)
        self.day=date(2026,10,29)
        self.client.force_login(self.coach)
        for index,text in ((1,'AM easy 5000m Z1'),(2,'PM 6*400m Z3')):
            slot=TrainingSlot.objects.create(plan=self.plan,athlete=self.athlete,date=self.day,slot_index=index)
            slot.segments.create(type='CORE',text=text,order=3)
        self.url=f'/athlete/year/?year=2026&athlete={self.athlete.pk}'

    def test_page_contains_current_training_and_daypart_targets_on_desktop_and_mobile(self):
        response=self.client.get(self.url)
        self.assertEqual(response.status_code,200)
        self.assertContains(response,'data-t1-training="AM easy 5000m Z1"')
        texts=re.findall(r'data-t2-training="([^"]+)"',response.content.decode())
        self.assertTrue(any('PM 6' in text and '400m' in text for text in texts),texts)
        self.assertContains(response,'data-evaluation-slot="1" role="button"')
        self.assertContains(response,'data-evaluation-slot="2" role="button"')
        self.assertContains(response,'data-evaluation-slot="1"')
        self.assertContains(response,'class="evaluation-actions"')
        self.assertContains(response,'max-height:92dvh')

    def test_posting_one_daypart_leaves_other_evaluation_unchanged(self):
        other=AthleteDayCheck.objects.create(athlete=self.athlete,date=self.day,slot_index=2,
            updated_by=self.coach,status='done_as_planned',rpe=7,pain='some_pain',comment='PM original comment')
        response=self.client.post(self.url,dict(date=self.day.isoformat(),slot_index='1',report_submit='1',
            check_status='adjusted_ok',rpe='4',pain='no_pain',report_comment='AM evaluation only'))
        self.assertIn(response.status_code,(200,204,302))
        other.refresh_from_db()
        self.assertEqual((other.rpe,other.pain,other.comment),(7,'some_pain','PM original comment'))
        self.assertEqual(AthleteDayCheck.objects.get(athlete=self.athlete,date=self.day,slot_index=1).comment,'AM evaluation only')

    @skipUnless(shutil.which('node'),'Node required for actual browser handler regression')
    def test_actual_js_opens_and_saves_only_clicked_session(self):
        source=Path('core/templates/core/athlete_year_calendar.html').read_text(encoding='utf-8')
        start=source.index('  document.querySelectorAll(".comment-display").forEach(function(el){')
        opening=source[start:source.index('  function showPendingEvaluations()',start)]
        start=source.index('  document.getElementById("commentOkBtn").addEventListener("click", function(){')
        saving=source[start:source.index('})();',start)]
        script=r"""const assert=require('assert');
const els={};
const document={getElementById:(id)=>els[id]||(els[id]={value:'',textContent:'',style:{},addEventListener:function(k,fn){this[k]=fn}}),querySelectorAll:()=>[el]};
let activeDate='',evaluationPainEnabled=true,savedWatch=[],requests=[],visible={};
const values={'data-date':'2026-10-29','data-t1-enabled':'1','data-t2-enabled':'1',
 'data-t1-training':'AM training','data-t2-training':'PM <script>training</script>',
 'data-t1-watch-id':'am-watch','data-t2-watch-id':'pm-watch',
 'data-t1-comment':'AM comment','data-t2-comment':'PM comment'};
const el={getAttribute:(k)=>values[k]||'',addEventListener:(k,fn)=>{el[k]=fn}};
function setSectionVisible(k,v){visible[k]=v;}
function enabled(k){return visible[k];}
function updateReportGrid(){}
function setVal(id,v){document.getElementById(id).value=v||'';}
function val(id){return document.getElementById(id).value;}
function setNotDoneRpe(){}
function setSavedWatchResult(id,summary){savedWatch=[id,summary];}
function validate(){}
function stopVoiceComment(){}
function post(...args){requests.push(args);return Promise.resolve();}
const window={location:{reload:()=>{}}};
"""+opening+saving+r"""
(async()=>{
 for(const slot of ['1','2']){
  requests=[];
  el.click({preventDefault(){},stopImmediatePropagation(){},target:{closest:()=>({getAttribute:()=>slot})}});
  assert.equal(visible.reportT1,slot==='1');assert.equal(visible.reportT2,slot==='2');
  assert.equal(els.reportTraining.textContent,values['data-t'+slot+'-training']);
  assert.equal(savedWatch[0],slot==='1'?'am-watch':'pm-watch');
  els.commentOkBtn.click.call(els.commentOkBtn);
  await new Promise(resolve=>setImmediate(resolve));
  assert.equal(requests.length,1);assert.equal(requests[0][0],Number(slot));
 }
})();
"""
        result=subprocess.run([shutil.which('node'),'-'],input=script,text=True,capture_output=True,timeout=15)
        self.assertEqual(result.returncode,0,result.stderr)
