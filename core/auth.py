import hashlib

from django import forms
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.admin.forms import AdminAuthenticationForm
from django.contrib.auth.views import LoginView
from django.core.cache import cache
from django.urls import reverse


class _LoginThrottleMixin:
    """Short-lived failure throttle shared by the public and admin login."""

    failure_limit = 5
    failure_timeout = 600

    def _client_ip(self):
        forwarded = self.request.META.get("HTTP_X_FORWARDED_FOR", "")
        if forwarded:
            return forwarded.split(",", 1)[0].strip()
        return self.request.META.get("REMOTE_ADDR", "unknown")

    def _cache_key(self):
        username = str(self.data.get("username") or "").strip().lower()
        digest = hashlib.sha256(username.encode("utf-8")).hexdigest()[:24]
        return f"login-failures:{self._client_ip()}:{digest}"

    def clean(self):
        key = self._cache_key()
        failures = int(cache.get(key, 0) or 0)
        if failures >= self.failure_limit:
            raise forms.ValidationError(
                "Too many unsuccessful login attempts. Please try again later."
            )
        try:
            cleaned = super().clean()
        except forms.ValidationError:
            cache.set(key, failures + 1, self.failure_timeout)
            raise
        cache.delete(key)
        return cleaned


class ThrottledAuthenticationForm(_LoginThrottleMixin, AuthenticationForm):
    pass


class ThrottledAdminAuthenticationForm(_LoginThrottleMixin, AdminAuthenticationForm):
    pass


class AthleteAwareLoginView(LoginView):
    """Send opted-in athlete accounts to their own Athlete Year Calendar."""

    def get_success_url(self):
        # Explicit destinations (including links to a protected page) always
        # take precedence over the athlete's preferred start page.
        if self.get_redirect_url():
            return super().get_success_url()

        user = self.request.user
        if user.is_staff or user.is_superuser:
            return super().get_success_url()

        from core.views.coach import _athlete_for_user

        athlete = _athlete_for_user(user)
        if athlete and athlete.start_on_ayc:
            return reverse("athlete_year_calendar")
        return super().get_success_url()
