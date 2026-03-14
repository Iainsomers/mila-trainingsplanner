"""
WSGI config for mila project.

It exposes the WSGI callable as a module-level variable named ``application``.
"""

import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "mila.settings")

application = get_wsgi_application()

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