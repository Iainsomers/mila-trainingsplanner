from datetime import date, timedelta
from django.contrib.auth import get_user_model
from django.test import TestCase
from core.models import RaceEvent


class RaceListLayoutTests(TestCase):
    def setUp(self):
        self.coach = get_user_model().objects.create_user(username='race-columns', is_staff=True)
        self.client.force_login(self.coach)

    def test_balanced_columns_keep_chronological_order(self):
        for count, sizes in ((21, [7, 7, 7]), (22, [8, 7, 7]), (23, [8, 8, 7]), (2, [1, 1, 0])):
            with self.subTest(count=count):
                RaceEvent.objects.all().delete()
                races = [RaceEvent.objects.create(owner=self.coach, name=f'Race {i}', date=date(2026, 10, 1) + timedelta(days=i)) for i in range(count)]
                response = self.client.get('/race-calendar/?year=2026&view=year_list&period=season')
                self.assertEqual(response.status_code, 200)
                columns = response.context['race_columns']
                self.assertEqual([len(column) for column in columns], sizes)
                self.assertEqual([row['race'].id for column in columns for row in column], [race.id for race in races])
                self.assertContains(response, 'race-list-columns')

    def test_season_boundaries_and_save_redirect(self):
        for name, day in [('Before', date(2026, 9, 30)), ('Start', date(2026, 10, 1)), ('End', date(2027, 9, 30)), ('After', date(2027, 10, 1))]:
            RaceEvent.objects.create(owner=self.coach, name=name, date=day)
        response = self.client.get('/race-calendar/?year=2026&view=year_list&period=season')
        self.assertEqual([row['race'].name for row in response.context['race_rows']], ['Start', 'End'])
        self.assertEqual(len(response.context['month_rows']), 12)
        self.assertContains(response, '2026/27')
        response = self.client.post('/race-calendar/', {'year': '2026', 'view': 'year_list', 'period': 'season', 'name': 'New', 'date': '2027-05-01', 'race_type': 'race_other'})
        self.assertEqual(response.status_code, 302)
        self.assertIn('period=season', response.url)
        self.assertIn('year=2026', response.url)
