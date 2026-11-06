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
        response=self.client.get('/planning/')
        self.assertContains(response,'?section=under_dev')
        self.assertNotContains(self.client.get('/'),'?section=under_dev')
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

    def test_planning_navigation_for_coach_and_athlete(self):
        from core.models import Athlete
        coach=get_user_model().objects.create_user(username='navcoach',is_staff=True)
        runner=get_user_model().objects.create_user(username='navrunner')
        Athlete.objects.create(owner=coach,name='navrunner',birth_year=2000,gender='X')
        CoachSettings.objects.create(user=coach,under_dev_enabled=True)
        for user in (coach,runner):
            self.client.force_login(user)
            dashboard=self.client.get('/')
            planning=self.client.get('/planning/')
            for url in ('/coach-tools/','/settings/','/?section=under_dev'):
                self.assertNotContains(dashboard,'href="'+url+'"')
                if user==coach:
                    self.assertContains(planning,'href="'+url+'"' if not url.startswith('?') else '?section=under_dev')
                else:
                    self.assertNotContains(planning,'href="'+url+'"')
            self.assertNotContains(dashboard,'>New, Plans, Wishes<')
            self.assertContains(planning,'>New, Plans, Wishes<')

    def test_coach_selection_on_planning_keeps_access_boundaries(self):
        coach=get_user_model().objects.create_user(username='select-coach',is_staff=True)
        owner=get_user_model().objects.create_user(username='select-owner',is_staff=True)
        stranger=get_user_model().objects.create_user(username='select-stranger',is_staff=True)
        CoachAccess.objects.create(owner=owner,grantee=coach,can_edit=False)
        self.client.force_login(coach)
        self.assertNotContains(self.client.get('/'),'View as coach')
        self.assertContains(self.client.get('/planning/'),'View as coach')
        response=self.client.post('/planning/',{'coach_view_owner':owner.pk})
        self.assertRedirects(response,'/planning/')
        self.assertEqual(self.client.session['active_coach_owner_id'],owner.pk)
        self.assertContains(self.client.get('/planning/'),'View only: changes are blocked.')
        self.client.post('/planning/',{'coach_view_owner':stranger.pk})
        self.assertNotEqual(self.client.session.get('active_coach_owner_id'),stranger.pk)

    def test_dashboard_return_buttons_removed_from_templates(self):
        import re
        from pathlib import Path
        directory=Path(__file__).parent/'templates'/'core'
        for path in directory.rglob('*.html'):
            if ' - Copy' in path.name:
                continue
            source=path.read_text(encoding='utf-8')
            self.assertIsNone(re.search(r'<a[^>]+href="(?:/|\{% url [\'\"]dashboard[\'\"] %\})"',source),str(path))
