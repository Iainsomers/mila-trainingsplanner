from datetime import date, timedelta
from io import BytesIO

from PIL import Image
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase

from core.models import Athlete, TrainingPlan, TrainingSlot, TrainingPhoto, PlanMembership, CoachAccess
from core.views.slots import _week_segment_payload


class TrainingPhotoTests(TestCase):
    def setUp(self):
        self.coach = get_user_model().objects.create_user(username='photo-coach', is_staff=True)
        self.athlete = Athlete.objects.create(owner=self.coach, name='Photo Runner', birth_year=2000, gender='X')
        self.login = get_user_model().objects.create_user(username='Photo_Runner')
        self.day = date.today()
        self.plan = TrainingPlan.objects.create(owner=self.coach, name='Photo plan', start_date=self.day, end_date=self.day + timedelta(days=30))
        PlanMembership.objects.create(plan=self.plan, athlete=self.athlete)
        self.slot = TrainingSlot.objects.create(plan=self.plan, date=self.day, slot_index=1)
        self.slot.segments.create(type='MOB', text='Strength')
        self.client.force_login(self.coach)

    def url(self, day=None):
        day = day or self.day
        return f'/slot-modal/{day.year}/{day.month}/{day.day}/1/?plan={self.plan.pk}'

    def photo(self):
        output = BytesIO()
        Image.new('RGB', (2600, 1200), 'white').save(output, 'PNG')
        return SimpleUploadedFile('workout.png', output.getvalue(), 'image/png')

    def upload(self):
        response = self.client.post(self.url(), {'mob_text':'Strength', 'mob_photos':self.photo()})
        self.assertEqual(response.status_code, 200)
        return self.slot.segments.get(type='MOB')

    def test_upload_normalizes_and_previews_and_preserves_on_text_save(self):
        seg = self.upload()
        self.assertEqual(len(seg.photo_ids), 1)
        photo = TrainingPhoto.objects.get()
        with Image.open(BytesIO(bytes(photo.image))) as image:
            self.assertEqual(image.format, 'JPEG')
            self.assertLessEqual(max(image.size), 2200)
            self.assertFalse(image.getexif())
        page = self.client.get(self.url())
        self.assertContains(page, seg.photo_items[0]['url'])
        self.assertContains(page, 'hx-encoding="multipart/form-data"')
        self.client.post(self.url(), {'mob_text':'New notes'})
        self.assertEqual(self.slot.segments.get(type='MOB').photo_ids, seg.photo_ids)

    def test_photos_are_private_and_own_athlete_can_read_plan(self):
        seg = self.upload()
        url = seg.photo_items[0]['url']
        self.assertEqual(self.client.get(url).status_code, 200)
        self.client.force_login(self.login)
        response = self.client.get(url + '?thumb=1')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Cache-Control'], 'private, no-store')
        other = get_user_model().objects.create_user(username='unrelated', is_staff=True)
        self.client.force_login(other)
        self.assertEqual(self.client.get(url).status_code, 404)
        CoachAccess.objects.create(owner=self.coach, grantee=other)
        self.assertEqual(self.client.get(url).status_code, 200)
        self.client.logout()
        self.assertEqual(self.client.get(url).status_code, 302)

    def test_athlete_ayc_upload_and_remove_does_not_change_shared_plan(self):
        original = self.upload()
        self.client.force_login(self.login)
        response = self.client.post(f'/athlete/year/?year={self.day.year}', {
            'date':self.day.isoformat(), 'slot_index':'1', 'slot_text':'Strength',
            'plan':self.plan.pk, 'mob_text':'My strength', 'mob_photos':self.photo()})
        self.assertEqual(response.status_code, 200)
        own = TrainingSlot.objects.get(athlete=self.athlete, date=self.day, slot_index=1).segments.get(type='MOB')
        self.assertEqual(len(own.photo_ids), 2)
        self.assertEqual(self.slot.segments.get(type='MOB').photo_ids, original.photo_ids)
        response = self.client.post(f'/athlete/year/?year={self.day.year}', {
            'date':self.day.isoformat(), 'slot_index':'1', 'slot_text':'Strength',
            'plan':self.plan.pk, 'mob_text':'My strength', 'remove_mob_photo':own.photo_ids})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(own.slot.segments.get(type='MOB').photo_ids, [])

    def test_invalid_photo_and_limit_do_not_replace_training(self):
        seg = self.upload()
        response = self.client.post(self.url(), {'mob_text':'Changed', 'mob_photos':SimpleUploadedFile('bad.jpg', b'not an image', 'image/jpeg')})
        self.assertEqual(response['HX-Retarget'], '#mobPhotoError')
        self.assertEqual(self.slot.segments.get(type='MOB').text, 'Strength')
        self.assertEqual(TrainingPhoto.objects.count(), 1)
        response = self.client.post(self.url(), {'mob_text':'Changed', 'mob_photos':[self.photo() for _ in range(5)]})
        self.assertContains(response, 'up to 5')
        self.assertEqual(self.slot.segments.get(type='MOB').photo_ids, seg.photo_ids)

    def test_athlete_cannot_upload_to_future_training_without_edit_rights(self):
        self.client.force_login(self.login)
        tomorrow = self.day + timedelta(days=1)
        response = self.client.post(self.url(tomorrow) + f'&athlete={self.athlete.pk}&source=athlete_year',
                                    {'mob_text':'Strength', 'mob_photos':self.photo()})
        self.assertEqual(response.status_code, 403)
        self.assertEqual(TrainingPhoto.objects.count(), 0)

    def test_photo_only_training_and_display_clone_preserve_photo_links(self):
        self.client.post(self.url(), {'mob_photos':self.photo()})
        seg = self.slot.segments.get(type='MOB')
        self.assertEqual(seg.text, '')
        from core.views.calendar import _clone_slot_for_display
        from django.template.loader import render_to_string
        clone = _clone_slot_for_display(self.slot)
        self.assertEqual(clone.segments.all()[0].photo_items, seg.photo_items)
        html = render_to_string('core/partials/segment_display.html', {'seg':clone.segments.all()[0]})
        self.assertIn(seg.photo_items[0]['url'], html)

    def test_day_copy_and_delete_reference_leave_original_available(self):
        seg = self.upload()
        self.assertEqual(_week_segment_payload(self.slot)[0]['photo_ids'], seg.photo_ids)
        parts = f'{self.day.year}/{self.day.month}/{self.day.day}/1/'
        response = self.client.post('/slot-copy/' + parts + f'?plan={self.plan.pk}')
        self.assertEqual(response.status_code, 200)
        tomorrow = self.day + timedelta(days=1)
        parts = f'{tomorrow.year}/{tomorrow.month}/{tomorrow.day}/1/'
        response = self.client.post('/slot-paste/' + parts + f'?plan={self.plan.pk}')
        self.assertEqual(response.status_code, 200)
        copied = TrainingSlot.objects.get(plan=self.plan, date=tomorrow, slot_index=1).segments.get(type='MOB')
        self.assertEqual(copied.photo_ids, seg.photo_ids)
        self.assertEqual(self.client.get(copied.photo_items[0]['url']).status_code, 200)
        self.client.post(self.url(), {'mob_text':'Strength', 'remove_mob_photo':seg.photo_ids})
        self.assertEqual(self.client.get(copied.photo_items[0]['url']).status_code, 200)
