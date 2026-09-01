from django.http import HttpResponse

from core.views.common import _active_coach_can_edit, _active_coach_user


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
