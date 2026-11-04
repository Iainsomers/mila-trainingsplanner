from types import SimpleNamespace
from django.test import SimpleTestCase
from core.views.calendar import _ayc_slot_loads_for_totals, _VirtualSlot, _virtual_segment_from_text
from core.stats import _alt_zone_durations


class AlternativeProgressionTests(SimpleTestCase):
    def test_combined_and_split_segments_agree_on_repeated_progression(self):
        text = "20'z1 // 15*3' z2>z3 // 10'z1 p1"
        combined = SimpleNamespace(type='ALT', text=text, zone='1', duration_s=1200)
        expected = [('1',1200),('2',1350),('3',1350),('1',600)]
        self.assertEqual(_alt_zone_durations(combined), expected)
        split = [_virtual_segment_from_text('ALT', part.strip()) for part in text.split('//')]
        self.assertEqual([pair for seg in split for pair in _alt_zone_durations(seg)], expected)
        for segments in [[combined],split]:
            loads = _ayc_slot_loads_for_totals(_VirtualSlot(segments))
            self.assertEqual([(l['zone'],l['seconds']) for l in loads], expected)
            self.assertTrue(all(l['kind']=='alt' and not l.get('meters') for l in loads))

    def test_downward_and_three_zone_ranges_preserve_total_duration(self):
        for text, expected in [("9' z1>z3", [('1',180),('2',180),('3',180)]),
                               ("3*3' z3>z2", [('3',270),('2',270)]),
                               ("9' z2", [('2',540)])]:
            seg = SimpleNamespace(type='ALT',text=text,zone='2',duration_s=None)
            self.assertEqual(_alt_zone_durations(seg),expected)
            self.assertEqual(sum(s for _,s in expected),540)
