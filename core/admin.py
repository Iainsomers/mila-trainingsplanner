# core/admin.py
from django.contrib import admin

# Intentionally empty:
# We keep Django admin for authentication & authorization only
# (Users / auth Groups / Permissions).
#
# All MiLa domain models (plans, athletes, groups, slots, segments, logs)
# are managed via the Coach Console UI instead of /admin/.
