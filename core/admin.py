from django.contrib import admin
from core.models import CoachAccess


@admin.register(CoachAccess)
class CoachAccessAdmin(admin.ModelAdmin):
    list_display = ("grantee", "owner", "can_edit", "created_at")
    list_filter = ("can_edit",)
    search_fields = ("grantee__username", "grantee__first_name", "grantee__last_name", "owner__username", "owner__first_name", "owner__last_name")
