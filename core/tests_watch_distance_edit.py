from copy import deepcopy
from unittest.mock import MagicMock, patch
import json
from django.test import SimpleTestCase
from core.watch_distance_edit import apply_distance_edit, propose_distance_edit


class DistanceEditTests(SimpleTestCase):
    def example(self):
        loads = [dict(segment='WU',meters=5500,seconds=1700,zone='1')]
        for longer,shorter in zip((182.05,175.32,175.94,167.25,169.27,171.58),
                                  (147.311,135.51,138.359,143.21,139.489,139.091)):
            for meters,target in ((longer,200),(shorter,150)):
                loads.extend([dict(segment='CORE',work_rep=True,nominal_rep_m=target,meters=meters,seconds=33,zone='4'),
                              dict(segment='CORE',work_rep=False,meters=190,seconds=140,zone='1')])
        return dict(training_fields=dict(wu='5500 m Z1',main='2400 m Z1 + 4×50 m Z5 p92 + 6×200 m Z4 p139 + 6×150 m Z4>Z5 p134',cd='1850 m Z1'),watch_loads=loads)

    def test_changes_only_target_metadata_and_text_for_existing_six_reps(self):
        part = self.example()
        original = deepcopy(part)
        edited = apply_distance_edit(part,dict(count=6,from_m=200,to_m=185))
        self.assertIsNotNone(edited)
        self.assertEqual(part,original)
        self.assertEqual(edited['training_fields']['main'],original['training_fields']['main'].replace('6×200 m','6×185 m'))
        for before,after in zip(part['watch_loads'],edited['watch_loads']):
            expected = dict(before)
            if expected.get('nominal_rep_m') == 200:
                expected['nominal_rep_m'] = 185
            self.assertEqual(after,expected)
        self.assertIsNotNone(apply_distance_edit(edited,dict(count=6,from_m=185,to_m=190)))

    def test_bad_distance_missing_membership_and_ambiguous_group_are_rejected(self):
        for change in ('distance','membership','ambiguous'):
            part=self.example()
            if change=='distance': part['watch_loads'][1]['meters']=140
            if change=='membership': part['watch_loads'][1].pop('nominal_rep_m')
            if change=='ambiguous': part['training_fields']['main'] += ' + 6×200 m Z4'
            self.assertIsNone(apply_distance_edit(part,dict(count=6,from_m=200,to_m=185)))

    def test_ai_only_extracts_edit_and_measured_validation_still_decides(self):
        response=MagicMock()
        response.__enter__.return_value.read.return_value=json.dumps({'choices':[{'message':{'content':json.dumps(
            dict(confidence=.96,distance_edit=dict(count=6,from_m=200,to_m=185)))}}]}).encode()
        with patch.dict('os.environ',{'OPENAI_API_KEY':'test'}),patch('core.watch_distance_edit.urlopen',return_value=response):
            self.assertIsNotNone(propose_distance_edit(self.example(),[dict(role='user',content='Maak de zes langere reps 185m, behoud de rest')]))
