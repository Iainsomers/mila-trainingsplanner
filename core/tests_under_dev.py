from django.test import TestCase
from django.contrib.auth import get_user_model
from core.models import CoachSettings, CoachAccess


class UnderDevTests(TestCase):
    def test_default_off_toggle_and_submenus(self):
        coach=get_user_model().objects.create_user(username='dev-coach',is_staff=True)
        self.client.force_login(coach)
        for section in ('under_dev','hardware'):
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
        self.assertRedirects(self.client.get('/'),'/planning/')
        self.assertNotContains(response,'?section=hardware')
        response=self.client.get('/',{'section':'under_dev'})
        self.assertContains(response,'?section=hardware')
        self.assertContains(response,'Stats (Under Development)')
        self.assertTemplateUsed(self.client.get('/',{'section':'hardware'}),'core/hardware_access.html')
        self.client.post('/settings/',{})
        self.assertRedirects(self.client.get('/'),'/planning/')

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
                self.assertEqual(dashboard.status_code,302)
                if user==coach:
                    self.assertContains(planning,'href="'+url+'"' if not url.startswith('?') else '?section=under_dev')
                else:
                    self.assertNotContains(planning,'href="'+url+'"')
            self.assertRedirects(dashboard,'/planning/')
            self.assertContains(planning,'>New, Plans, Wishes<')

    def test_coach_selection_on_planning_keeps_access_boundaries(self):
        coach=get_user_model().objects.create_user(username='select-coach',is_staff=True)
        owner=get_user_model().objects.create_user(username='select-owner',is_staff=True)
        stranger=get_user_model().objects.create_user(username='select-stranger',is_staff=True)
        CoachAccess.objects.create(owner=owner,grantee=coach,can_edit=False)
        self.client.force_login(coach)
        self.assertRedirects(self.client.get('/'),'/planning/')
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

    def test_main_page_title_and_evaluations_back(self):
        coach=get_user_model().objects.create_user(username='back-coach',is_staff=True)
        self.client.force_login(coach)
        response=self.client.get('/planning/')
        self.assertContains(response,'<title>Mila Planner</title>',html=True)
        self.assertContains(response,'<h1 class="mb-1">Mila Planner</h1>',html=True)
        self.assertContains(self.client.get('/evaluations/'),'<a href="/planning/" class="btn btn-outline-secondary">Back</a>',html=True)

    def test_back_buttons_and_athlete_hardware_group(self):
        from core.models import Athlete
        coach=get_user_model().objects.create_user(username='hardware-coach',is_staff=True)
        runner=get_user_model().objects.create_user(username='hardware-runner')
        Athlete.objects.create(owner=coach,name='hardware-runner',birth_year=2000,gender='X',garmin_fit_upload_enabled=True)
        self.client.force_login(coach)
        for url in ('/coach-tools/','/new-plans-wishes/','/settings/'):
            from django.urls import reverse
            target=reverse('new_plans_wishes') if 'wishes' in url else url
            self.assertContains(self.client.get(target),'<a href="/planning/" class="btn btn-outline-secondary">Back</a>',html=True)
        self.assertContains(self.client.get('/planning/'),'>Athlete Info</h5>')
        self.client.force_login(runner)
        main=self.client.get('/planning/')
        self.assertContains(main,'>Athlete Info</h5>')
        self.assertContains(main,'href="/planning/?section=hardware"')
        self.assertNotContains(main,'Upload and inspect your Garmin FIT file.')
        hardware=self.client.get('/planning/',{'section':'hardware'})
        self.assertTemplateUsed(hardware,'core/athlete_hardware.html')
        self.assertContains(hardware,'Upload and inspect your Garmin FIT file.')
        self.assertContains(hardware,'>Back</a>')

    def test_standard_trainings_group_and_three_column_layout(self):
        from core.models import Athlete
        from django.urls import reverse
        coach=get_user_model().objects.create_user(username='standard-coach',is_staff=True)
        athlete=get_user_model().objects.create_user(username='standard-athlete')
        Athlete.objects.create(owner=coach,name='standard-athlete',birth_year=2000,gender='X')
        self.client.force_login(coach)
        main=self.client.get('/planning/')
        self.assertContains(main,'>Standard Trainings</h5>')
        self.assertNotContains(main,'>Saved Trainings</h5>')
        self.assertContains(main,'col-md-6 col-lg-3')
        self.assertContains(main,'col-md-6 col-lg-4')
        self.assertContains(main,'planning-section planning-more')
        standards=self.client.get('/planning/',{'section':'standards'})
        self.assertTemplateUsed(standards,'core/standard_trainings.html')
        self.assertContains(standards,reverse('coach_saved_trainings'))
        self.assertContains(standards,reverse('standard_strength_list'))
        self.client.force_login(athlete)
        main=self.client.get('/planning/')
        self.assertNotContains(main,'>Standard Trainings</h5>')
        self.assertTemplateUsed(self.client.get('/planning/',{'section':'standards'}),'core/planning.html')
