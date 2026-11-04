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
    def test_ai_distance_group_keeps_seventeen_measured_reps_and_outlier(self):
        from core.views.polar_raw import _model_b_ai_description
        values = [(1000,324.87),(1000,311.95),(244.87,994.38)]
        work = [(499.74,105.84),(498.86,100.68),(496.63,98.54),(496.73,98.89),
                (531.92,108.72),(497.7,97.42),(499.16,98.29),(495.84,97.71),
                (498.08,98.11),(492.68,97.13),(498.71,97.9),(495.12,97.65),
                (497.26,96.96),(495.6,97.09),(497.05,98.18),(504.67,100.75),(502.39,100.64)]
        for index, rep in enumerate(work):
            values.extend([rep, (80,45) if index < 16 else (9.53,3.27)])
        facts = [dict(lap=i,distance_m=m,duration_s=t,zone='Z2' if i in range(4,37,2) else 'Z1')
                 for i,(m,t) in enumerate(values,1)]
        proposal = {'confidence':.96, 'lap_structure':dict(warmup_laps=[1,2],stop_laps=[3],
            cooldown_laps=[], recovery_laps=list(range(5,38,2)),
            groups=[dict(target_meters=500,target_seconds=None,reps=[[i] for i in range(4,37,2)])])}
        response = MagicMock()
        response.__enter__.return_value.read.return_value = json.dumps(
            {'choices':[{'message':{'content':json.dumps(proposal)}}]}).encode()
        laps = [dict(distanceMeters=m,durationMillis=t*1000) for m,t in values]
        with patch.dict('os.environ',{'OPENAI_API_KEY':'test'}), patch('core.views.polar_raw.lap_zone_paces', side_effect=lambda m,t,a: ('Z2' if m > 400 and t < 150000 else 'Z1', None)), patch('core.views.polar_raw.urlopen',return_value=response) as call:
            result = _model_b_ai_description(laps)
        self.assertEqual(call.call_count,1)
        structure = result.structure
        self.assertEqual(structure['training_fields']['main'],'17×500 m Z2 p45')
        self.assertEqual(structure['training_fields']['wu'],'2000 m Z1')
        self.assertIsNone(structure['time_fields'])
        loads = [dict(segment='CORE',meters=m,seconds=t,zone='2' if i in range(4,37,2) else '1')
                 for i,(m,t) in enumerate(values,1)]
        part = {}
        self.assertTrue(apply_lap_structure(part,loads,structure))
        self.assertEqual([a['label'] for a in part['training_alternatives']],['Distance'])
        segment = _virtual_segment_from_text('CORE',structure['training_fields']['main'])
        slot = SimpleNamespace(source='watch_c',watch_loads=loads,segments=SimpleNamespace(all=lambda:[segment]))
        reps = processed_main_reps(slot)
        self.assertEqual([r['measured_seconds'] for r in reps],[t for m,t in work])
        self.assertEqual([(l['meters'],l['seconds']) for l in loads],values)
        bad = deepcopy(proposal)
        bad['lap_structure']['groups'][0]['target_meters']=400
        self.assertIsNone(validate_lap_structure(bad,facts))

    def test_ai_set_boundaries_build_measured_pause_and_keep_twenty_clock_reps(self):
        from core.views.polar_raw import _model_b_ai_description
        values=[(3812.71,1084.14),(1455.01,3448.11),(665.01,612.07)]
        work=[(414.63,80.21),(408.24,81.38),(413.09,79.76),(412.06,79.98),(412.37,79.16),
              (404.8,77.99),(410.6,77.53),(404.95,77.46),(411.78,76.51),(410.11,74.74),
              (417.21,75.02),(410.97,74.86),(410.51,73.05),(410.67,72.36),(412.57,71.8),
              (410.35,73.04),(413.82,72.18),(413.7,69.05),(410.91,68.56),(406.35,69.6)]
        for i,rep in enumerate(work):
            values.extend([rep,(308.1,317.76) if i==9 else (260.12,375.39) if i==19 else (106,60)])
        values.append((1460.18,434.21))
        facts=[dict(lap=i,distance_m=m,duration_s=t,zone='Z2' if i in range(4,43,2) else 'Z1')
               for i,(m,t) in enumerate(values,1)]
        proposal={'confidence':.98,'lap_structure':dict(warmup_laps=[1],stop_laps=[2],
            recovery_laps=[3]+list(range(5,44,2)),cooldown_laps=[44],
            groups=[dict(target_meters=400,reps=[[i] for i in range(4,43,2)],set_start_laps=[4,24])])}
        response=MagicMock()
        response.__enter__.return_value.read.return_value=json.dumps({'choices':[{'message':{'content':json.dumps(proposal)}}]}).encode()
        laps=[dict(distanceMeters=m,durationMillis=t*1000) for m,t in values]
        with patch.dict('os.environ',{'OPENAI_API_KEY':'test'}), patch('core.views.polar_raw.urlopen',return_value=response), patch(
                'core.views.polar_raw.lap_zone_paces',side_effect=lambda m,t,a:('Z2' if 390<m<430 else 'Z1',None)):
            result=_model_b_ai_description(laps,strict_lap_structure=True)
        self.assertEqual(result.structure['training_fields']['main'],'2×(10×400 m Z2 p60) sp318')
        loads=[dict(meters=m,seconds=t,zone='2',hr_samples=[[t-1,160]],average_hr=150) for m,t in values]
        part={}
        self.assertTrue(apply_lap_structure(part,loads,result.structure))
        athlete=SimpleNamespace(zone_hr_bpm={'1':'max 150','2':'151-170','3':'171-180','4':'181-190','5':'max 205'})
        d=apply_garmin_d([{'parts':[part]}],athlete)[0]['parts'][0]
        for source,candidate in [('watch_c',part),('watch_d',d)]:
            segment=_virtual_segment_from_text('CORE',candidate['training_fields']['main'])
            slot=SimpleNamespace(source=source,watch_loads=candidate['watch_loads'],segments=SimpleNamespace(all=lambda:[segment]))
            reps=processed_main_reps(slot)
            self.assertEqual([r['measured_seconds'] for r in reps],[t for m,t in work])
            self.assertEqual([(l['meters'],l['seconds']) for l in candidate['watch_loads']],values)
        for starts in ([4,25],[24,4],[4,4],[4,22]):
            bad=deepcopy(proposal);bad['lap_structure']['groups'][0]['set_start_laps']=starts
            self.assertIsNone(validate_lap_structure(bad,facts))

    def test_minute_block_separator_preserves_nested_sets_zones_and_paces(self):
        from core.training_text import split_main_segments
        self.assertEqual(split_main_segments("2×8′ Z2 p91 - 4×4′ Z2 p61"),
                         ["2×8′ Z2 p91", "4×4′ Z2 p61"])
        for text in ("2*(8′-4′) Z2-Z3", "2×8′ Z2-Z3 (3:32-->3:25 min/km)"):
            self.assertEqual(split_main_segments(text), [text])

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
            description = _model_b_ai_description(laps,strict_lap_structure=True)
        self.assertIsNotNone(description.structure)
        request = call.call_args.args[0]
        self.assertIn('lap_structure',request.data.decode())
        self.assertNotIn('heart_rate',request.data.decode())
        prompt = json.loads(json.loads(request.data)['messages'][1]['content'])
        self.assertEqual(set(prompt['output_schema']), {'lap_structure','confidence'})
        self.assertNotIn('legacy',prompt['task'])
        self.assertNotIn('Use the legacy segments/sets schema',json.loads(request.data)['messages'][0]['content'])

    def test_ai_failures_are_distinguishable_without_exposing_service_response(self):
        from core.views.polar_raw import _model_b_ai_description
        laps = [{'distanceMeters':f['distance_m'],'durationMillis':f['duration_s']*1000} for f in self.facts]
        cases = [('unavailable', '', None), ('service_error','test', OSError('private service detail')),
                 ('invalid_response','test', {}), ('rejected_structure','test', {'confidence':.1,'lap_structure':{}})]
        for expected,key,payload in cases:
            with self.subTest(status=expected):
                response = MagicMock()
                response.__enter__.return_value.read.return_value = json.dumps(
                    {'choices':[{'message':{'content':json.dumps({} if isinstance(payload,Exception) else payload)}}]}).encode()
                diagnostics = {}
                with patch.dict('os.environ',{'OPENAI_API_KEY':key}), patch('core.views.polar_raw.urlopen',
                        side_effect=payload if isinstance(payload,Exception) else None,return_value=response), patch(
                        'core.views.polar_raw.lap_zone_paces',return_value=('Z2','NA')):
                    self.assertEqual(_model_b_ai_description(laps,diagnostics=diagnostics,strict_lap_structure=True),'')
                self.assertEqual(diagnostics['status'],expected)
                self.assertNotIn('private service detail',str(diagnostics))

    def test_invalid_ai_structure_gets_one_repair_with_validation_feedback(self):
        from core.views.polar_raw import _model_b_ai_description
        laps=[dict(distanceMeters=f['distance_m'],durationMillis=f['duration_s']*1000) for f in self.facts]
        invalid=deepcopy(self.proposal)
        invalid['lap_structure']['warmup_laps']=[1,2,3]
        invalid['lap_structure']['stop_laps']=[]
        def response(data):
            result=MagicMock()
            result.__enter__.return_value.read.return_value=json.dumps({'choices':[{'message':{'content':json.dumps(data)}}]}).encode()
            return result
        for repair_succeeds in (True,False):
            diagnostics={}
            with patch.dict('os.environ',{'OPENAI_API_KEY':'test'}), patch('core.views.polar_raw.urlopen',
                    side_effect=[response(invalid),response(self.proposal if repair_succeeds else invalid)]) as call, patch(
                    'core.views.polar_raw.lap_zone_paces',return_value=('Z2','NA')):
                result=_model_b_ai_description(laps,strict_lap_structure=True,diagnostics=diagnostics)
            self.assertEqual(call.call_count,2)
            feedback=json.loads(call.call_args.args[0].data)['messages'][-1]['content']
            self.assertIn('slower than 2 m/s',feedback)
            if repair_succeeds:
                self.assertTrue(result.structure)
                self.assertEqual(diagnostics['status'],'applied')
            else:
                self.assertEqual(result,'')
                self.assertEqual(diagnostics['status'],'rejected_structure')
                self.assertIn('slower than 2 m/s',diagnostics['reason'])

    def test_confidence_rejection_distinguishes_score_from_invalid_format(self):
        for value, expected in ((.6,'0.60'),(1.5,'1.50'),('high','not a finite number'),(True,'not a finite number')):
            proposal=deepcopy(self.proposal);proposal['confidence']=value
            issues=[]
            self.assertIsNone(validate_lap_structure(proposal,self.facts,issues=issues))
            self.assertIn(expected,issues[0])

    def test_low_confidence_is_review_only_after_all_measurement_checks(self):
        from core.views.polar_raw import _model_b_ai_description
        laps=[dict(distanceMeters=f['distance_m'],durationMillis=f['duration_s']*1000) for f in self.facts]
        for corrupt in (False,True):
            proposal=deepcopy(self.proposal);proposal['confidence']=.7
            if corrupt:
                proposal['lap_structure']['groups'][0]['reps'][0].append(99)
            response=MagicMock()
            response.__enter__.return_value.read.return_value=json.dumps({'choices':[{'message':{'content':json.dumps(proposal)}}]}).encode()
            diagnostics={}
            with patch.dict('os.environ',{'OPENAI_API_KEY':'test'}), patch('core.views.polar_raw.urlopen',return_value=response), patch(
                    'core.views.polar_raw.lap_zone_paces',return_value=('Z2','NA')):
                self.assertEqual(_model_b_ai_description(laps,strict_lap_structure=True,diagnostics=diagnostics),'')
            self.assertEqual(diagnostics['status'],'rejected_structure' if corrupt else 'review_available')
            self.assertEqual('review_structure' in diagnostics,not corrupt)
            self.assertIsNone(validate_lap_structure(proposal,self.facts))

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
            result = translate_model_b([session],5,allow_ai=False,allow_lap_structure=True)
            self.assertNotIn('validated_lap_structure',result[0]['parts'][0])
            self.assertEqual(result[0]['parts'][0]['ai_structure_status'],'consent_required')
