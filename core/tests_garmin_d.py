from copy import deepcopy
from types import SimpleNamespace

from django.test import SimpleTestCase

from core.garmin_d import apply_garmin_d, hr_zone, rep_hr_zone
from core.watch_processing import processed_main_reps


class GarminDTests(SimpleTestCase):
    def setUp(self):
        self.athlete = SimpleNamespace(zone_hr_bpm={
            '1': 'max 150', '2': '151-170', '3': '171-188', '4': '189-194', '5': 'max 205'})

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

    def test_complete_timed_reps_use_final_hr_and_keep_measured_distance(self):
        loads = []
        for block in range(5):
            for meters, seconds, pace_zone, hr in [(1000,200,'2',167),(1000,200,'3',172),(400,80,'3',168)]:
                loads.append({'segment':'CORE','zone':pace_zone,'meters':meters,'seconds':seconds,
                              'average_hr':160,'average_hr_last_15':hr})
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
