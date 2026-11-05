from copy import deepcopy
from types import SimpleNamespace

from django.test import SimpleTestCase

from core.garmin_d import apply_garmin_d, hr_zone, rep_hr_zone
from core.watch_processing import processed_main_reps


class GarminDTests(SimpleTestCase):
    def setUp(self):
        self.athlete = SimpleNamespace(zone_hr_bpm={
            '1': 'max 150', '2': '151-170', '3': '171-188', '4': '189-194', '5': 'max 205'})

    def test_hr_summary_ignores_rare_zone_without_changing_rep_measurements(self):
        from core.watch_ai_structure import validate_lap_structure, apply_lap_structure
        facts = []
        loads = []
        for index in range(24):
            hr = 200 if index == 0 else 180 if index < 15 else 190
            for meters, seconds, zone in ((300,55,'3'), (100,29,'1')):
                facts.append(dict(lap=len(facts)+1,distance_m=meters,duration_s=seconds,zone='Z'+zone))
                loads.append(dict(segment='CORE',meters=meters,seconds=seconds,zone=zone,
                                  hr_samples=[[t,hr] for t in range(seconds)]))
        proposal = dict(confidence=.95,lap_structure=dict(warmup_laps=[],cooldown_laps=[],stop_laps=[],
            recovery_laps=list(range(2,49,2)),groups=[dict(target_meters=300,reps=[[i] for i in range(1,48,2)])]))
        structure = validate_lap_structure(proposal,facts,rep_zone=lambda m,s:'Z3')
        part = {}
        apply_lap_structure(part,loads,structure)
        converted = apply_garmin_d([{'parts':[part]}],self.athlete)[0]['parts'][0]
        self.assertEqual(converted['training_fields']['main'],'24×300 m Z3>Z4 p29')
        self.assertEqual(converted['watch_loads'][0]['zone'],'5')
        self.assertEqual([(l['meters'],l['seconds']) for l in loads],
                         [(l['meters'],l['seconds']) for l in converted['watch_loads']])

    def test_configured_hr_limits_and_exact_rep_thresholds(self):
        for hr, zone in [(150,'1'),(151,'2'),(170,'2'),(171,'3'),(194,'4'),(195,'5'),(205,'5'),(206,None)]:
            self.assertEqual(hr_zone(self.athlete, hr), zone)
        self.assertIsNone(rep_hr_zone(self.athlete, 399.9, 49.999, 168))
        self.assertEqual(rep_hr_zone(self.athlete, 400, 20, 168), '2')
        self.assertEqual(rep_hr_zone(self.athlete, 100, 50, 168), '2')
        for missing in (None, 'NA', 0, float('nan')):
            self.assertIsNone(hr_zone(self.athlete, missing))
        self.assertIsNone(hr_zone(SimpleNamespace(zone_hr_bpm={}), 168))
        invalid = deepcopy(self.athlete)
        invalid.zone_hr_bpm['3'] = '160-188'
        self.assertIsNone(hr_zone(invalid, 168))

    def test_shared_boundary_does_not_disable_unambiguous_hr_zones(self):
        athlete=SimpleNamespace(zone_hr_bpm={'1':'151','2':'152-168','3':'169-178','4':'178-184','5':'188'})
        values=[139,92,100,155,160,166,164,169,177,178,179,184,185,188,189]
        expected=['1','1','1','2','2','2','2','3','3',None,'4','4','5','5',None]
        self.assertEqual([hr_zone(athlete,hr) for hr in values],expected)
        part=apply_garmin_d([{'parts':[{'manual':[{'hr_tail':hr} for hr in values]}]}],athlete)[0]['parts'][0]
        self.assertEqual([r['hr_zone'] for r in part['manual']],['Z'+z if z else None for z in expected])
        athlete.zone_hr_bpm['5']=''
        self.assertEqual(hr_zone(athlete,155),'2')
        self.assertIsNone(hr_zone(athlete,186))
        athlete.zone_hr_bpm['3']='invalid'
        self.assertEqual(hr_zone(athlete,155),'2')
        self.assertEqual(hr_zone(athlete,180),'4')
        athlete.zone_hr_bpm['4']='184'
        self.assertIsNone(hr_zone(athlete,180))  # Unknown preceding limit is never guessed.

    def test_complete_timed_reps_use_final_hr_and_keep_measured_distance(self):
        loads = []
        for block in range(5):
            for meters, seconds, pace_zone, hr in [(1000,200,'2',167),(1000,200,'3',172),(400,80,'3',168)]:
                loads.append({'segment':'CORE','zone':pace_zone,'meters':meters,'seconds':seconds,
                              'average_hr':160,'average_hr_last_15':hr,
                              'hr_samples':[[t, (160 if t < 65 else 180) if seconds == 80 else hr] for t in range(seconds)]})
            if block < 4:
                loads.append({'segment':'CORE','zone':'1','meters':300,'seconds':90,
                              'average_hr':140,'average_hr_last_15':175})
        loads.append({'segment':'CORE','zone':'1','meters':17,'seconds':5,'average_hr_last_15':166})
        results = [{'parts':[{'training_fields':{'wu':'','main':"5×8' Z2>Z3 p90",'cd':''},
                             'watch_loads':loads}]}]
        before = deepcopy(results)
        part = apply_garmin_d(results, self.athlete)[0]['parts'][0]
        self.assertEqual(part['training_fields']['main'], "5×8' Z2 p90")
        self.assertEqual(results, before)  # C and source measurements are untouched.
        for original, updated in zip(loads, part['watch_loads']):
            self.assertEqual((original['meters'],original['seconds']), (updated['meters'],updated['seconds']))
            if original['meters'] >= 400:
                self.assertEqual(updated['zone'], '2')
            elif original['meters'] == 300:
                self.assertEqual(updated['zone'], '1')  # recovery is not a work rep
        from core.views.calendar import _virtual_segment_from_text, _ayc_slot_loads_for_totals
        segment = _virtual_segment_from_text('CORE', part['training_fields']['main'])
        slot = SimpleNamespace(source='watch_d', watch_loads=part['watch_loads'], segments=SimpleNamespace(all=lambda:[segment]))
        reps = processed_main_reps(slot)
        self.assertEqual([rep['seconds'] for rep in reps], [480] * 5)
        self.assertEqual([rep['hr_tail'] for rep in reps], [166] * 5)
        self.assertEqual(sum(load['meters'] for load in _ayc_slot_loads_for_totals(slot)), sum(load['meters'] for load in loads))

    def test_short_reps_and_missing_tail_hr_keep_pace_zone(self):
        results = [{'parts':[{'training_fields':{'wu':'','main':'2×200 m Z4','cd':''},
            'watch_loads':[{'segment':'CORE','zone':'4','meters':200,'seconds':30,'average_hr_last_15':168},
                           {'segment':'CORE','zone':'4','meters':200,'seconds':31,'average_hr_last_15':168}]}]}]
        part = apply_garmin_d(results,self.athlete)[0]['parts'][0]
        self.assertEqual(part['training_fields']['main'],'2×200 m Z4')
        self.assertTrue(all(load['zone']=='4' for load in part['watch_loads']))
        results[0]['parts'][0]['training_fields']['main']='1×800 m Z3'
        results[0]['parts'][0]['watch_loads']=[{'segment':'CORE','zone':'3','meters':800,'seconds':160,'average_hr':168}]
        part = apply_garmin_d(results,self.athlete)[0]['parts'][0]
        self.assertEqual(part['training_fields']['main'],'1×800 m Z3')

    def test_hr_column_uses_each_displayed_lap_end_hr_even_without_matching_reps(self):
        # Screenshot laps 10 and 12 had End HR 178 but retained pace Z1.
        rows=[{'index':i,'z_pace':'Z1','hr_tail':hr} for i,hr in [(1,171),(4,173),(6,174),(8,175),(10,178),(12,178)]]
        source=[{'parts':[{'training_fields':{'wu':'','main':'unrecognized recording','cd':''},
                          'manual':rows,'auto':[dict(index=1,z_pace='Z1',hr_tail=178)],
                          'watch_loads':[dict(segment='CORE',zone='1',meters=1000,seconds=265,average_hr=166) for _ in rows]}]}]
        before=deepcopy(source)
        part=apply_garmin_d(source,self.athlete)[0]['parts'][0]
        self.assertEqual([r['hr_zone'] for r in part['manual']],['Z3']*6)
        self.assertEqual([r['pace_z_pace'] for r in part['manual']],['Z1']*6)
        self.assertEqual(part['auto'][0]['hr_zone'],'Z3')
        self.assertEqual(source,before)
        self.assertEqual([l['zone'] for l in part['watch_loads']],['1']*6)

    def test_hr_column_has_no_pace_fallback_or_minimum_rep_length(self):
        source=[{'parts':[{'manual':[dict(z_pace='Z4',hr_tail=178),dict(z_pace='Z2',hr_tail=None),
                                     dict(z_pace='Z2',hr_tail='NA'),dict(z_pace='Z2',hr_tail=0)]}]}]
        part=apply_garmin_d(source,self.athlete)[0]['parts'][0]
        self.assertEqual([r['hr_zone'] for r in part['manual']],['Z3',None,None,None])
        missing=apply_garmin_d(source,SimpleNamespace(zone_hr_bpm={}))[0]['parts'][0]
        self.assertTrue(all(r['hr_zone'] is None for r in missing['manual']))

    def test_hr_table_renders_hr_zone_instead_of_corrected_pace_zone(self):
        import shutil
        import subprocess
        from django.template.loader import get_template
        node=shutil.which('node')
        if not node:self.skipTest('Node is required to execute the table renderer')
        source=get_template('core/athlete_year_calendar.html').template.source
        start=source.index('  function renderTypeALaps(')
        end=source.index('  {% include "core/partials/garmin_combine.js" %}',start)
        script='''const assert=require('assert');
function element(){return {children:[],appendChild(child){this.children.push(child);}};}
const document={createElement:()=>element()};
'''+source[start:end]+'''
const parent=element();
renderTypeALaps(parent,'Recorded laps',[{z_pace:'Z1',pace_z_pace:'Z1',hr_zone:'Z3',hr_tail:178},{z_pace:'Z1',hr_zone:null}],true,true,true);
const rows=parent.children[1].children[0].children[1].children;
assert.equal(rows[0].children[5].textContent,'Z1');
assert.equal(rows[0].children[6].textContent,'Z3');
assert.equal(rows[1].children[6].textContent,'NA');
'''
        result=subprocess.run([node,'-'],input=script,text=True,capture_output=True,timeout=15)
        self.assertEqual(result.returncode,0,result.stderr)
