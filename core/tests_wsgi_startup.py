"""Exercise cold imports in a fresh process; the test runner warms URL modules."""
import os
from pathlib import Path
import subprocess
import sys

from django.test import SimpleTestCase


class WsgiStartupTests(SimpleTestCase):
    def test_oura_starts_only_after_url_and_http_imports_are_complete(self):
        script = '''
import os, sys
from unittest.mock import patch, MagicMock
os.environ['DJANGO_SETTINGS_MODULE'] = 'mila.settings'
os.environ['OURA_AUTO_IMPORT_WORKER'] = '1'
import django
django.setup()
assert 'core.urls' not in sys.modules
def start():
    for name in ('core.urls', 'core.views.garmin', 'core.views.oura', 'requests'):
        module = sys.modules.get(name)
        assert module is not None, name + ' missing before Oura thread starts'
        assert not getattr(module.__spec__, '_initializing', False), name + ' still importing'
user = MagicMock()
user.objects.filter.return_value.exists.return_value = True
with patch('core.oura_sync.start_worker', side_effect=start) as worker, patch('django.contrib.auth.get_user_model', return_value=user):
    import mila.wsgi
    worker.assert_called_once_with()
'''
        result = subprocess.run([sys.executable, "-c", script],
            cwd=Path(__file__).resolve().parent.parent,
            env={**os.environ, "RENDER": "", "DATABASE_URL": ""}, capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
