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
        self.assertEqual(self.client.get(own.photo_items[0]['url']).status_code, 200)
        self.assertEqual(self.slot.segments.get(type='MOB').photo_ids, original.photo_ids)
        response = self.client.post(f'/athlete/year/?year={self.day.year}', {
            'date':self.day.isoformat(), 'slot_index':'1', 'slot_text':'Strength',
            'plan':self.plan.pk, 'mob_text':'My strength', 'remove_mob_photo':own.photo_ids})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(own.slot.segments.get(type='MOB').photo_ids, [])

    def test_photo_link_survives_ayc_segment_recreation(self):
        self.upload()
        self.client.force_login(self.login)
        payload = {'date':self.day.isoformat(), 'slot_index':'1', 'slot_text':'Strength',
                   'plan':self.plan.pk, 'mob_text':'My strength'}
        url = f'/athlete/year/?year={self.day.year}'
        self.client.post(url, payload)
        slot = TrainingSlot.objects.get(athlete=self.athlete, date=self.day, slot_index=1)
        segment = slot.segments.get(type='MOB')
        photo_url = segment.photo_items[0]['url']
        self.client.post(url, dict(payload, mob_text='Changed notes'))
        self.assertNotEqual(slot.segments.get(type='MOB').pk, segment.pk)
        self.assertEqual(self.client.get(photo_url).status_code, 200)
        self.assertEqual(self.client.get(photo_url + '?thumb=1').status_code, 200)

    def test_coach_can_read_own_athlete_photo_in_personal_plan(self):
        seg = self.upload()
        other = get_user_model().objects.create_user(username='personal-plan-owner')
        self.slot.plan = TrainingPlan.objects.create(owner=other, name='Personal plan')
        self.slot.athlete = self.athlete
        self.slot.save()
        url = seg.photo_items[0]['url']
        self.assertEqual(self.client.get(url).status_code, 200)
        self.client.force_login(other)
        self.assertEqual(self.client.get(url).status_code, 404)

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

    def test_strength_upload_is_default_and_primary_buttons_precede_standards(self):
        response=self.client.post(self.url(),{'core2_text':'Squats','strength_photos':self.photo()})
        self.assertEqual(response.status_code,200)
        strength=self.slot.segments.get(type='CORE2')
        self.assertEqual(len(strength.photo_ids),1)
        self.assertFalse(self.slot.segments.filter(type='MOB').exists())
        self.assertEqual(strength.zone,'')
        page=self.client.get(self.url())
        html=page.content.decode()
        self.assertContains(page,'name="strength_photos"')
        self.assertNotContains(page,'name="mob_photos"')
        self.assertLess(html.index('class="modal-footer slot-main-actions"'),html.index('<b>Save standard</b>'))
        self.assertContains(page,strength.photo_items[0]['url'])
        self.assertEqual(self.client.get(strength.photo_items[0]['url']).status_code,200)
        self.client.post(self.url(),{'core2_text':'Updated squats'})
        self.assertEqual(self.slot.segments.get(type='CORE2').photo_ids,strength.photo_ids)
        self.client.post(self.url(),{'core2_text':'Updated squats','remove_strength_photo':strength.photo_ids})
        self.assertEqual(self.slot.segments.get(type='CORE2').photo_ids,[])

    def test_strength_photo_only_session_renders_and_keeps_private_access(self):
        self.client.post(self.url(),{'strength_photos':self.photo()})
        segment=self.slot.segments.get(type='CORE2')
        self.assertEqual(segment.text,'')
        self.assertEqual(len(segment.photo_ids),1)
        from django.template.loader import render_to_string
        html=render_to_string('core/partials/segment_display.html',{'seg':segment})
        self.assertIn(segment.photo_items[0]['url'],html)
        self.client.force_login(self.login)
        self.assertEqual(self.client.get(segment.photo_items[0]['url']).status_code,200)
        stranger=get_user_model().objects.create_user(username='strength-photo-outsider')
        self.client.force_login(stranger)
        self.assertEqual(self.client.get(segment.photo_items[0]['url']).status_code,404)

    def test_direct_ayc_strength_photo_does_not_move_or_drop_legacy_mob_photos(self):
        original=self.upload()
        response=self.client.post('/athlete/year/',{'athlete':self.athlete.id,'plan':self.plan.id,'date':self.day.isoformat(),
               'slot_index':1,'slot_text':'','mob_text':'Existing drills','core2_text':'Gym notes','strength_photos':self.photo()})
        self.assertIn(response.status_code,[200,204])
        own=TrainingSlot.objects.get(athlete=self.athlete,date=self.day,slot_index=1)
        self.assertEqual(own.segments.get(type='MOB').photo_ids,original.photo_ids)
        strength=own.segments.get(type='CORE2')
        self.assertEqual(len(strength.photo_ids),1)
        self.assertNotEqual(strength.photo_ids,original.photo_ids)
        url=strength.photo_items[0]['url']
        self.client.post('/athlete/year/',{'athlete':self.athlete.id,'plan':self.plan.id,'date':self.day.isoformat(),
               'slot_index':1,'slot_text':'','mob_text':'Existing drills','core2_text':'Gym notes'})
        self.assertEqual(self.client.get(url).status_code,200)
        self.assertEqual(self.slot.segments.get(type='MOB').photo_ids,original.photo_ids)

    def test_strength_photo_limit_counts_legacy_mob_and_rejects_bad_uploads(self):
        original=self.upload()
        count=TrainingPhoto.objects.count()
        response=self.client.post(self.url(),{'core2_text':'Should not save','strength_photos':[self.photo() for _ in range(5)]})
        self.assertEqual(response['HX-Retarget'],'#strengthPhotoError')
        self.assertEqual(TrainingPhoto.objects.count(),count)
        self.assertEqual(self.slot.segments.get(type='MOB').photo_ids,original.photo_ids)
        bad=SimpleUploadedFile('bad.png',b'not an image','image/png')
        response=self.client.post(self.url(),{'core2_text':'Should not save','strength_photos':bad})
        self.assertEqual(response['HX-Retarget'],'#strengthPhotoError')
        self.assertFalse(self.slot.segments.filter(type='CORE2').exists())

    def test_flex_strength_upload_and_copy_keep_photo_in_strength(self):
        response=self.client.post(self.url()+f'&athlete={self.athlete.id}&source=flex',{'core2_text':'Gym','strength_photos':self.photo()})
        self.assertEqual(response.status_code,200)
        own=TrainingSlot.objects.get(athlete=self.athlete,date=self.day,slot_index=1)
        segment=own.segments.get(type='CORE2')
        copy=f'/slot-copy/{self.day.year}/{self.day.month}/{self.day.day}/1/?plan={own.plan_id}&athlete={self.athlete.id}&source=flex'
        self.assertEqual(self.client.post(copy).status_code,200)
        target=self.day+timedelta(days=1)
        paste=f'/slot-paste/{target.year}/{target.month}/{target.day}/1/?plan={own.plan_id}&athlete={self.athlete.id}&source=flex'
        self.assertEqual(self.client.post(paste).status_code,200)
        copied=TrainingSlot.objects.get(plan=own.plan,athlete=self.athlete,date=target,slot_index=1).segments.get(type='CORE2')
        self.assertEqual(copied.photo_ids,segment.photo_ids)
        self.assertEqual(self.client.get(copied.photo_items[0]['url']).status_code,200)
