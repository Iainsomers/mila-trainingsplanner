from copy import deepcopy
import json
from types import SimpleNamespace
from unittest.mock import patch, MagicMock

from django.test import SimpleTestCase

from core.watch_ai_structure import validate_lap_structure, apply_lap_structure
from core.watch_processing import processed_main_reps
from core.garmin_d import apply_garmin_d
from core.views.calendar import _virtual_segment_from_text, _ayc_slot_loads_for_totals


class WatchAIStructureTests(SimpleTestCase):
    def setUp(self):
        values = [(1005.4,301),(1001.21,286),(946.95,13681),(1008.92,215),
                  (996.954,211),(272.28,56),(126.39,91),(2347.52,481),
                  (152.97,93),(1192.51,253),(236.771,222),(1175.82,240),
                  (162.26,61),(1167.32,241),(46.8906,61),(1172.89,242),
                  (432.01,301),(1106.27,437)]
        work = {4,5,6,8,10,12,14,16}
        self.facts = [{'lap':i,'distance_m':m,'duration_s':s,'zone':'Z2' if i in work else 'Z1'}
                      for i,(m,s) in enumerate(values,1)]
        self.proposal = {'confidence':.95,'lap_structure':{
            'warmup_laps':[1,2], 'stop_laps':[3], 'cooldown_laps':[18],
            'recovery_laps':[7,9,11,13,15,17],
            'groups':[{'target_seconds':480,'reps':[[4,5,6],[8]]},
                      {'target_seconds':240,'reps':[[10],[12],[14],[16]]}]}}
        self.loads = [{'segment':'CORE','meters':f['distance_m'],'seconds':f['duration_s'],
                       'zone':f['zone'][1:], 'average_hr':160,
                       'hr_samples':[[t,160] for t in range(int(f['duration_s']))] if f['lap'] in work else []}
                      for f in self.facts]

    def test_ai_lap_plan_builds_two_options_and_six_clock_reps_for_both_models(self):
        structure = validate_lap_structure(self.proposal,self.facts)
        self.assertIsNotNone(structure)
        self.assertEqual(structure['time_fields']['main'], "2×8' Z2 p91 + 4×4' Z2 p61")
        self.assertEqual(structure['training_fields']['wu'],'2000 m Z1')
        self.assertEqual(structure['training_fields']['cd'],'1100 m Z1')
        part = {}
        before = deepcopy(self.loads)
        self.assertTrue(apply_lap_structure(part,deepcopy(self.loads),structure))
        athlete = SimpleNamespace(zone_hr_bpm={'1':'max 140','2':'141-170','3':'171-180','4':'181-190','5':'max 205'})
        d = apply_garmin_d([{'parts':[part]}],athlete)[0]['parts'][0]
        for source, candidate in [('watch_c',part),('watch_d',d)]:
            self.assertEqual([a['label'] for a in candidate['training_alternatives']],['Distance','Time'])
            for alternative in candidate['training_alternatives']:
                fields = alternative['training_fields']
                segments = [_virtual_segment_from_text('CORE',t) for t in fields['main'].split(' + ')]
                segments += [_virtual_segment_from_text('WU',fields['wu']), _virtual_segment_from_text('CD',fields['cd'])]
                slot = SimpleNamespace(source=source,watch_loads=alternative['watch_loads'],segments=SimpleNamespace(all=lambda:segments))
                reps = processed_main_reps(slot)
                self.assertEqual([r['measured_seconds'] for r in reps],[482,481,253,240,241,242])
                self.assertEqual([r['hr_tail'] for r in reps],[160]*6)
                if alternative['label']=='Time':
                    self.assertEqual([r['seconds'] for r in reps],[482,481,253,240,241,242])
                self.assertAlmostEqual(sum(l['meters'] for l in _ayc_slot_loads_for_totals(slot)),
                    sum(l['meters'] for l in before if l['seconds'] <= l['meters']*.6))
        self.assertEqual([(l['meters'],l['seconds']) for l in part['watch_loads']],[(l['meters'],l['seconds']) for l in before])

    def test_local_inference_recognizes_actual_mixed_recording_without_ai(self):
        from core.watch_ai_structure import infer_lap_structure
        with patch('core.views.polar_raw.urlopen',side_effect=AssertionError('No AI request')):
            result = infer_lap_structure(self.facts)
        expected = validate_lap_structure(self.proposal,self.facts)
        self.assertEqual(result,expected)
        self.assertEqual(result['time_fields']['main'],"2×8' Z2 p91 + 4×4' Z2 p61")
        no_zones = [dict(row, zone='Z1') for row in self.facts]
        self.assertIsNone(infer_lap_structure(no_zones))

    def test_rejects_missing_duplicate_invented_and_noncontiguous_laps(self):
        mutations = [lambda p:p['lap_structure']['stop_laps'].clear(),
                     lambda p:p['lap_structure']['groups'][0]['reps'][0].append(5),
                     lambda p:p['lap_structure']['groups'][0]['reps'][0].append(99),
                     lambda p:p['lap_structure']['groups'][0]['reps'].__setitem__(0,[4,6]),
                     lambda p:p['lap_structure']['groups'][1].__setitem__('target_seconds',180),
                     lambda p:p.__setitem__('confidence',.5)]
        for mutate in mutations:
            proposal = deepcopy(self.proposal)
            mutate(proposal)
            self.assertIsNone(validate_lap_structure(proposal,self.facts))

    def test_rejects_running_disguised_as_stop_or_recovery(self):
        facts = deepcopy(self.facts)
        facts[2].update(distance_m=3000,duration_s=600)
        self.assertIsNone(validate_lap_structure(self.proposal,facts))
        facts = deepcopy(self.facts)
        facts[6].update(distance_m=450,duration_s=91)
        self.assertIsNone(validate_lap_structure(self.proposal,facts))

    def test_actual_ai_response_uses_schema_and_attaches_validated_structure(self):
        from core.views.polar_raw import _model_b_ai_description
        laps = [{'distanceMeters':f['distance_m'],'durationMillis':f['duration_s']*1000} for f in self.facts]
        response = MagicMock()
        response.__enter__.return_value.read.return_value = json.dumps({'choices':[{'message':{'content':json.dumps(self.proposal)}}]}).encode()
        with patch.dict('os.environ',{'OPENAI_API_KEY':'test'}), patch('core.views.polar_raw.urlopen',return_value=response) as call, patch('core.views.polar_raw.lap_zone_paces',return_value=('Z2','NA')):
            description = _model_b_ai_description(laps)
        self.assertIsNotNone(description.structure)
        request = call.call_args.args[0]
        self.assertIn('lap_structure',request.data.decode())
        self.assertNotIn('heart_rate',request.data.decode())

    def test_translation_keeps_validated_metadata_and_consent_skips_ai(self):
        from core.views.polar_raw import translate_model_b
        from core.watch_ai_structure import ValidatedDescription
        structure = validate_lap_structure(self.proposal,self.facts)
        laps = [{'distanceMeters':f['distance_m'],'durationMillis':f['duration_s']*1000} for f in self.facts]
        session = {'laps':{'laps':laps}}
        baseline = [{'parts':[{}]}]
        with patch('core.views.polar_raw.translate',return_value=deepcopy(baseline)), patch(
                'core.views.polar_raw._model_b_ai_description',return_value=ValidatedDescription(structure)) as ai:
            result = translate_model_b([session],5,allow_lap_structure=True)
            self.assertEqual(result[0]['parts'][0]['validated_lap_structure'],structure)
            self.assertEqual(ai.call_count,1)
        with patch('core.views.polar_raw.translate',return_value=deepcopy(baseline)), patch(
                'core.views.polar_raw._model_b_ai_description',side_effect=AssertionError('AI consent disabled')):
            result = translate_model_b([session],5,allow_ai=False)
            self.assertNotIn('validated_lap_structure',result[0]['parts'][0])
