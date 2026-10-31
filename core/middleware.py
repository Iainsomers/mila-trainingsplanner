from django.http import HttpResponse
from django.shortcuts import redirect

from core.access import is_coach_tools_only_user
from core.views.common import _active_coach_can_edit, _active_coach_user


class AthleteLastActiveMiddleware:
    """Track interactive athlete use, never coach views or background imports."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        before_user = getattr(request, "user", None)
        if before_user is not None:
            bool(before_user.is_authenticated)  # Resolve before logout replaces request.user.
        response = self.get_response(request)
        user = getattr(request, "user", None)
        if not getattr(user, "is_authenticated", False):
            user = before_user
        if (not getattr(user, "is_authenticated", False) or user.is_staff or user.is_superuser
                or request.method not in {"GET", "POST"} or not 200 <= response.status_code < 400):
            return response
        path = request.path_info
        if path.startswith(("/static/", "/admin/", "/integrations/garmin/activities/", "/integrations/coros/")):
            return response
        purpose = (request.headers.get("Purpose", "") + request.headers.get("Sec-Purpose", "")).lower()
        if "prefetch" in purpose or "prerender" in purpose:
            return response
        if request.method == "GET":
            if (not response.get("Content-Type", "").startswith("text/html")
                    or request.headers.get("X-Requested-With") == "XMLHttpRequest"
                    or request.headers.get("Sec-Fetch-Mode", "navigate") != "navigate"):
                return response
        from core.views.athlete_identity import _athlete_for_user, _is_ayc_coach_user
        if _is_ayc_coach_user(user):
            return response
        athlete = _athlete_for_user(user)
        if athlete:
            from core.models import Athlete
            from django.db.models import Q
            from django.utils import timezone
            now = timezone.now()
            Athlete.objects.filter(pk=athlete.pk).filter(
                Q(last_active_at__isnull=True) | Q(last_active_at__lt=now)
            ).update(last_active_at=now)
        return response


class CoachToolsOnlyMiddleware:
    """
    Keeps the shared coach-tools login away from the main Mila planner.
    """

    ALLOWED_PATHS = {"/", "/login/", "/logout/"}
    ALLOWED_PREFIXES = (
        "/coach-tools/",
        "/timer/",
        "/static/",
        "/favicon.ico",
    )

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, "user", None)
        if user and is_coach_tools_only_user(user):
            path = request.path_info or request.path or ""
            if path not in self.ALLOWED_PATHS and not path.startswith(self.ALLOWED_PREFIXES):
                return redirect("coach_tools")

        return self.get_response(request)


class CoachViewEditAccessMiddleware:
    """
    Blocks write actions while a trainer is explicitly viewing another coach
    through a view-only CoachAccess relation.
    """

    SAFE_METHODS = {"GET", "HEAD", "OPTIONS", "TRACE"}
    ALLOWED_PREFIXES = ("/admin/",)
    ALLOWED_PATHS = {"/", "/logout/"}

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.method not in self.SAFE_METHODS:
            user = getattr(request, "user", None)
            if user and user.is_authenticated and (user.is_staff or user.is_superuser):
                path = request.path_info or request.path or ""
                if path not in self.ALLOWED_PATHS and not path.startswith(self.ALLOWED_PREFIXES):
                    active_owner = _active_coach_user(request)
                    if active_owner.id != user.id and not _active_coach_can_edit(request):
                        return HttpResponse("View-only coach access.", status=403)

        return self.get_response(request)
