from copy import deepcopy
from types import SimpleNamespace
from django.test import SimpleTestCase
from core.watch_alternatives import add_training_alternatives, long_interval_options, prefer_explicit_time_request
from core.garmin_d import apply_garmin_d
from core.watch_processing import processed_main_reps


class WatchAlternativesTests(SimpleTestCase):
    def test_explicit_time_request_selects_time_without_ambiguity_choice(self):
        options = [
            dict(label='Distance',training_fields={'main':'4×1800 m Z1 p61'},
                 description='distance',watch_loads=[{'kind':'distance'}]),
            dict(label='Time',training_fields={'main':"4×8' Z1 p61"},
                 description='time',watch_loads=[{'kind':'time'}]),
        ]
        for request in ("4*8'", '4 x 8 minuten', 'Maak er 4×8 min van'):
            part = {'training_alternatives':deepcopy(options)}
            prefer_explicit_time_request([{'parts':[part]}],[{'role':'user','content':request}])
            self.assertEqual(part['training_fields']['main'],"4×8' Z1 p61")
            self.assertEqual([option['label'] for option in part['training_alternatives']],['Time'])
            self.assertEqual(part['watch_loads'],[{'kind':'time'}])

        ambiguous = {'training_alternatives':deepcopy(options),'training_fields':{'main':'original'}}
        prefer_explicit_time_request([{'parts':[ambiguous]}],[{'role':'user','content':'Welke training was dit?'}])
        self.assertEqual(ambiguous['training_fields']['main'],'original')
        self.assertEqual([option['label'] for option in ambiguous['training_alternatives']],['Distance','Time'])

    def test_single_time_series_keeps_all_reps_for_c_and_d(self):
        values = [(997.78,242),(67.3198,64),(990.69,241),(91.9199,62),
                  (1008.96,243),(95.0195,61),(1014.68,242),(126.16,80),
                  (1025.32,242),(96.1904,62),(1080.86,245),(99.2207,64),
                  (1083.15,243),(150.73,297)]
        loads = [{'segment':'WU','zone':'1','meters':5031.7,'seconds':4643}]
        loads += [dict(segment='CORE',zone='2' if i%2==0 else '1',meters=m,seconds=s)
                  for i,(m,s) in enumerate(values)]
        loads += [dict(segment='CD',zone='1',meters=1495.04,seconds=460)]
        fields = {'wu':'5050 m Z1','main':'5×1000 m Z2 + 2×1100 m Z2','cd':'1500 m Z1'}
        results = [{'parts':[dict(training_fields=fields,watch_loads=deepcopy(loads))]}]
        add_training_alternatives(results)
        athlete = SimpleNamespace(zone_hr_bpm={})
        from core.views.calendar import _virtual_segment_from_text
        for source, result in [('watch_c',results),('watch_d',apply_garmin_d(deepcopy(results),athlete))]:
            part = result[0]['parts'][0]
            self.assertEqual([option['label'] for option in part['training_alternatives']],['Time','Distance'])
            timed = part['training_alternatives'][0]
            self.assertEqual(timed['training_fields']['main'],"7×4' Z2 p63")
            self.assertEqual(part['training_fields'],timed['training_fields'])
            self.assertEqual(part['training_alternatives'][1]['training_fields'],fields)
            self.assertEqual([(l['meters'],l['seconds']) for l in timed['watch_loads']],
                             [(l['meters'],l['seconds']) for l in loads])
            segment = _virtual_segment_from_text('CORE',timed['training_fields']['main'])
            slot = SimpleNamespace(source=source,watch_loads=timed['watch_loads'],segments=SimpleNamespace(all=lambda:[segment]))
            self.assertEqual([r['measured_seconds'] for r in processed_main_reps(slot)],
                             [242,241,243,242,242,245,243])

    def test_single_time_rule_is_general_and_rejects_false_patterns(self):
        from core.watch_alternatives import single_time_option
        for count, minutes in [(3,2),(5,6),(9,10)]:
            core = [dict(meters=minutes*200 if i%2==0 else 80,
                         seconds=minutes*60 if i%2==0 else 60,
                         zone='3' if i%2==0 else '1') for i in range(count*2)]
            self.assertEqual(single_time_option(core),f"{count}×{minutes}' Z3 p60")
            wrong = deepcopy(core)
            wrong[2]['seconds'] += 40
            self.assertIsNone(single_time_option(wrong))
            wrong = deepcopy(core)
            wrong[1]['meters'] = 300
            self.assertIsNone(single_time_option(wrong))

    def setUp(self):
        values = [(2970.31,611),(203.83,106),(3001.14,598),(105.59,283),
                  (2967.94,591),(117.671,224),(1001.82,184),(131.431,88),(997.329,178),(119.4,295)]
        self.loads = [{'segment':'CORE','zone':'2' if i%2==0 else '1', 'meters':m,'seconds':s,
                       'average_hr_last_15':168 if i%2==0 else 120} for i,(m,s) in enumerate(values)]
        self.laps = [{'distanceMeters':l['meters'],'durationMillis':l['seconds']*1000,'zone':'Z'+l['zone']} for l in self.loads]

    def test_both_complete_options_preserve_data_and_measured_time_reps(self):
        options = long_interval_options(self.laps, lambda lap:lap['zone'])
        self.assertEqual(options['distance'], '3×3000 m Z2 p106 + 2×1000 m Z2 p88')
        self.assertEqual(options['time'], "3×10' Z2 p106 + 2×3' Z2 p88")
        results = [{'parts':[{'training_fields':{'wu':'','main':"611s Z2 + 10' Z2",'cd':''},'watch_loads':deepcopy(self.loads)}]}]
        add_training_alternatives(results)
        part = results[0]['parts'][0]
        self.assertEqual([a['label'] for a in part['training_alternatives']],['Distance','Time'])
        self.assertEqual(part['training_fields']['main'],options['distance'])
        self.assertEqual(part['watch_loads'],self.loads)
        from core.views.calendar import _virtual_segment_from_text, _ayc_slot_loads_for_totals
        for alternative in part['training_alternatives']:
            segments = [_virtual_segment_from_text('CORE',t) for t in alternative['training_fields']['main'].split(' + ')]
            slot = SimpleNamespace(source='watch_c',watch_loads=alternative['watch_loads'],segments=SimpleNamespace(all=lambda:segments))
            self.assertEqual([r['measured_seconds'] for r in processed_main_reps(slot)], [611,598,591,184,178])
            self.assertAlmostEqual(sum(l['meters'] for l in _ayc_slot_loads_for_totals(slot)),
                sum(l['meters'] for l in self.loads if l['seconds'] <= l['meters']*.6))
        athlete=SimpleNamespace(zone_hr_bpm={'1':'max 150','2':'151-170','3':'171-188','4':'189-194','5':'max 205'})
        d = apply_garmin_d(results,athlete)[0]['parts'][0]
        self.assertEqual(len(d['training_alternatives']),2)
        self.assertTrue(all('Z2' in a['training_fields']['main'] for a in d['training_alternatives']))
        self.assertTrue(all(a['watch_loads'] == d['watch_loads'] for a in d['training_alternatives']))

    def test_no_alternatives_without_complete_recovery_pattern(self):
        laps = deepcopy(self.laps)
        laps[3]['distanceMeters']=1000
        self.assertIsNone(long_interval_options(laps,lambda lap:lap['zone']))
        laps=deepcopy(self.laps)
        laps[4]['durationMillis']=450000
        self.assertIsNone(long_interval_options(laps,lambda lap:lap['zone']))
