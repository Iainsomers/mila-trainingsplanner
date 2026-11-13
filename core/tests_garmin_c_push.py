import json
from datetime import datetime, timezone as dt_timezone
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from core.models import Athlete, GarminConnection, GarminActivitySummary
from core.views.garmin import receiver_key


@override_settings(GARMIN_CLIENT_ID="test-id", GARMIN_CLIENT_SECRET="test-secret", GARMIN_REDIRECT_URI="https://example.org/callback/")
class GarminCPushTests(TestCase):
    def setUp(self):
        self.coach = get_user_model().objects.create_user(username="garmin-c-coach", is_staff=True)
        self.athlete = Athlete.objects.create(owner=self.coach, name="Garmin C runner", birth_year=2000,
            gender="X", garmin_connection_enabled=True)
        GarminConnection.objects.create(athlete=self.athlete, garmin_user_id="runner-id", access_token="private-token", data_consent_at=timezone.now())
        self.start = int(datetime(2026, 10, 31, 10, tzinfo=dt_timezone.utc).timestamp())
        self.summary = {"userId": "runner-id", "activityId": 456, "summaryId": "summary-456",
            "startTimeInSeconds": self.start, "distanceInMeters": 1000, "durationInSeconds": 300}
        self.push_url = reverse("garmin_activity_push", args=[receiver_key()])

    def test_chat_requests_confirmation_for_one_longer_timed_rep(self):
        from types import SimpleNamespace
        from urllib.parse import urlencode
        from core.views.calendar import _virtual_segment_from_text
        from core.watch_processing import processed_main_reps

        values = [(1315.1,362),(63.87,46),(1301.07,360),(61.72,45),(1275.4,361),
                  (59.6702,45),(1427.69,405),(54.75,45),(1292.75,360),(64.0601,46),(1296.08,361)]
        GarminActivitySummary.objects.create(athlete=self.athlete,activity_id='timed-outlier',
            activity_start=datetime.fromtimestamp(self.start,dt_timezone.utc),activity_date='2026-10-31',
            distance_m=sum(m for m,s in values),duration_s=sum(s for m,s in values),
            analysis_data={'laps':[dict(distance=m,elapsed_time=s) for m,s in values]})
        self.client.force_login(self.coach)
        with patch('core.views.polar_raw.lap_zone_paces',return_value=('Z1','NA')), patch(
                'core.views.polar_raw.urlopen',side_effect=AssertionError('Local time request')):
            for model in ('c','d'):
                url = reverse(f'garmin_type_{model}_ayc')
                query = {'athlete':self.athlete.pk,'date':'2026-10-31','preview':'measured'}
                activity = self.client.get(url,query).json()['results'][0]
                chat_url = url+'?'+urlencode({**query,'suggestion_session':activity['start']})
                payload = {'chat':json.dumps([{'role':'user','content':"6*6'"}])}
                proposed = self.client.post(chat_url,payload).json()
                self.assertFalse(proposed['ok'])
                self.assertEqual(proposed['results'],[])
                self.assertIn('Rep 4 lasted 6:45',proposed['chat_reply'])
                token = proposed['confirmation_required']['token']
                invalid = self.client.post(chat_url,{**payload,'time_confirmation':token+'invalid'})
                self.assertEqual(invalid.status_code,400)
                confirmed = self.client.post(chat_url,{**payload,'time_confirmation':token}).json()
                self.assertTrue(confirmed['ok'],confirmed)
                part = confirmed['results'][0]['parts'][0]
                self.assertEqual(part['training_fields']['main'],"6×6' Z1 p45")
                self.assertEqual([(l['meters'],l['seconds']) for l in part['watch_loads']],values)
                slot = SimpleNamespace(source=f'watch_{model}',watch_loads=part['watch_loads'],
                    segments=SimpleNamespace(all=lambda:[_virtual_segment_from_text('CORE',part['training_fields']['main'])]))
                self.assertEqual([r['measured_seconds'] for r in processed_main_reps(slot)],[362,360,361,405,360,361])
                from django.core import signing
                import time
                with patch('django.core.signing.time.time',return_value=time.time()+601):
                    with self.assertRaises(signing.SignatureExpired):
                        signing.loads(token,salt='watch-time-outlier',max_age=600)
                changed = self.client.post(chat_url,{
                    'chat':json.dumps([{'role':'user','content':"5*6'"}]),'time_confirmation':token}).json()
                self.assertFalse(changed['ok'])
                self.assertNotIn('confirmation_required',changed)

    def test_chat_groups_autolaps_with_user_supplied_repetition_context(self):
        from types import SimpleNamespace
        from urllib.parse import urlencode
        from core.views.calendar import _virtual_segment_from_text
        from core.watch_processing import processed_main_reps

        values = [(1003.64,280),(631.66,181),(1003.71,284),(608.46,174),
                  (497.25,124),(1.58008,1),(498,118),(507.25,120),(505.59,125),
                  (510.38,121),(510.21,122),(506.2,118),(507.53,122)]
        GarminActivitySummary.objects.create(athlete=self.athlete,activity_id='unrecorded-recovery',
            activity_start=datetime.fromtimestamp(self.start,dt_timezone.utc),activity_date='2026-10-31',
            distance_m=sum(m for m,s in values),duration_s=sum(s for m,s in values),
            analysis_data={'laps':[dict(distance=m,elapsed_time=s) for m,s in values]})
        self.client.force_login(self.coach)
        with patch('core.views.polar_raw.lap_zone_paces',
                   side_effect=lambda m,ms,a: ('Z2' if m/(ms/1000)<3.8 else 'Z4','NA')), patch(
                   'core.views.polar_raw.urlopen',side_effect=AssertionError('Explicit measured request')):
            for model in ('c','d'):
                url = reverse(f'garmin_type_{model}_ayc')
                query = {'athlete':self.athlete.pk,'date':'2026-10-31','preview':'measured'}
                activity = self.client.get(url,query).json()['results'][0]
                chat_url = url+'?'+urlencode({**query,'suggestion_session':activity['start']})
                for message in ('1650m//1600m//8*500m','2*1625m//8*500m'):
                    reply = self.client.post(chat_url,{'chat':json.dumps([{'role':'user','content':message}])}).json()
                    self.assertTrue(reply['ok'],reply)
                    part = reply['results'][0]['parts'][0]
                    self.assertNotIn(' p',part['training_fields']['main'])
                    self.assertIn('onbekend',part['chat_reply'])
                    self.assertEqual([(l['meters'],l['seconds']) for l in part['watch_loads']],values)
                    slot = SimpleNamespace(source=f'watch_{model}',watch_loads=part['watch_loads'],
                        segments=SimpleNamespace(all=lambda:[_virtual_segment_from_text('CORE',part['training_fields']['main'])]))
                    reps = processed_main_reps(slot)
                    self.assertEqual(len(reps),10)
                    self.assertEqual([r['measured_seconds'] for r in reps],[461,458,124,118,120,125,121,122,118,122])
                    self.assertEqual([r['measured_distance_m'] for r in reps[:2]],[1635.3,1612.17])
                rejected = self.client.post(chat_url,{'chat':json.dumps([
                    {'role':'user','content':'1650m//1600m//9*500m'}])}).json()
                self.assertFalse(rejected['ok'])

    def test_descending_short_sets_preserve_strides_and_allow_full_chat_request(self):
        from types import SimpleNamespace
        from urllib.parse import urlencode
        from core.views.calendar import _virtual_segment_from_text
        from core.watch_processing import processed_main_reps

        values = [(1004.2,302),(1001.65,293),(999.882,305),(999.049,1319),(808.664,970),
                  (31.8198,7),(137.45,126),(28.7397,8),(90.7803,157),(36.3799,8),(104.58,402),
                  (205.26,38),(225.6,130),(180.98,33),(205.15,119),(140.87,22),(221.18,252),
                  (204.09,39),(232.3,118),(180.45,32),(197.33,130),(136.43,24),(202.1,251),
                  (197.17,36),(235.3,121),(176.13,31),(207.46,122),(130.46,23),(188.84,154),
                  (1005.45,339),(770.59,281)]
        zones = {6:'Z2',10:'Z2',12:'Z3',14:'Z3',16:'Z5',18:'Z3',20:'Z4',22:'Z4',24:'Z3',26:'Z4',28:'Z4'}
        measured_zones = {row:zones.get(i,'Z1') for i,row in enumerate(values,1)}
        GarminActivitySummary.objects.create(athlete=self.athlete, activity_id='descending-short-sets',
            activity_start=datetime.fromtimestamp(self.start,dt_timezone.utc),activity_date='2026-10-31',
            distance_m=sum(m for m,s in values),duration_s=sum(s for m,s in values),
            analysis_data={'laps':[dict(distance=m,elapsed_time=s) for m,s in values]})
        self.client.force_login(self.coach)
        with patch('core.views.polar_raw.lap_zone_paces',
                   side_effect=lambda m,ms,a:(measured_zones.get((m,ms/1000),'Z1'),'NA')), patch(
                   'core.views.polar_raw.urlopen',side_effect=AssertionError('Measured structure')):
            for model in ('c','d'):
                url = reverse(f'garmin_type_{model}_ayc')
                query = {'athlete':self.athlete.pk,'date':'2026-10-31'}
                activity = self.client.get(url,query).json()['results'][0]
                auto = activity['parts'][0]['training_fields']
                self.assertIn('3×50 m',auto['main'])
                self.assertIn('3×(200 m - 180 m - 140 m)',auto['main'])
                chat_url = url+'?'+urlencode({**query,'suggestion_session':activity['start']})
                message = '4800m//3*50m//3*(200m-190m-150m)//1950m'
                reply = self.client.post(chat_url,{'chat':json.dumps([{'role':'user','content':message}])}).json()
                self.assertTrue(reply['ok'],reply)
                part = reply['results'][0]['parts'][0]
                fields = part['training_fields']
                self.assertEqual((fields['wu'],fields['cd']),('4800 m Z1','1950 m Z1'))
                self.assertIn('3×(200 m - 190 m - 150 m)',fields['main'])
                self.assertEqual([(l['meters'],l['seconds']) for l in part['watch_loads']],values)
                slot = SimpleNamespace(source=f'watch_{model}',watch_loads=part['watch_loads'],
                    segments=SimpleNamespace(all=lambda:[_virtual_segment_from_text('CORE',fields['main'])]))
                reps = processed_main_reps(slot)
                self.assertEqual([r['distance_m'] for r in reps],[50]*3+[200,190,150]*3)
                self.assertEqual(reps[5]['measured_distance_m'],140.87)
                self.assertEqual(reps[5]['measured_seconds'],22)
                rejected = self.client.post(chat_url,{'chat':json.dumps([
                    {'role':'user','content':message.replace('190m-150m','190m-200m')}])}).json()
                self.assertFalse(rejected['ok'])

    def test_mixed_set_chat_validates_distance_drift_and_leading_walking(self):
        from types import SimpleNamespace
        from urllib.parse import urlencode

        from core.views.calendar import _virtual_segment_from_text
        from core.watch_processing import processed_main_reps

        values = [(3480.53,1134),(649.31,460),(1692.92,418),(47.3804,99),(1177.6,275),
                  (47.21,90),(843.75,184),(154.89,241),(1684.42,412),(49.9307,102),
                  (1156.79,265),(52,95),(849,175),(1900,620)]
        zones = ['Z1','Z1','Z2','Z1','Z3','Z1','Z3','Z1','Z2','Z1','Z3','Z1','Z4','Z1']
        measured_zones = dict(zip(values,zones))
        GarminActivitySummary.objects.create(athlete=self.athlete, activity_id='mixed-distance-drift',
            activity_start=datetime.fromtimestamp(self.start, dt_timezone.utc), activity_date='2026-10-31',
            distance_m=sum(m for m,s in values), duration_s=sum(s for m,s in values),
            analysis_data={'laps':[dict(distance=m,elapsed_time=s) for m,s in values]})
        self.client.force_login(self.coach)
        with patch('core.views.polar_raw.lap_zone_paces',
                   side_effect=lambda m,ms,a: (measured_zones.get((m,ms/1000),'Z1'),'NA')), patch(
                   'core.views.polar_raw.urlopen',side_effect=AssertionError('Explicit sets use measured laps')):
            for model in ('c','d'):
                url = reverse(f'garmin_type_{model}_ayc')
                query = {'athlete':self.athlete.pk,'date':'2026-10-31'}
                activity = self.client.get(url,query).json()['results'][0]
                expected = '2×(1700 m - 1200 m - 850 m) Z2>Z4 p97 sp241'
                self.assertEqual(activity['parts'][0]['training_fields']['main'],expected)
                chat_url = url + '?' + urlencode({**query,'suggestion_session':activity['start']})
                for message in ('2*(1700m-1200m-850m)', '2*(1700m-1200m-850m) z2>z4'):
                    result = self.client.post(chat_url,{'chat':json.dumps([{'role':'user','content':message}])}).json()
                    self.assertTrue(result['ok'],result)
                    part = result['results'][0]['parts'][0]
                    self.assertEqual(part['training_fields']['main'],expected)
                    self.assertEqual([(l['meters'],l['seconds']) for l in part['watch_loads']],values)
                    slot = SimpleNamespace(source=f'watch_{model}',watch_loads=part['watch_loads'],
                        segments=SimpleNamespace(all=lambda:[_virtual_segment_from_text('CORE',expected)]))
                    reps = processed_main_reps(slot)
                    self.assertEqual([r['distance_m'] for r in reps],[1700,1200,850]*2)
                    self.assertEqual(reps[4]['measured_distance_m'],1156.79)
                    self.assertEqual(reps[4]['measured_seconds'],265)
                rejected = self.client.post(chat_url,{'chat':json.dumps([
                    {'role':'user','content':'2*(1700m-1350m-850m)'}])}).json()
                self.assertFalse(rejected['ok'])
                self.assertEqual(rejected['results'],[])

    def test_mixed_distance_sets_and_existing_flat_clock_ignore_zone_drift(self):
        from types import SimpleNamespace
        from core.views.calendar import _annotate_slot_segment_display_times, _virtual_segment_from_text
        from core.watch_processing import match_repeating_distance_sets, processed_main_reps

        distances = [1700,1200,850] * 2
        times = [351,233,158,334,220,144]
        zones = ['Z2','Z2','Z3','Z3','Z3','Z4']
        values = [(1950,580)]
        measured_zones = {(1950,580):'Z1'}
        for index, (distance, seconds, zone) in enumerate(zip(distances,times,zones)):
            values.append((distance,seconds))
            measured_zones[distance,seconds] = zone
            if index < 5:
                values.append((60,180 if index == 2 else 60))
                measured_zones[values[-1]] = 'Z1'
        values.append((2000,570))
        measured_zones[values[-1]] = 'Z1'
        GarminActivitySummary.objects.create(athlete=self.athlete, activity_id='mixed-distance-sets',
            activity_start=datetime.fromtimestamp(self.start, dt_timezone.utc), activity_date='2026-10-31',
            distance_m=sum(m for m,s in values), duration_s=sum(s for m,s in values),
            analysis_data={'laps':[dict(distance=m,elapsed_time=s) for m,s in values]})
        self.client.force_login(self.coach)
        old_main = ' + '.join(f'1×{distance} m {zone}' for distance,zone in
                             zip(distances,['Z2','Z2','Z3','Z3','Z2','Z4']))
        with patch('core.views.polar_raw.lap_zone_paces',
                   side_effect=lambda m,ms,a: (measured_zones.get((m,ms/1000),'Z1'),'NA')):
            for model in ('c','d'):
                url = reverse(f'garmin_type_{model}_ayc')
                part = self.client.get(url,{'athlete':self.athlete.pk,'date':'2026-10-31'}).json()['results'][0]['parts'][0]
                main = part['training_fields']['main']
                self.assertEqual(main, '2×(1700 m - 1200 m - 850 m) Z2>Z4 p60 sp180')
                loads = part['watch_loads']
                self.assertEqual([(load['meters'],load['seconds']) for load in loads], values)
                for text in (main,old_main):
                    slot = SimpleNamespace(source=f'watch_{model}',watch_loads=loads,
                        segments=SimpleNamespace(all=lambda:[_virtual_segment_from_text('CORE',text)]))
                    reps = processed_main_reps(slot)
                    self.assertEqual([r['distance_m'] for r in reps],distances)
                    self.assertEqual([r['measured_seconds'] for r in reps],times)
                loose_segments = [_virtual_segment_from_text('CORE',part.strip()) for part in old_main.split('+')]
                loose_slot = SimpleNamespace(source=f'watch_{model}',watch_loads=loads)
                loose_slot.segments = SimpleNamespace(all=lambda:loose_segments)
                for segment in loose_segments:
                    segment.slot = loose_slot
                _annotate_slot_segment_display_times(loose_slot,self.athlete)
                self.assertEqual([segment.display_text for segment in loose_segments], [
                    '1700m - 5:51 - 3:26/km', '1200m - 3:53 - 3:14/km',
                    '850m - 2:38 - 3:06/km', '1700m - 5:34 - 3:16/km',
                    '1200m - 3:40 - 3:03/km', '850m - 2:24 - 2:49/km',
                ])
                missing = [load for load in loads if load['seconds'] != 220]
                self.assertIsNone(match_repeating_distance_sets(old_main,missing))

    def test_easy_run_then_three_strides_preserves_all_laps_in_c_d_and_chat(self):
        from types import SimpleNamespace
        from urllib.parse import urlencode
        from unittest.mock import MagicMock
        from core.views.calendar import _virtual_segment_from_text
        from core.views.garmin import CONSENT_VERSION
        from core.watch_ai_structure import infer_easy_run_with_strides
        from core.watch_processing import processed_main_reps

        values = [(1005.27,327),(1000.84,308),(998.29,316),(1001.47,327),(997.8,318),
                  (1000.28,321),(1002.78,324),(997.69,318),(998,322),(1003.04,315),
                  (3.48047,1),(104.409,19),(109.641,95),(106.399,18),(95.3701,74),(110.54,18)]
        facts = [dict(lap=i, distance_m=m, duration_s=s,
                      zone='Z5' if i in (12,14,16) else 'Z2' if i == 11 else 'Z1')
                 for i,(m,s) in enumerate(values,1)]
        self.assertIsNone(infer_easy_run_with_strides(facts[:11]))
        self.assertIsNone(infer_easy_run_with_strides(facts[:-2]))
        too_fast_recovery = [dict(row,duration_s=20) if row['lap'] == 13 else row for row in facts]
        self.assertIsNone(infer_easy_run_with_strides(too_fast_recovery))
        GarminActivitySummary.objects.create(athlete=self.athlete, activity_id='easy-and-strides',
            activity_start=datetime.fromtimestamp(self.start, dt_timezone.utc), activity_date='2026-10-31',
            distance_m=sum(m for m,s in values), duration_s=sum(s for m,s in values),
            analysis_data={'laps':[dict(distance=m,elapsed_time=s) for m,s in values]})
        self.athlete.garmin_ai_consent_at = timezone.now()
        self.athlete.garmin_ai_consent_version = CONSENT_VERSION
        self.athlete.save()
        self.client.force_login(self.coach)
        proposal = dict(confidence=.96,lap_structure=dict(continuous_main_laps=list(range(1,12)),
            recovery_laps=[13,15],groups=[dict(target_meters=100,reps=[[12],[14],[16]])]))
        response = MagicMock()
        response.__enter__.return_value.read.return_value = json.dumps(
            {'choices':[{'message':{'content':json.dumps(proposal)}}]}).encode()
        with patch.dict('os.environ',{'OPENAI_API_KEY':'test'}), patch(
                'core.views.polar_raw.urlopen',return_value=response) as ai, patch(
                'core.views.polar_raw.lap_zone_paces',
                side_effect=lambda m,ms,a: ('Z5' if m / (ms / 1000) > 5 else 'Z2' if m < 5 else 'Z1','NA')):
            for model in ('c','d'):
                url = reverse(f'garmin_type_{model}_ayc')
                query = {'athlete':self.athlete.pk,'date':'2026-10-31'}
                before = ai.call_count
                for preview in ('measured',''):
                    activity = self.client.get(url,{**query,'preview':preview}).json()['results'][0]
                    self.assertEqual(activity['parts'][0]['ai_structure_status'],'measured_structure')
                self.assertEqual(ai.call_count,before)
                chat = self.client.post(url+'?'+urlencode({**query,'suggestion_session':activity['start']}),
                    {'chat':json.dumps([{'role':'user','content':'10000m Z1//3*100m Z5'}])}).json()
                self.assertTrue(chat['ok'],chat)
                for item in (activity,chat['results'][0]):
                    part = item['parts'][0]
                    fields = part['training_fields']
                    self.assertEqual(fields,{'wu':'','main':'10000 m Z1 + 3×100 m Z5 p85','cd':''})
                    self.assertEqual([(l['meters'],l['seconds']) for l in part['watch_loads']],values)
                    slot = SimpleNamespace(source=f'watch_{model}',watch_loads=part['watch_loads'],
                        segments=SimpleNamespace(all=lambda:[_virtual_segment_from_text('CORE',fields['main'])]))
                    reps = processed_main_reps(slot)
                    self.assertEqual([r['distance_m'] for r in reps],[10000,100,100,100])
                    self.assertEqual([r['measured_seconds'] for r in reps],[sum(s for m,s in values[:11]),19,18,18])

    def test_suggestion_targets_one_activity_and_hides_athlete_diagnostics(self):
        from unittest.mock import MagicMock
        from core.tests_watch_ai_structure import split_distance_example
        from core.views.garmin import CONSENT_VERSION
        from django.core.cache import cache
        cache.clear()
        self.addCleanup(cache.clear)
        facts, proposal = split_distance_example()
        self.athlete.garmin_ai_consent_at = timezone.now()
        self.athlete.garmin_ai_consent_version = CONSENT_VERSION
        self.athlete.save()
        GarminActivitySummary.objects.create(athlete=self.athlete, activity_id='suggestion',
            activity_start=datetime.fromtimestamp(self.start, dt_timezone.utc), activity_date='2026-10-31',
            distance_m=sum(f['distance_m'] for f in facts),
            analysis_data={'laps':[dict(distance=f['distance_m'], elapsed_time=f['duration_s']) for f in facts]})
        self.client.force_login(self.coach)
        response = MagicMock()
        response.__enter__.return_value.read.return_value = json.dumps(
            {'choices':[{'message':{'content':json.dumps(proposal)}}]}).encode()
        with patch.dict('os.environ', {'OPENAI_API_KEY':'test'}), patch(
                'core.views.polar_raw.urlopen', return_value=response) as ai, patch(
                'core.views.polar_raw.lap_zone_paces', return_value=('Z2','NA')):
            for route in ('garmin_type_c_ayc', 'garmin_type_d_ayc'):
                url = reverse(route)
                query = {'athlete':self.athlete.pk, 'date':'2026-10-31'}
                current = self.client.get(url, query).json()
                query.update(suggestion='4x3000m', suggestion_session=current['results'][0]['start'])
                found = self.client.get(url, query).json()
                self.assertTrue(found['ok'])
                self.assertEqual(found['results'][0]['parts'][0]['training_fields']['main'], '4\u00d73000 m Z2 p119')
                self.assertEqual(len(found['results'][0]['parts'][0]['watch_loads']), 16)
                chat_query = dict(query)
                chat_query.pop('suggestion')
                chat_url = url + '?' + __import__('urllib.parse',fromlist=['urlencode']).urlencode(chat_query)
                with patch('core.watch_distance_edit.propose_distance_edit', return_value=None):
                    chatted = self.client.post(chat_url, {'chat':json.dumps([
                        {'role':'user','content':'Kun je vier herhalingen van 3000 meter herkennen?'}])}).json()
                self.assertTrue(chatted['ok'])
                self.assertEqual(len(chatted['results'][0]['parts'][0]['watch_loads']),16)
                query['suggestion'] = '5x3000m'
                rejected = self.client.get(url, query).json()
                self.assertFalse(rejected['ok'])
                self.assertIn('No matching structure', rejected['message'])
            athlete_user = get_user_model().objects.create_user(username='Garmin_C_runner')
            self.client.force_login(athlete_user)
            rejected = self.client.get(url, query).json()
            self.assertEqual(rejected['message'], 'No matching structure could be confirmed.')
            query.pop('suggestion')
            result = self.client.get(url, query).json()['results'][0]['parts'][0]
            self.assertNotIn('ai_structure_reason', result)
            self.assertNotIn('ai_structure_model', result)
            other = Athlete.objects.create(owner=self.coach, name='Other runner', birth_year=2000, gender='X')
            query['athlete'] = other.pk
            self.assertEqual(self.client.get(url, query).status_code, 404)

    def test_mixed_timed_recording_exposes_time_option_without_ai_in_c_and_d(self):
        self.athlete.zone_speed_mps = {'1':4,'2':4.9,'3':5.5,'4':6,'5':6.5,'6':7}
        self.athlete.save(update_fields=['zone_speed_mps'])
        values = [(1005.4,301),(1001.21,286),(946.95,13681),(1008.92,215),
                  (996.954,211),(272.28,56),(126.39,91),(2347.52,481),
                  (152.97,93),(1192.51,253),(236.771,222),(1175.82,240),
                  (162.26,61),(1167.32,241),(46.8906,61),(1172.89,242),
                  (432.01,301),(1106.27,437)]
        GarminActivitySummary.objects.create(athlete=self.athlete, activity_id='mixed-timed',
            activity_start=datetime.fromtimestamp(self.start, dt_timezone.utc), activity_date='2026-10-31',
            distance_m=14550.3, analysis_data={'laps':[{'distance':m,'elapsed_time':s} for m,s in values]})
        self.client.force_login(self.coach)
        with patch('core.views.polar_raw.urlopen',side_effect=AssertionError('No AI consent')):
            for route in ['garmin_type_c_ayc','garmin_type_d_ayc']:
                response = self.client.get(reverse(route), {'athlete':self.athlete.pk,'date':'2026-10-31'})
                self.assertEqual(response.status_code,200)
                part = response.json()['results'][0]['parts'][0]
                self.assertEqual([a['label'] for a in part['training_alternatives']],['Distance','Time'])
                time_fields = part['training_alternatives'][1]['training_fields']
                self.assertEqual(time_fields['main'],"2×8' Z2 p91 + 4×4' Z2 p61")
                self.assertEqual(time_fields['wu'],'2000 m Z1')
                self.assertEqual(time_fields['cd'],'1100 m Z1')
                self.assertEqual([(l['meters'],l['seconds']) for l in part['watch_loads']],values)

    def test_timed_repetitions_with_distinct_finish_in_preview_and_chat(self):
        from types import SimpleNamespace
        from urllib.parse import urlencode
        from core.views.calendar import _virtual_segment_from_text
        from core.watch_processing import processed_main_reps

        values = [(1753.7,479),(89.7101,61),(1778.25,480),(68.7002,61),
                  (1748.64,481),(93.7402,61),(2117.09,589)]
        GarminActivitySummary.objects.create(athlete=self.athlete,activity_id='time-with-finish',
            activity_start=datetime.fromtimestamp(self.start, dt_timezone.utc),activity_date='2026-10-31',
            distance_m=sum(m for m,_ in values),duration_s=sum(s for _,s in values),
            analysis_data={'laps':[dict(distance=m,elapsed_time=s) for m,s in values]})
        self.client.force_login(self.coach)
        timed = "3×8' Z1 p61 + 1×10' Z1"
        distance = "3×8' Z1 p61 + 1×2100 m Z1"
        with patch('core.views.polar_raw.lap_zone_paces',return_value=('Z1','NA')), patch(
                'core.views.polar_raw.urlopen',side_effect=AssertionError('Measured recognition')):
            for model in ('c','d'):
                url = reverse(f'garmin_type_{model}_ayc')
                query = {'athlete':self.athlete.pk,'date':'2026-10-31','preview':'measured'}
                result = self.client.get(url,query).json()['results'][0]
                self.assertEqual(result['parts'][0]['training_fields']['main'],timed)
                chat_url = url + '?' + urlencode({**query,'suggestion_session':result['start']})
                for message, expected in (("3*8' z1//1*10' z1",timed),("3*8' z1 // 2100m",distance)):
                    chat = self.client.post(chat_url,{'chat':json.dumps([{'role':'user','content':message}])}).json()
                    self.assertTrue(chat['ok'],chat)
                    part = chat['results'][0]['parts'][0]
                    self.assertEqual(part['training_fields']['main'],expected)
                    self.assertEqual([(l['meters'],l['seconds']) for l in part['watch_loads']],values)
                    slot = SimpleNamespace(source=f'watch_{model}',watch_loads=part['watch_loads'],
                        segments=SimpleNamespace(all=lambda:[_virtual_segment_from_text('CORE',expected)]))
                    self.assertEqual([row['measured_seconds'] for row in processed_main_reps(slot)],[479,480,481,589])
                for message in ("4*8' z1","3*8' z1 // 1*8' z1","3*8' z1 // 3000m"):
                    rejected = self.client.post(chat_url,{'chat':json.dumps([{'role':'user','content':message}])}).json()
                    self.assertFalse(rejected['ok'])

    def test_chat_confirms_exact_four_by_eight_minutes_without_ai(self):
        values = [(1779.24,480),(84.0601,62),(1781.23,481),(80.46,60),
                  (1736.48,480),(73.1997,61),(1774.31,481)]
        self.athlete.zone_speed_mps = {'1':4,'2':4.9,'3':5.5,'4':6,'5':6.5,'6':7}
        self.athlete.save()
        GarminActivitySummary.objects.create(athlete=self.athlete,activity_id='four-by-eight',
            activity_start=datetime.fromtimestamp(self.start,dt_timezone.utc),activity_date='2026-10-31',
            distance_m=sum(m for m,_ in values),duration_s=sum(s for _,s in values),
            analysis_data={'laps':[{'distance':m,'elapsed_time':s} for m,s in values]})
        self.client.force_login(self.coach)
        with patch('core.views.polar_raw.urlopen',side_effect=AssertionError('Exact timed request needs no AI')):
            for route in ('garmin_type_c_ayc','garmin_type_d_ayc'):
                url=reverse(route)
                initial=self.client.get(url,{'athlete':self.athlete.pk,'date':'2026-10-31',
                    'preview':'measured'}).json()['results'][0]
                response=self.client.post(url+'?'+__import__('urllib.parse',fromlist=['urlencode']).urlencode({
                    'athlete':self.athlete.pk,'date':'2026-10-31','suggestion_session':initial['start']}),
                    {'chat':json.dumps([{'role':'user','content':"4*8'"}])})
                self.assertEqual(response.status_code,200)
                part=response.json()['results'][0]['parts'][0]
                self.assertEqual(part['training_fields']['main'],"4×8' Z1 p61")
                self.assertEqual([option['label'] for option in part['training_alternatives']],['Time'])
                self.assertEqual(part['ai_structure_status'],'measured_structure')
                self.assertIn('confirm',part['chat_reply'])

    def test_calendar_loads_combiner_without_oura_import(self):
        self.client.force_login(self.coach)
        response = self.client.get(reverse("athlete_year_calendar"), {"athlete": self.athlete.pk, "year": 2026})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context["show_oura_vitals_import"])
        self.assertContains(response, 'root.combineGarminActivities = combine;')
        self.assertNotContains(response, 'src="/static/core/garmin_combine.js"')
        # Execute the delivered function, rather than only checking a script URL.
        import subprocess
        script = response.content.decode().split('/* Compose already analysed recordings', 1)[1].split('  function renderTypeAResults', 1)[0]
        script = '/* Compose already analysed recordings' + script
        check = subprocess.run(['node', '-e', 'global.window = {};\n' + script + '\nif (typeof window.combineGarminActivities !== "function") process.exit(1);'],
            capture_output=True, text=True, timeout=10)
        self.assertEqual(check.returncode, 0, check.stderr)

    def test_long_work_before_short_reps_is_retained_and_boundaries_are_measured(self):
        from core.models import GarminActivity
        values = [(5521, 1785), (44, 680), (2420, 1083), (180, 1156),
                  (50, 9), (87, 98), (150, 28), (170, 120), (1842, 925)]
        GarminActivity.objects.create(athlete=self.athlete,
            activity_start=datetime.fromtimestamp(self.start, dt_timezone.utc), original_filename="anonymous.fit",
            file_hash="x" * 64, raw_file=b"", parsed_data={
                "total_distance_m": sum(m for m, _ in values), "total_elapsed_s": sum(s for _, s in values),
                "laps": [{"distance": m, "elapsed_time": seconds} for m, seconds in values]})
        fields = {"wu": "5500 m Z1", "main": "4×50 m Z5 p99 + 12×150 m Z4>Z5 p168", "cd": "1850 m Z1"}
        translated = [{"parts": [{"training_fields": fields, "description": "WU: 5500 m Z1 · Main: " + fields["main"] + " · CD: 1850 m Z1"}]}]
        with patch("core.views.polar_raw.translate_model_b", return_value=translated):
            response = self.read_c()
        self.assertEqual(response.status_code, 200)
        part = response.json()["results"][0]["parts"][0]
        self.assertIn("2400 m Z1", part["training_fields"]["main"])
        self.assertEqual(part["watch_loads"][0]["segment"], "WU")
        self.assertEqual(part["watch_loads"][-1]["segment"], "CD")
        self.assertEqual(part["watch_loads"][2]["segment"], "CORE")
        self.assertEqual(sum(load["meters"] for load in part["watch_loads"]), sum(m for m, _ in values))

    def test_watch_walking_is_excluded_from_weekly_running_totals(self):
        from core.models import TrainingPlan, TrainingSlot
        from core.stats import athlete_week_stats
        from django.core.cache import cache
        plan = TrainingPlan.objects.create(owner=self.coach, name="Walking threshold")
        day = datetime.fromtimestamp(self.start, dt_timezone.utc).date()
        loads = [{"segment": "CORE", "zone": zone, "meters": meters, "seconds": seconds}
                 for zone, meters, seconds in [("1",1000,600),("1",200,121),("2",1000,300),("5",200,200)]]
        slot = TrainingSlot.objects.create(plan=plan, athlete=self.athlete, date=day, slot_index=1,
                                          source="watch_c", watch_loads=loads)
        slot.segments.create(type="CORE", text="5000 m Z1", distance_m=5000, zone="1")
        cache.clear()
        result = athlete_week_stats(plan, self.athlete, day)
        self.assertEqual(result["zones"]["1"]["distance_m"], 1000)
        self.assertEqual(result["zones"]["1"]["duration_s"], 600)
        self.assertEqual(result["zones"]["2"]["distance_m"], 1000)
        self.assertEqual(result["zones"]["5"]["distance_m"], 0)
        slot.watch_loads = [loads[1]]
        slot.save(update_fields=["watch_loads"])
        cache.clear()
        result = athlete_week_stats(plan, self.athlete, day)
        self.assertEqual(sum(zone["distance_m"] for zone in result["zones"].values()), 0)
        slot.refresh_from_db()
        self.assertEqual(slot.watch_loads, [loads[1]])

    def test_garmin_d_has_same_access_as_c_and_separate_model(self):
        self.assertEqual(self.send({"activityDetails":[self.details()]}).status_code,200)
        self.client.force_login(self.coach)
        response = self.client.get(reverse("garmin_type_d_ayc"), {"athlete":self.athlete.pk,"date":"2026-10-31"})
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.json()["model"],"D")
        self.assertIn("analysis_note",response.json()["results"][0]["parts"][0])
        other = get_user_model().objects.create_user(username="other-d-coach",is_staff=True)
        self.client.force_login(other)
        response = self.client.get(reverse("garmin_type_d_ayc"), {"athlete":self.athlete.pk,"date":"2026-10-31"})
        self.assertEqual(response.status_code,404)

    def send(self, payload):
        return self.client.post(self.push_url, json.dumps(payload), content_type="application/json")

    def read_c(self, **query):
        self.client.force_login(self.coach)
        return self.client.get(reverse("garmin_type_c_ayc"), {"athlete": self.athlete.pk, "date": "2026-10-31", **query})

    def details(self):
        return {"userId": "runner-id", "activityId": 456, "summaryId": "summary-456-detail",
            "summary": self.summary,
            "samples": [{"startTimeInSeconds": self.start + t, "totalDistanceInMeters": meters,
                "heartRate": hr, "latitudeInDegree": 52.0} for t, meters, hr in (
                    (0, 0, 100), (100, 400, 140), (150, 500, 150), (200, 600, 160), (290, 980, 170), (300, 1000, 170))],
            "laps": [{"startTimeInSeconds": self.start}, {"startTimeInSeconds": self.start + 150}]}

    @patch("core.views.polar_raw.translate_model_b", return_value=[])
    def test_timer_pause_facts_survive_push_and_reach_recognition(self, translate):
        details = self.details()
        for sample, timer in zip(details["samples"], (0, 100, 120, 170, 260, 270)):
            sample["clockDurationInSeconds"] = sample["startTimeInSeconds"] - self.start
            sample["timerDurationInSeconds"] = timer
            sample["movingDurationInSeconds"] = timer
        self.assertEqual(self.send({"activityDetails": [details]}).status_code, 200)
        saved = GarminActivitySummary.objects.get().analysis_data
        self.assertEqual(saved["laps"][0]["timer_time"], 120)
        self.assertEqual(saved["laps"][0]["paused_time"], 30)
        self.assertEqual(saved["laps"][1]["paused_time"], 0)
        self.assertNotIn("latitudeInDegree", json.dumps(saved))
        self.read_c()
        laps = translate.call_args.args[0][0]["laps"]["laps"]
        self.assertEqual(laps[0]["pausedDurationMillis"], 30000)
        self.assertEqual(laps[0]["timerDurationMillis"], 120000)

    @patch('core.views.polar_raw._model_b_ai_description',return_value='')
    def test_uploaded_fit_uses_fit_consent_in_both_previews(self, ai):
        from core.models import GarminActivity
        from core.views.garmin import CONSENT_VERSION
        GarminActivity.objects.create(athlete=self.athlete,original_filename='coros.fit',
            file_hash='coros-ai',activity_start=datetime.fromtimestamp(self.start,dt_timezone.utc),
            parsed_data={'total_distance_m':1000,'total_elapsed_s':300,
                'laps':[{'distance':1000,'elapsed_time':300}]})
        for enabled in (False,True):
            self.athlete.garmin_fit_upload_enabled = True
            self.athlete.fit_ai_consent_at = timezone.now() if enabled else None
            self.athlete.fit_ai_consent_version = CONSENT_VERSION
            self.athlete.save()
            ai.reset_mock()
            for route in ('garmin_type_c_ayc','garmin_type_d_ayc'):
                self.client.force_login(self.coach)
                self.assertEqual(self.client.get(reverse(route),{'athlete':self.athlete.pk,'date':'2026-10-31'}).status_code,200)
            self.assertEqual(ai.call_count,2 if enabled else 0)

    def test_low_confidence_ai_is_optional_in_c_and_d_preview(self):
        from core.models import GarminActivity
        from core.views.garmin import CONSENT_VERSION
        from core.watch_ai_structure import validate_lap_structure
        values=[(1000,300),(400,80),(100,60),(400,80),(100,60),(400,80),(100,60),(400,80),(1000,300)]
        facts=[dict(lap=i,distance_m=m,duration_s=t,zone='Z2' if i in (2,4,6,8) else 'Z1') for i,(m,t) in enumerate(values,1)]
        structure=validate_lap_structure({'confidence':.7,'lap_structure':dict(warmup_laps=[1],cooldown_laps=[9],
            recovery_laps=[3,5,7],stop_laps=[],groups=[dict(target_meters=400,reps=[[2],[4],[6],[8]])])},facts,minimum_confidence=.5)
        self.assertIsNotNone(structure)
        self.athlete.garmin_fit_upload_enabled=True
        self.athlete.fit_ai_consent_at=timezone.now()
        self.athlete.fit_ai_consent_version=CONSENT_VERSION
        self.athlete.save()
        GarminActivity.objects.create(athlete=self.athlete,original_filename='review.fit',file_hash='review',
            activity_start=datetime.fromtimestamp(self.start,dt_timezone.utc),parsed_data={'laps':[
                dict(distance=m,elapsed_time=t) for m,t in values]})
        def ai(*args,diagnostics,**kwargs):
            diagnostics.update(status='review_available',review_structure=structure)
            return ''
        with patch('core.views.polar_raw._model_b_ai_description',side_effect=ai):
            for route in ('garmin_type_c_ayc','garmin_type_d_ayc'):
                self.client.force_login(self.coach)
                part=self.client.get(reverse(route),{'athlete':self.athlete.pk,'date':'2026-10-31'}).json()['results'][0]['parts'][0]
                options=part['training_alternatives']
                self.assertFalse(options[0].get('requires_review',False))
                self.assertTrue(options[-1]['requires_review'])
                self.assertEqual(options[-1]['training_fields']['main'],'4×400 m Z2 p60')
                self.assertEqual(part['training_fields'],options[0]['training_fields'])
                self.assertNotIn('review_lap_structure',part)

    def test_ai_split_kilometre_distance_group_survives_c_and_d_preview(self):
        from copy import deepcopy
        from unittest.mock import MagicMock
        from core.tests_watch_ai_structure import split_distance_example
        from core.views.garmin import CONSENT_VERSION
        from core.watch_processing import processed_main_reps
        from core.views.calendar import _virtual_segment_from_text
        from types import SimpleNamespace
        facts,proposal=split_distance_example()
        GarminActivitySummary.objects.create(athlete=self.athlete,activity_id='split-distance',
            activity_start=datetime.fromtimestamp(self.start,dt_timezone.utc),activity_date='2026-10-31',
            distance_m=sum(f['distance_m'] for f in facts),duration_s=sum(f['duration_s'] for f in facts),
            analysis_data={'laps':[dict(distance=f['distance_m'],elapsed_time=f['duration_s']) for f in facts]})
        self.client.force_login(self.coach)
        from django.core.cache import cache
        cache.clear()
        self.addCleanup(cache.clear)
        for consent,confidence in ((True,.96),(True,.68),(False,.96)):
            cache.clear()
            self.athlete.garmin_ai_consent_at=timezone.now() if consent else None
            self.athlete.garmin_ai_consent_version=CONSENT_VERSION
            self.athlete.save()
            answer=deepcopy(proposal);answer['confidence']=confidence
            response=MagicMock()
            response.__enter__.return_value.read.return_value=json.dumps(
                {'choices':[{'message':{'content':json.dumps(answer)}}]}).encode()
            with patch.dict('os.environ',{'OPENAI_API_KEY':'test'}), patch('core.views.polar_raw.urlopen',return_value=response) as ai, patch(
                    'core.views.polar_raw.lap_zone_paces',side_effect=lambda m,t,a: ('Z1' if m<500 else 'Z2','NA')):
                for route in ('garmin_type_c_ayc','garmin_type_d_ayc'):
                    ai.reset_mock()
                    quick=self.client.get(reverse(route),{'athlete':self.athlete.pk,'date':'2026-10-31','preview':'measured'})
                    self.assertEqual(quick.status_code,200)
                    self.assertEqual(ai.call_count,0)
                    quick_part=quick.json()['results'][0]['parts'][0]
                    self.assertEqual(len(quick_part['manual']),16)
                    self.assertEqual(quick_part['ai_structure_status'],'pending' if consent else 'consent_required')
                    result=self.client.get(reverse(route),{'athlete':self.athlete.pk,'date':'2026-10-31'})
                    self.assertEqual(result.status_code,200)
                    part=result.json()['results'][0]['parts'][0]
                    self.assertEqual(len(part['manual']),16)
                    if not consent:
                        self.assertEqual(ai.call_count,0)
                        self.assertNotIn('4×3000',part['training_fields']['main'])
                        continue
                    self.assertEqual(ai.call_count, (1 if route == 'garmin_type_c_ayc' else 0) if confidence>=.75 else 2)
                    if confidence>=.75:
                        self.assertEqual(part['ai_structure_status'],'applied')
                        selected=part
                    else:
                        self.assertEqual(part['ai_structure_status'],'review_available')
                        self.assertNotIn('4×3000',part['training_fields']['main'])
                        selected=part['training_alternatives'][-1]
                        self.assertTrue(selected['requires_review'])
                    self.assertEqual(selected['training_fields']['main'],'4×3000 m Z2 p119')
                    slot=SimpleNamespace(source='watch_c',watch_loads=selected['watch_loads'],segments=SimpleNamespace(
                        all=lambda:[_virtual_segment_from_text('CORE',selected['training_fields']['main'])]))
                    reps=processed_main_reps(slot)
                    self.assertEqual([r['measured_seconds'] for r in reps],[593,586,592,589])
                    self.assertEqual(sum(l['meters'] for l in selected['watch_loads']),sum(f['distance_m'] for f in facts))

    def test_distance_free_activity_preserves_sport_and_heart_rate_in_c_and_d(self):
        details=self.details()
        details['summary']=dict(self.summary,activityType='ELLIPTICAL_FITNESS',
            averageHeartRateInBeatsPerMinute=142,maxHeartRateInBeatsPerMinute=170,activeKilocalories=450)
        details['summary'].pop('distanceInMeters')
        self.send({'activityDetails':[details]})
        saved=GarminActivitySummary.objects.get().analysis_data
        self.assertTrue(saved['heart_rate_samples'])
        self.assertEqual([lap['elapsed_time'] for lap in saved['laps']],[150,150])
        self.assertTrue(all(lap['distance'] is None for lap in saved['laps']))
        self.assertEqual(saved['lap_data_status'],'available_time_only')
        self.assertNotIn('latitudeInDegree',json.dumps(saved))
        for route in ('garmin_type_c_ayc','garmin_type_d_ayc'):
            self.client.force_login(self.coach)
            item=self.client.get(reverse(route),{'athlete':self.athlete.pk,'date':'2026-10-31'}).json()['results'][0]
            self.assertEqual(item['distance'],'NA')
            self.assertEqual(item['activity_metrics']['sport'],'ELLIPTICAL_FITNESS')
            self.assertEqual(item['activity_metrics']['average_hr'],142)
            self.assertEqual(item['activity_metrics']['max_hr'],170)
            self.assertEqual(item['activity_metrics']['active_kcal'],450)
            self.assertEqual(item['activity_metrics']['heart_rate_sample_count'],6)
            self.assertEqual([row['duration'] for row in item['parts'][0]['manual']],
                             ['00:02:30.000','00:02:30.000'])
            self.assertNotIn('watch_loads',item['parts'][0])
        from core.garmin_details import lap_data
        details['summary'].pop('averageHeartRateInBeatsPerMinute')
        details['summary'].pop('maxHeartRateInBeatsPerMinute')
        metrics=lap_data(details)['activity_metrics']
        self.assertIn('sample_average_hr',metrics)
        self.assertNotIn('average_hr',metrics)
        self.assertEqual(metrics['sample_max_hr'],170)

    def test_distance_free_elliptical_keeps_and_recognizes_six_by_eight_laps(self):
        durations = [600,480,180,481,179,479,181,480,180,481,180,479,600]
        starts, elapsed = [], 0
        for seconds in durations:
            starts.append(self.start + elapsed)
            elapsed += seconds
        details = {'userId':'runner-id','activityId':999,'summaryId':'elliptical-laps',
            'summary':dict(self.summary,activityId=999,activityType='ELLIPTICAL',
                durationInSeconds=elapsed,averageHeartRateInBeatsPerMinute=132),
            'laps':[{'startTimeInSeconds':timestamp} for timestamp in starts],
            'samples':[{'startTimeInSeconds':self.start+second,'heartRate':145 if index%2==0 else 110}
                       for index,(start,seconds) in enumerate(zip(starts,durations))
                       for second in range(start-self.start,start-self.start+seconds,30)]}
        details['summary'].pop('distanceInMeters')
        self.assertEqual(self.send({'activityDetails':[details]}).status_code,200)
        saved=GarminActivitySummary.objects.get(activity_id='999').analysis_data
        self.assertEqual([lap['elapsed_time'] for lap in saved['laps']],durations)
        self.assertTrue(all(lap['distance'] is None for lap in saved['laps']))
        for route in ('garmin_type_c_ayc','garmin_type_d_ayc'):
            self.client.force_login(self.coach)
            part=self.client.get(reverse(route),{'athlete':self.athlete.pk,'date':'2026-10-31'}).json()['results'][0]['parts'][0]
            self.assertEqual(part['training_fields'],{'alt':"Elliptical 6×8' p180"})
            self.assertEqual(len(part['manual']),13)
            self.assertEqual(part['manual'][0]['duration'],'00:10:00.000')
            self.assertEqual(part['manual'][1]['duration'],'00:08:00.000')
            self.assertEqual(part['manual'][2]['duration'],'00:03:00.000')
            self.assertEqual(part['manual'][0]['distance'],'NA')

    def test_non_running_previews_use_average_hr_plus_ten_in_both_models(self):
        self.athlete.zone_hr_bpm = {'1':'151','2':'152-168','3':'169-178','4':'179-184','5':'185-200'}
        self.athlete.save(update_fields=['zone_hr_bpm'])
        examples = [('PILATES', 2771, 80, "Pilates 46' Z1"),
                    ('ELLIPTICAL', 5408, 143, "Elliptical 90' Z2"),
                    ('ELLIPTICAL', 5945, 134, "Elliptical 99' Z1"),
                    ('CYCLING', 300, 160, "Cycling 5' Z3")]
        for index,(sport,seconds,hr,expected) in enumerate(examples):
            details = self.details()
            details['activityId'] = index + 100
            details['summary'] = dict(self.summary, activityId=index+100, activityType=sport,
                durationInSeconds=seconds, averageHeartRateInBeatsPerMinute=hr)
            if sport != 'CYCLING':
                details['summary'].pop('distanceInMeters')
            self.assertEqual(self.send({'activityDetails':[details]}).status_code,200)
        self.client.force_login(self.coach)
        with patch('core.views.polar_raw.translate_model_b', side_effect=AssertionError('Non-running needs no running AI')):
            for route in ('garmin_type_c_ayc','garmin_type_d_ayc'):
                results=self.client.get(reverse(route),{'athlete':self.athlete.pk,'date':'2026-10-31'}).json()['results']
                self.assertEqual(len(results),len(examples))
                for result,(_,_,hr,expected) in zip(results,examples):
                    part=result['parts'][0]
                    self.assertEqual(part['description'],expected)
                    self.assertEqual(part['training_fields'],{'alt':expected})
                    self.assertIn(f'+ 10 = {hr+10} bpm',part['analysis_note'])
                    self.assertNotIn('watch_loads',part)
                    self.assertEqual(len(part['manual']),2)
        cycling=GarminActivitySummary.objects.get(activity_id='103')
        self.assertEqual(cycling.analysis_data['activity_metrics']['sport'],'CYCLING')
        self.assertTrue(cycling.analysis_data['laps'])

        self.athlete.alternative_hr_correction = 0
        self.athlete.save(update_fields=['alternative_hr_correction'])
        expected_without_correction = ["Pilates 46' Z1", "Elliptical 90' Z1",
                                       "Elliptical 99' Z1", "Cycling 5' Z2"]
        for route in ('garmin_type_c_ayc','garmin_type_d_ayc'):
            results=self.client.get(reverse(route),{'athlete':self.athlete.pk,'date':'2026-10-31'}).json()['results']
            self.assertEqual([result['parts'][0]['description'] for result in results],expected_without_correction)
            for result,(_,_,hr,_) in zip(results,examples):
                self.assertIn(f'+ 0 = {hr} bpm',result['parts'][0]['analysis_note'])

    def test_recognized_alternative_intervals_use_work_lap_hr_for_zone(self):
        from core.watch_alternative import alternative_part

        self.athlete.zone_hr_bpm = {'1':'145','2':'146-163','3':'164-172','4':'173-180','5':'181'}
        self.athlete.alternative_hr_correction = 0
        laps = [{'elapsed_time': 1020, 'avg_heart_rate': 111}]
        for index in range(16):
            laps.append({'elapsed_time': 180, 'avg_heart_rate': 151,
                         'hr_tail': 150 if index < 8 else 168})
            laps.append({'elapsed_time': 45, 'avg_heart_rate': 130})
        laps.append({'elapsed_time': 600, 'avg_heart_rate': 115})

        part = alternative_part(
            self.athlete,
            {'sport':'ELLIPTICAL', 'average_hr':138},
            sum(lap['elapsed_time'] for lap in laps),
            laps,
        )

        self.assertEqual(part['description'], "Elliptical 16×3' p45 Z2>Z3")
        self.assertIn('Work-lap end HR zones with +0 correction: Z2>Z3', part['analysis_note'])

    def test_non_running_missing_hr_or_limits_never_invents_a_zone(self):
        from core.watch_alternative import alternative_part
        self.athlete.zone_hr_bpm={'1':'151','2':'152-168'}
        missing=alternative_part(self.athlete,{'sport':'PILATES'},2771)
        self.assertEqual(missing['description'],"Pilates 46'")
        self.assertEqual(missing['training_fields'],{'alt':"Pilates 46'"})
        for value in (None, 0, float('nan'), True, 999):
            metrics={'sport':'ELLIPTICAL','average_hr':value}
            self.assertEqual(alternative_part(self.athlete,metrics,5408)['training_fields'],
                             {'alt':"Elliptical 90'"})
        self.athlete.zone_hr_bpm={}
        self.assertEqual(alternative_part(self.athlete,{'sport':'ELLIPTICAL','average_hr':143},5408)['training_fields'],
                         {'alt':"Elliptical 90'"})
        self.athlete.zone_hr_bpm={'1':'151','2':'152-168'}
        sampled=alternative_part(self.athlete,{'sport':'ELLIPTICAL','sample_average_hr':143},5408)
        self.assertEqual(sampled['training_fields'],{'alt':"Elliptical 90' Z2"})
        for sport in ('RUNNING','TRAIL_RUNNING','TREADMILL_RUNNING','VIRTUAL_RUN','UNKNOWN','MULTISPORT',None):
            self.assertIsNone(alternative_part(self.athlete,{'sport':sport,'average_hr':143},5408))

    def test_z1_run_includes_partial_lap_as_one_block_with_or_without_ai(self):
        from core.views.garmin import CONSENT_VERSION
        self.athlete.zone_speed_mps={'1':4,'2':4.8,'3':5.3,'4':5.6,'5':6,'6':7}
        values=[(1005.56,312),(1000.39,285),(234.197,65)]
        GarminActivitySummary.objects.create(athlete=self.athlete,activity_id='easy-splits',
            activity_start=datetime.fromtimestamp(self.start,dt_timezone.utc),activity_date='2026-10-31',
            distance_m=sum(m for m,t in values),duration_s=662,
            analysis_data={'total_distance_m':sum(m for m,t in values),'total_elapsed_s':702,
                'total_timer_s':662,'laps':[dict(distance=m,elapsed_time=t+(20 if i<2 else 0),timer_time=t)
                    for i,(m,t) in enumerate(values)]})
        for consent in (False,True):
            self.athlete.garmin_ai_consent_at=timezone.now() if consent else None
            self.athlete.garmin_ai_consent_version=CONSENT_VERSION
            self.athlete.save()
            for route in ('garmin_type_c_ayc','garmin_type_d_ayc'):
                self.client.force_login(self.coach)
                with patch('core.views.polar_raw.urlopen',side_effect=AssertionError('No AI needed for clear Z1 splits')):
                    part=self.client.get(reverse(route),{'athlete':self.athlete.pk,'date':'2026-10-31'}).json()['results'][0]['parts'][0]
                self.assertEqual(part['training_fields']['main'],'2250 m Z1')
                self.assertAlmostEqual(sum(l['meters'] for l in part['watch_loads']),2240.147)
                self.assertEqual([l['seconds'] for l in part['watch_loads']],[312,285,65])

    def test_timer_duration_matches_garmin_for_new_and_existing_single_lap(self):
        details = self.details()
        details['summary'] = dict(self.summary,distanceInMeters=17336,durationInSeconds=4503)
        details['laps'] = [{'startTimeInSeconds':self.start}]
        details['samples'] = [dict(startTimeInSeconds=self.start+t,totalDistanceInMeters=m,heartRate=hr)
                              for t,m,hr in [(0,0,100),(4500,17320,150),(4670,17334,155),(4676,17336,155)]]
        self.send({'activityDetails':[details]})
        stored = GarminActivitySummary.objects.get()
        self.assertEqual(stored.analysis_data['total_elapsed_s'],4676)
        self.assertEqual(stored.analysis_data['total_timer_s'],4503)
        for old in (False,True):
            if old:
                parsed = stored.analysis_data
                parsed.pop('total_timer_s')
                parsed['laps'][0].pop('timer_time')
                stored.analysis_data = parsed
                stored.save(update_fields=['analysis_data'])
            for route in ('garmin_type_c_ayc','garmin_type_d_ayc'):
                self.client.force_login(self.coach)
                response = self.client.get(reverse(route),{'athlete':self.athlete.pk,'date':'2026-10-31'})
                result = response.json()['results'][0]
                self.assertEqual(result['duration'],'01:15:03.000')
                row = result['parts'][0]['manual'][0]
                self.assertEqual(row['duration'],'01:15:03.000')
                self.assertEqual(row['pace'],'4:20')
                load = result['parts'][0]['watch_loads'][0]
                self.assertEqual(load['seconds'],4503)
                self.assertEqual(load['elapsed_seconds'],4676)
                self.assertGreater(load['hr_samples'][-1][0],4503)
        stored.refresh_from_db()
        self.assertEqual(stored.analysis_data['laps'][0]['elapsed_time'],4676)

    def test_unknown_or_reset_timer_is_not_reported_as_zero_pause(self):
        for reset in (False, True):
            details = self.details()
            if reset:
                for sample, timer in zip(details["samples"], (0, 100, 20, 70, 160, 170)):
                    sample["timerDurationInSeconds"] = timer
            self.send({"activityDetails": [details]})
            for lap in GarminActivitySummary.objects.get().analysis_data["laps"]:
                self.assertNotIn("paused_time", lap)

    @patch("core.views.polar_raw.lap_zone_paces", return_value=("Z1", "NA"))
    def test_long_run_with_two_slow_kilometres_is_one_block_in_garmin_c(self, zones):
        laps = [{"distance": 1000, "elapsed_time": 600 if index in (9, 18) else 260} for index in range(27)]
        laps.append({"distance": 300, "elapsed_time": 80})
        GarminActivitySummary.objects.create(athlete=self.athlete, activity_id="long-run",
            activity_start=datetime.fromtimestamp(self.start, dt_timezone.utc), activity_date="2026-10-31",
            distance_m=27300, analysis_data={"laps": laps})
        result = self.read_c().json()["results"][0]["parts"][0]
        self.assertEqual(result["training_fields"]["main"], "27300 m Z1")
        self.assertEqual(len(result["manual"]), 28)

    @patch("core.views.polar_raw._model_b_ai_description")
    def test_old_received_summary_is_visible_without_invented_laps_or_use_actions(self, ai):
        GarminActivitySummary.objects.create(athlete=self.athlete, activity_id="short-test",
            activity_start=datetime.fromtimestamp(self.start, dt_timezone.utc), activity_date="2026-10-31", distance_m=60)
        data = self.read_c().json()
        self.assertTrue(data["ok"])
        self.assertEqual(data["results"][0]["distance"], "60")
        self.assertEqual(data["results"][0]["parts"][0]["manual"], [])
        self.assertNotIn("training_fields", data["results"][0]["parts"][0])
        ai.assert_not_called()

    @patch("core.views.polar_raw._model_b_ai_description")
    def test_detail_push_flows_into_garmin_c_measured_laps_and_hr(self, ai):
        self.assertEqual(self.send({"activityDetails": [self.details()]}).status_code, 200)
        saved = GarminActivitySummary.objects.get()
        self.assertEqual(saved.duration_s, 300)
        self.assertEqual([lap["distance"] for lap in saved.analysis_data["laps"]], [500, 500])
        self.assertNotIn("latitudeInDegree", json.dumps(saved.analysis_data))
        data = self.read_c().json()
        self.assertTrue(data["ok"])
        self.assertEqual(len(data["results"]), 1)
        self.assertEqual(len(data["results"][0]["parts"][0]["manual"]), 2)
        self.assertEqual(data["results"][0]["parts"][0]["manual"][0]["distance"], "500")
        self.assertEqual(data["results"][0]["parts"][0]["watch_loads"][1]["average_hr_last_15"], 170)
        self.assertEqual(data["results"][0]["parts"][0]["watch_loads"][1]["average_hr"], 160)
        self.assertNotIn("average_hr_last_15", data["results"][0]["parts"][0]["watch_loads"][0])
        ai.assert_not_called()  # Data consent alone never enables OpenAI.

    def test_summary_retry_does_not_erase_already_received_lap_details(self):
        self.send({"activityDetails": [self.details()]})
        before = GarminActivitySummary.objects.get().analysis_data
        self.send({"activities": [self.summary]})
        self.send({"activityDetails": [self.details()]})
        self.assertEqual(GarminActivitySummary.objects.count(), 1)
        self.assertEqual(GarminActivitySummary.objects.get().analysis_data["laps"], before["laps"])

    @patch("core.views.polar_raw.lap_zone_paces", return_value=("Z2", "NA"))
    def test_short_sets_continuous_block_and_cooldown_reach_c_with_measured_loads(self, zones):
        from core.tests_watch_structure import workout
        for cooldown in (False, True):
            rows = workout(cooldown)
            GarminActivitySummary.objects.update_or_create(athlete=self.athlete, activity_id="structure",
                defaults={"activity_start": datetime.fromtimestamp(self.start, dt_timezone.utc),
                    "activity_date": "2026-10-31", "distance_m": sum(row["distanceMeters"] for row in rows),
                    "analysis_data": {"laps": [{"distance": row["distanceMeters"],
                        "elapsed_time": row["durationMillis"] / 1000} for row in rows]}})
            part = self.read_c().json()["results"][0]["parts"][0]
            self.assertEqual(part["training_fields"]["main"], "2*(5*100m z2) p45//3750m z2")
            self.assertEqual(part["training_fields"]["cd"], "2000m" if cooldown else "")
            self.assertEqual(len(part["manual"]), len(rows))
            loads = part["watch_loads"]
            self.assertEqual(sum(load["meters"] for load in loads), sum(row["distanceMeters"] for row in rows))
            self.assertTrue(all(load["segment"] == "CORE" for load in loads[:26]))
            self.assertTrue(all(load["segment"] == "CD" for load in loads[26:]))

    def test_missing_sample_coverage_does_not_invent_intermediate_laps(self):
        details = self.details()
        details["samples"] = []
        self.assertEqual(self.send({"activityDetails": [details]}).status_code, 200)
        self.assertEqual(GarminActivitySummary.objects.get().analysis_data["laps"], [])

    def test_garmin_c_respects_day_and_athlete_access(self):
        self.send({"activityDetails": [self.details()]})
        self.assertEqual(self.read_c(date="2026-10-30").json()["results"], [])
        other = get_user_model().objects.create_user(username="other-c-coach", is_staff=True)
        self.client.force_login(other)
        response = self.client.get(reverse("garmin_type_c_ayc"), {"athlete": self.athlete.pk, "date": "2026-10-31"})
        self.assertEqual(response.status_code, 404)

    def test_invalid_details_do_not_save_partial_summary(self):
        details = self.details()
        details["summary"]["durationInSeconds"] = -1
        self.assertEqual(self.send({"activityDetails": [details]}).status_code, 400)
        self.assertFalse(GarminActivitySummary.objects.exists())

    @patch("core.views.polar_raw._model_b_ai_description")
    def test_uploaded_fit_still_works_and_is_not_duplicated_by_matching_push(self, ai):
        from core.models import GarminActivity
        self.send({"activities": [self.summary]})
        GarminActivity.objects.create(athlete=self.athlete,
            activity_start=datetime.fromtimestamp(self.start, dt_timezone.utc),
            original_filename="run.fit", file_hash="fit-test", raw_file=b"",
            parsed_data={"total_distance_m": 1000, "total_elapsed_s": 300,
                "laps": [{"distance": 500, "elapsed_time": 150}, {"distance": 500, "elapsed_time": 150}]})
        results = self.read_c().json()["results"]
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["name"], "run.fit")
        self.assertEqual(len(results[0]["parts"][0]["manual"]), 2)

    def test_details_without_laps_are_not_misreported_as_missing_delivery(self):
        details = self.details()
        details["laps"] = []
        self.send({"activityDetails": [details]})
        result = self.read_c().json()["results"][0]
        self.assertEqual(result["detail_status"], "details_without_usable_laps")
        description = result["parts"][0]["description"]
        self.assertIn("have been received", description)
        self.assertIn("no recorded lap boundaries", description)
        self.assertNotIn("enable Activity Details", description)
        self.assertIn("Last detail delivery:", description)

    def test_resend_replaces_summary_status_and_keeps_all_three_runs_in_time_order(self):
        first = {**self.summary, "activityId": 111, "startTimeInSeconds": self.start - 600}
        self.send({"activities": [first]})
        self.send({"activityDetails": [self.details()]})
        third = {**self.summary, "activityId": 999, "startTimeInSeconds": self.start + 600}
        self.send({"activities": [third]})
        results = self.read_c().json()["results"]
        self.assertEqual([r["name"] for r in results], ["Garmin activity 111", "Garmin activity 456", "Garmin activity 999"])
        self.assertEqual(results[0]["detail_status"], "summary_only")
        details = self.details()
        details["activityId"] = 111
        details["summary"] = {**self.summary, "startTimeInSeconds": self.start - 600}
        details["laps"] = []
        self.send({"activityDetails": [details]})
        results = self.read_c().json()["results"]
        self.assertEqual(len(results), 3)
        self.assertEqual(results[0]["detail_status"], "details_without_usable_laps")

    def test_rejected_detail_logs_safe_schema_not_personal_values(self):
        details = self.details()
        details["summary"].pop("durationInSeconds")
        details["summary"]["activityName"] = "PRIVATE TRAINING NAME"
        details["userAccessToken"] = "PRIVATE TOKEN"
        with self.assertLogs("core.views.garmin", level="WARNING") as logs:
            self.assertEqual(self.send({"activityDetails": [details]}).status_code, 400)
        output = " ".join(logs.output)
        self.assertIn("kind=activityDetails", output)
        self.assertIn("reason=Missing activity totals", output)
        self.assertIn("durationInSeconds=missing", output)
        for secret in ("PRIVATE TRAINING NAME", "PRIVATE TOKEN", "runner-id", receiver_key()):
            self.assertNotIn(secret, output)
        self.assertFalse(GarminActivitySummary.objects.exists())

    def test_detail_without_distance_does_not_block_other_activities_in_batch(self):
        from copy import deepcopy
        stationary = deepcopy(self.details())
        stationary["activityId"] = 111
        stationary["summary"].pop("distanceInMeters")
        response = self.send({"activityDetails": [stationary, self.details()]})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(GarminActivitySummary.objects.count(), 2)
        missing = GarminActivitySummary.objects.get(activity_id="111")
        self.assertIsNone(missing.distance_m)
        self.assertEqual(missing.analysis_data["lap_data_status"], "available_time_only")
        self.assertEqual([lap['elapsed_time'] for lap in missing.analysis_data["laps"]], [150,150])
        self.assertTrue(missing.analysis_data["details_received_at"])
        usable = GarminActivitySummary.objects.get(activity_id="456")
        self.assertEqual([lap["distance"] for lap in usable.analysis_data["laps"]], [500, 500])
        results = self.read_c().json()["results"]
        self.assertTrue(any("no total distance" in result["parts"][0]["description"] for result in results if result.get("detail_status")))

    def test_missing_distance_detail_preserves_existing_summary_distance(self):
        self.send({"activities": [self.summary]})
        details = self.details()
        details["summary"].pop("distanceInMeters")
        self.assertEqual(self.send({"activityDetails": [details]}).status_code, 200)
        saved = GarminActivitySummary.objects.get()
        self.assertEqual(saved.distance_m, 1000)
        self.assertEqual([lap['elapsed_time'] for lap in saved.analysis_data["laps"]], [150,150])

    def test_successful_details_receipt_reports_laps_with_private_reference(self):
        import hashlib
        with self.assertLogs("core.views.garmin", level="INFO") as logs:
            response = self.send({"activityDetails": [self.details()]})
        self.assertEqual(response.status_code, 200)
        output = " ".join(logs.output)
        self.assertIn("activity_ref=" + hashlib.sha256(b"456").hexdigest()[:12], output)
        self.assertIn("outcome=details_stored usable_laps=2 supplied_laps=2", output)
        self.assertNotIn("runner-id", output)
        self.assertNotIn("private-token", output)
        self.assertNotIn(receiver_key(), output)

    def test_all_z1_pace_recording_uses_hr_structure_in_complete_c_and_d_preview(self):
        from datetime import timedelta
        from core.tests_watch_hr_structure import HRDistanceStructureTests
        fixture=HRDistanceStructureTests();fixture.setUp()
        self.athlete.zone_hr_bpm=fixture.athlete.zone_hr_bpm
        self.athlete.save(update_fields=['zone_hr_bpm'])
        start=datetime.fromtimestamp(self.start,dt_timezone.utc)
        elapsed=0
        samples=[]
        laps=[]
        for load in fixture.loads:
            laps.append({'distance':load['meters'],'elapsed_time':load['seconds'],'avg_heart_rate':load['average_hr']})
            samples.append({'timestamp':(start+timedelta(seconds=elapsed+load['seconds']-1)).isoformat(),'heart_rate':load['average_hr']})
            elapsed+=load['seconds']
        GarminActivitySummary.objects.create(athlete=self.athlete,activity_id='hr-distance-recording',activity_start=start,
             activity_date='2026-10-31',distance_m=sum(l['meters'] for l in fixture.loads),
             analysis_data={'laps':laps,'heart_rate_samples':samples})
        self.client.force_login(self.coach)
        with patch('core.views.polar_raw.lap_zone_paces',return_value=('Z1','NA')), patch('core.views.polar_raw.urlopen',side_effect=AssertionError('No external AI')):
            for route,zone in [('garmin_type_c_ayc','Z1'),('garmin_type_d_ayc','Z3')]:
                response=self.client.get(reverse(route),{'athlete':self.athlete.pk,'date':'2026-10-31'})
                self.assertEqual(response.status_code,200)
                part=response.json()['results'][0]['parts'][0]
                self.assertEqual(part['training_fields']['main'],f'6×1000 m {zone} p356')
                self.assertEqual(part['training_fields']['cd'],'1400 m Z1')
                self.assertEqual([i+1 for i,l in enumerate(part['watch_loads']) if l['work_rep']],[1,4,6,8,10,12])
                self.assertAlmostEqual(sum(l['meters'] for l in part['watch_loads']),sum(l['meters'] for l in fixture.loads))
