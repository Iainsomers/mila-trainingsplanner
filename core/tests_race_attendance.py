from datetime import date
from django.contrib.auth import get_user_model
from django.test import TestCase
from core.models import Athlete, RaceEvent, RaceEventDistance, RaceEntry, RaceAttendance, TrainingSlot


class RaceAttendanceTests(TestCase):
    def setUp(self):
        self.coach = get_user_model().objects.create_user(username='attendance-coach', is_staff=True)
        self.athlete = Athlete.objects.create(owner=self.coach, name='Attend Runner', birth_year=2000, gender='X')
        self.race = RaceEvent.objects.create(owner=self.coach, name='Attend Meeting', date=date(2026, 11, 8))
        self.distance = RaceEventDistance.objects.create(race=self.race, distance='1500')
        self.client.force_login(self.coach)

    def save(self, **extra):
        return self.client.post(f'/race-calendar/{self.race.id}/entries/save/', {
            'athletes': [self.athlete.id], 'attendance_fields': '1', **extra,
        }, HTTP_X_REQUESTED_WITH='XMLHttpRequest')

    def test_attend_appears_in_all_calendars_without_distance(self):
        response = self.save(**{f'attend_{self.athlete.id}': '1'})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()['can_delete'])
        self.assertTrue(RaceAttendance.objects.filter(race=self.race, athlete=self.athlete).exists())
        self.assertFalse(RaceEntry.objects.exists())
        self.assertFalse(TrainingSlot.objects.filter(athlete=self.athlete).exists())
        self.assert_calendar_race(distance=None)
        response = self.client.get(f'/planning/year/?year=2026&period=season&athletes={self.athlete.id}')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Attend Meeting')
        self.assertContains(response, 'year-where-race_other')
        self.assertEqual(self.client.post(f'/race-calendar/{self.race.id}/delete/').status_code, 409)
        listing = self.client.get('/race-calendar/?year=2026&view=year_list&race_group=all&show_all=0')
        self.assertEqual(len(listing.context['race_rows']), 1)
        self.assertEqual(listing.context['race_rows'][0]['distance_rows'][0]['participant_count'], 0)
        self.assertTrue(listing.context['race_rows'][0]['athlete_rows'][0]['attend'])
        self.assertTrue(self.save().json()['can_delete'])
        self.assertFalse(RaceAttendance.objects.exists())

    def test_attendance_does_not_remove_existing_distance_choice(self):
        RaceEntry.objects.create(race_distance=self.distance, athlete=self.athlete, coach_selected=True)
        response = self.save(**{f'attend_{self.athlete.id}': '1', f'coach_{self.athlete.id}_{self.distance.id}': '1'})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(RaceEntry.objects.get().coach_selected)
        self.assertTrue(RaceAttendance.objects.exists())

    def test_athlete_cannot_set_attendance_for_another_athlete(self):
        user = get_user_model().objects.create_user(username='Attend_Runner')
        other = Athlete.objects.create(owner=self.coach, name='Other Runner', birth_year=2000, gender='X')
        self.client.force_login(user)
        response = self.save(**{f'attend_{other.id}': '1'})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(RaceAttendance.objects.filter(athlete=other).exists())
        response = self.save(**{f'attend_{self.athlete.id}': '1'})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(RaceAttendance.objects.filter(athlete=self.athlete).exists())

    def test_checkbox_shown_once_even_with_multiple_distances(self):
        RaceEventDistance.objects.create(race=self.race, distance='800')
        response = self.client.get('/race-calendar/?year=2026&view=year_list')
        self.assertEqual(response.content.decode().count(f'name="attend_{self.athlete.id}"'), 1)
        self.assertContains(response, '<span>Attend</span><span>Distance</span>', html=False)

    def assert_calendar_race(self, distance):
        ayc = self.client.get(f'/athlete/year/?year=2026&athlete={self.athlete.id}')
        self.assertEqual(ayc.status_code, 200)
        cell = next(cell for week in ayc.context['week_rows'] for cell in week['cells2'] if cell['day'] == self.race.date)
        self.assertIn('Attend Meeting', cell['slot'].core_text())
        self.assertEqual(cell['slot'].segments.all()[0].distance_m, distance)
        flex = self.client.get(f'/flex-planner/?start=2026-11-02&weeks=1&athletes={self.athlete.id}')
        self.assertEqual(flex.status_code, 200)
        cell = flex.context['week_rows'][0]['athlete_rows'][0]['pm_cells'][6]
        self.assertTrue(cell['calendar_race_locked'])
        self.assertIn('Attend Meeting', cell['slot'].core_text())
        self.assertEqual(cell['slot'].segments.all()[0].distance_m, distance)

    def test_distance_selection_visible_in_ayc_without_plan_membership(self):
        RaceEntry.objects.create(race_distance=self.distance, athlete=self.athlete, coach_selected=True)
        self.assert_calendar_race(distance=1500)

    def test_attend_and_distance_produce_one_race_not_a_duplicate(self):
        RaceAttendance.objects.create(race=self.race, athlete=self.athlete)
        RaceEntry.objects.create(race_distance=self.distance, athlete=self.athlete, coach_selected=True)
        from core.views.calendar import _calendar_race_slots
        slots = _calendar_race_slots([self.athlete.id], date(2026, 11, 1), date(2026, 12, 1))
        self.assertEqual(len(slots[(self.athlete.id, self.race.date)].segments.all()), 1)
        self.assert_calendar_race(distance=1500)

    def test_attendance_badge_counts_only_scoped_attendees_without_distance(self):
        RaceAttendance.objects.create(race=self.race, athlete=self.athlete)
        other = Athlete.objects.create(owner=self.coach, name="Selected Runner", birth_year=2000, gender="X")
        RaceAttendance.objects.create(race=self.race, athlete=other)
        entry = RaceEntry.objects.create(race_distance=self.distance, athlete=other, target_selected=True)
        url = "/race-calendar/?year=2026&view=year_list&race_group=all&show_all=1"
        response = self.client.get(url)
        self.assertEqual(response.context["race_rows"][0]["attendance_only_count"], 1)
        self.assertContains(response, 'data-attendance-count title="Attend without distance" >1</span>', html=False)
        response = self.client.get(url + f"&race_athlete=athlete:{other.id}")
        self.assertEqual(response.context["race_rows"][0]["attendance_only_count"], 0)
        self.assertContains(response, 'data-attendance-count title="Attend without distance" hidden>0</span>', html=False)
        entry.delete()
        response = self.client.get(url)
        self.assertEqual(response.context["race_rows"][0]["attendance_only_count"], 2)
        self.assertEqual(response.context["race_rows"][0]["distance_rows"][0]["participant_count"], 0)

    def test_multiday_year_race_is_one_pill_per_visible_chunk(self):
        self.race.date = date(2027, 9, 11)
        self.race.end_date = date(2027, 9, 19)
        self.race.save()
        RaceAttendance.objects.create(race=self.race, athlete=self.athlete)
        response = self.client.get(f"/planning/year/?year=2026&period=season&zoom=1&athletes={self.athlete.id}")
        cells = [cell for chunk in response.context["chunks"] for row in chunk["rows"] for cell in row["cells"] if cell.get("races")]
        self.assertEqual(len(cells), 9)
        self.assertEqual([cell.get("race_span") for cell in cells], [9] + [None] * 8)
        self.assertContains(response, "width: calc(100% * 9 + 8px)")
        self.assertEqual(response.content.decode().count('>Attend Meeting</span>'), 1)
        self.race.date, self.race.end_date = date(2027, 8, 31), date(2027, 9, 2)
        self.race.save()
        response = self.client.get(f"/planning/year/?year=2026&period=season&zoom=1&athletes={self.athlete.id}")
        spans = [cell["race_span"] for chunk in response.context["chunks"] for row in chunk["rows"] for cell in row["cells"] if cell.get("race_span")]
        self.assertEqual(spans, [1, 2])

    def test_athlete_sees_own_green_badges_without_other_athlete_counts(self):
        user = get_user_model().objects.create_user(username="Attend_Runner")
        other = Athlete.objects.create(owner=self.coach, name="Private Other", birth_year=2000, gender="X")
        RaceAttendance.objects.create(race=self.race, athlete=self.athlete)
        RaceAttendance.objects.create(race=self.race, athlete=other)
        RaceEntry.objects.create(race_distance=self.distance, athlete=other, coach_selected=True)
        self.client.force_login(user)
        url = "/race-calendar/?year=2026&view=list"
        response = self.client.get(url)
        row = response.context["race_rows"][0]
        self.assertEqual(row["attendance_only_count"], 1)
        self.assertEqual(row["distance_rows"][0]["participant_count"], 0)
        self.assertContains(response, 'data-attendance-count title="Attend without distance" >1</span>', html=False)
        self.assertNotContains(response, "Private Other")
        RaceEntry.objects.create(race_distance=self.distance, athlete=self.athlete, coach_selected=True)
        response = self.client.get(url)
        row = response.context["race_rows"][0]
        self.assertEqual(row["attendance_only_count"], 0)
        self.assertEqual(row["distance_rows"][0]["participant_count"], 1)
        self.assertContains(response, '<span class="race-distance-count">1</span>', html=False)
        self.assertContains(response, 'data-show-counts="1"', html=False)
