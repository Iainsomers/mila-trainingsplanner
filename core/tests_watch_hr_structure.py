from copy import deepcopy
from types import SimpleNamespace
from django.test import SimpleTestCase
from core.watch_hr_structure import apply_hr_distance_structure
from core.garmin_d import apply_garmin_d
from core.watch_processing import processed_main_reps
from core.views.calendar import _virtual_segment_from_text


class HRDistanceStructureTests(SimpleTestCase):
    def setUp(self):
        self.athlete=SimpleNamespace(zone_hr_bpm={'1':'max 150','2':'151-170','3':'171-188','4':'189-194','5':'max 205'})
        values=[(1000,284.31,171),(1000,340.61,118),(22.9,12.19,117),(1000,280.23,173),
                (634.19,355.91,122),(1000,277.53,174),(198.12,436.62,120),(1000,270.28,175),
                (390.85,313.63,137),(1000,265.84,178),(446.9,368.71,137),(1000,261.46,178),
                (1000,732.83,125),(1000,297.95,129),(379.23,115.15,141)]
        self.loads=[dict(segment='CORE',zone='1',meters=m,seconds=s,average_hr=hr,hr_samples=[[s-1,hr]]) for m,s,hr in values]

    def test_six_work_reps_split_recovery_and_cooldown_for_both_models(self):
        before=deepcopy(self.loads)
        part={}
        self.assertTrue(apply_hr_distance_structure(part,self.loads,self.athlete))
        self.assertEqual(part['training_fields'],{'wu':'','main':'6×1000 m Z1 p356','cd':'1400 m Z1'})
        self.assertEqual([i+1 for i,l in enumerate(part['watch_loads']) if l['work_rep']],[1,4,6,8,10,12])
        d=apply_garmin_d([{'parts':[part]}],self.athlete)[0]['parts'][0]
        self.assertEqual(d['training_fields']['main'],'6×1000 m Z3 p356')
        for source,candidate in [('watch_c',part),('watch_d',d)]:
            seg=_virtual_segment_from_text('CORE',candidate['training_fields']['main'])
            slot=SimpleNamespace(source=source,watch_loads=candidate['watch_loads'],segments=SimpleNamespace(all=lambda:[seg]))
            reps=processed_main_reps(slot)
            self.assertEqual([r['measured_seconds'] for r in reps],[284.31,280.23,277.53,270.28,265.84,261.46])
            self.assertEqual([r['hr_tail'] for r in reps],[171,173,174,175,178,178])
            self.assertEqual([(l['meters'],l['seconds']) for l in candidate['watch_loads']],[(l['meters'],l['seconds']) for l in before])
        self.assertEqual(self.loads,before)

    def test_does_not_override_other_pace_patterns_or_guess_missing_hr(self):
        mutations=[lambda l:l[0].update(zone='3'),lambda l:l[0].update(hr_samples=[]),
                   lambda l:l[9].update(seconds=500),lambda l:l[9].update(meters=1500),
                   lambda l:l[4].update(hr_samples=[[354,170]]),lambda l:l[6].update(seconds=1200)]
        for mutate in mutations:
            loads=deepcopy(self.loads);mutate(loads)
            part={'description':'existing result'}
            self.assertFalse(apply_hr_distance_structure(part,loads,self.athlete))
            self.assertEqual(part,{'description':'existing result'})
        self.assertFalse(apply_hr_distance_structure({},self.loads,SimpleNamespace(zone_hr_bpm={})))

    def test_continuous_kilometre_runs_and_missing_recovery_are_rejected(self):
        continuous=[dict(segment='CORE',zone='1',meters=1000,seconds=280,average_hr=175,hr_samples=[[279,175]]) for _ in range(8)]
        self.assertFalse(apply_hr_distance_structure({},continuous,self.athlete))
        flat=deepcopy(self.loads)
        for load in flat:load['hr_samples']=[[load['seconds']-1,145]];load['average_hr']=145
        self.assertFalse(apply_hr_distance_structure({},flat,self.athlete))
        self.assertFalse(apply_hr_distance_structure({},[self.loads[i] for i in [0,3,5,7,9,11]],self.athlete))
