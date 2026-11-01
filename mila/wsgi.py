"""
WSGI config for mila project.

It exposes the WSGI callable as a module-level variable named ``application``.
"""

import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "mila.settings")

application = get_wsgi_application()

# Render web workers poll independently of athlete page visits. A separate
# scheduler can instead call `manage.py sync_oura` with this worker disabled.
if os.environ.get("OURA_AUTO_IMPORT_WORKER", "1" if os.environ.get("RENDER") == "true" else "0") == "1":
    # Django resolves URLs lazily on the first request. Finish importing the
    # complete view graph on this thread before the poller imports Oura views.
    # Otherwise the request and poller can wait on each other's module locks
    # (notably requests), until Gunicorn kills the request worker.
    from django.urls import get_resolver

    get_resolver().url_patterns
    from core.oura_sync import start_worker
    start_worker()

# ---- Auto-create superuser if none exists (Render without shell) ----
try:
    from django.contrib.auth import get_user_model

    User = get_user_model()

    if not User.objects.filter(is_superuser=True).exists():
        User.objects.create_superuser(
            username="admin",
            email="admin@example.com",
            password="admin1234",
        )
        print("Auto-created admin user: admin / admin1234")

except Exception as e:
    print("Superuser auto-create skipped:", e)
