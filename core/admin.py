from django.contrib import admin
from core.models import CoachAccess


# Only make CoachAccess visible in admin
admin.site.register(CoachAccess)
