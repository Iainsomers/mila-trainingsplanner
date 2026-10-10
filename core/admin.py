from django.contrib import admin
from core.models import Athlete, CoachAccess, CoachSettings, Team
from core.auth import ThrottledAdminAuthenticationForm

admin.site.login_form = ThrottledAdminAuthenticationForm


@admin.register(CoachAccess)
class CoachAccessAdmin(admin.ModelAdmin):
    list_display = ("grantee", "owner", "can_edit", "created_at")
    list_filter = ("can_edit",)
    search_fields = ("grantee__username", "grantee__first_name", "grantee__last_name", "owner__username", "owner__first_name", "owner__last_name")


@admin.register(Athlete)
class AthleteAdmin(admin.ModelAdmin):
    list_display = ("name", "owner", "team", "birth_year", "gender")
    readonly_fields = ("team",)
    list_filter = ("owner", "team", "gender")
    search_fields = ("name", "owner__username", "owner__first_name", "owner__last_name")
    autocomplete_fields = ("owner", "team")


@admin.register(CoachSettings)
class CoachSettingsAdmin(admin.ModelAdmin):
    list_display = ("user", "team")
    list_editable = ("team",)
    list_filter = ("team",)
    search_fields = ("user__username", "user__first_name", "user__last_name")
    autocomplete_fields = ("user", "team")


@admin.register(Team)
class TeamAdmin(admin.ModelAdmin):
    list_display = ("name",)
    search_fields = ("name",)
