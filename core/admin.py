from django.contrib import admin
from core.models import Athlete, CoachAccess
from core.auth import ThrottledAdminAuthenticationForm

admin.site.login_form = ThrottledAdminAuthenticationForm


@admin.register(CoachAccess)
class CoachAccessAdmin(admin.ModelAdmin):
    list_display = ("grantee", "owner", "can_edit", "created_at")
    list_filter = ("can_edit",)
    search_fields = ("grantee__username", "grantee__first_name", "grantee__last_name", "owner__username", "owner__first_name", "owner__last_name")


@admin.register(Athlete)
class AthleteAdmin(admin.ModelAdmin):
    list_display = ("name", "owner", "birth_year", "gender")
    list_filter = ("owner", "gender")
    search_fields = ("name", "owner__username", "owner__first_name", "owner__last_name")
    autocomplete_fields = ("owner",)
