from django.test import TestCase
from django.contrib.auth import get_user_model
from core.models import CoachSettings, CoachAccess


class UnderDevTests(TestCase):
    def test_default_off_toggle_and_submenus(self):
        coach=get_user_model().objects.create_user(username='dev-coach',is_staff=True)
        self.client.force_login(coach)
        for section in ('','under_dev','hardware'):
            response=self.client.get('/',{'section':section})
            self.assertTemplateUsed(response,'core/dashboard.html')
            self.assertNotContains(response,'?section=under_dev')
        settings=self.client.get('/settings/')
        self.assertContains(settings,'id="under-dev-enabled"')
        self.assertFalse(CoachSettings.objects.get(user=coach).under_dev_enabled)
        self.assertEqual(self.client.post('/settings/',{'under_dev_enabled':'on'}).status_code,302)
        self.assertTrue(CoachSettings.objects.get(user=coach).under_dev_enabled)
        response=self.client.get('/')
        self.assertContains(response,'?section=under_dev')
        self.assertNotContains(response,'?section=hardware')
        response=self.client.get('/',{'section':'under_dev'})
        self.assertContains(response,'?section=hardware')
        self.assertContains(response,'Stats (under development)')
        self.assertTemplateUsed(self.client.get('/',{'section':'hardware'}),'core/hardware_access.html')
        self.client.post('/settings/',{})
        self.assertNotContains(self.client.get('/'),'?section=under_dev')

    def test_view_only_coach_cannot_enable_module(self):
        owner=get_user_model().objects.create_user(username='dev-owner',is_staff=True)
        viewer=get_user_model().objects.create_user(username='dev-viewer',is_staff=True)
        CoachSettings.objects.create(user=owner)
        CoachAccess.objects.create(owner=owner,grantee=viewer,can_edit=False)
        self.client.force_login(viewer)
        session=self.client.session
        session['active_coach_owner_id']=owner.pk
        session.save()
        self.assertEqual(self.client.post('/settings/',{'under_dev_enabled':'on'}).status_code,403)
        self.assertFalse(CoachSettings.objects.get(user=owner).under_dev_enabled)
