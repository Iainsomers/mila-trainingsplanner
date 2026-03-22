from django.contrib import admin
from core.models import CoachAccess


# Alleen CoachAccess zichtbaar maken in admin
admin.site.register(CoachAccess)
