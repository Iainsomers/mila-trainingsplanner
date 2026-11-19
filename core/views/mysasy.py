"""Individual consent and a clean-URL confirmation for mySASY's stateless redirect."""
from datetime import timedelta
import json
from uuid import UUID

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.debug import sensitive_variables
from django.views.decorators.http import require_GET, require_POST, require_http_methods

from core.models import Athlete, MySasyConnection, MySasyLinkAttempt
from core.mysasy import MySasyError, configured, measurements, diagnostic_response
from core.views.oura import _athlete_user
from core.views.athlete_identity import _is_ayc_coach_user
from core.views.common import _filter_owned, _active_coach_can_edit
from core.access import evaluation_visibility_for_request

PENDING = "mysasy_link_attempt"


def own_athlete(request):
    athlete = _athlete_user(request)
    if athlete:
        MySasyLinkAttempt.objects.filter(created_at__lte=timezone.now() - timedelta(minutes=10)).delete()
    return athlete if athlete and athlete.mysasy_connection_enabled else None


def pending(request, athlete):
    try:
        identity = UUID(str(request.session.get(PENDING, "")))
    except (ValueError, TypeError):
        return MySasyLinkAttempt.objects.none()
    return MySasyLinkAttempt.objects.filter(
        pk=identity, user=request.user, athlete=athlete,
        created_at__gt=timezone.now() - timedelta(minutes=10),
    )


@login_required
@never_cache
@require_GET
def mysasy_view(request):
    athlete = own_athlete(request)
    if not athlete:
        return HttpResponseForbidden()
    connection = MySasyConnection.objects.filter(athlete=athlete).first()
    return render(request, "core/mysasy.html", {
        "connection": connection, "configured": configured(),
        "rows": connection.measurements if connection else [],
    })


@login_required
@never_cache
@require_POST
def mysasy_connect(request):
    athlete = own_athlete(request)
    if not athlete:
        return HttpResponseForbidden()
    if not configured() or request.POST.get("consent") != "on" or request.POST.get("permission") != "on":
        messages.error(request, "Confirm both permissions before connecting. mySASY must also be configured.")
        return redirect("mysasy")
    MySasyLinkAttempt.objects.filter(user=request.user).delete()
    attempt = MySasyLinkAttempt.objects.create(user=request.user, athlete=athlete)
    request.session[PENDING] = str(attempt.pk)
    return redirect("https://client.mysasy.com/profile/connect/" + str(settings.MYSASY_APPLICATION_ID))


@never_cache
@require_GET
@sensitive_variables()
def mysasy_callback(request):
    athlete = own_athlete(request)
    if not athlete:
        # Never copy the query token into a login URL's `next` parameter.
        response = redirect("mysasy") if not request.user.is_authenticated else HttpResponseForbidden()
        response["Referrer-Policy"] = "no-referrer"
        return response
    # Claim the initiation once, across workers; no callback state is supported by mySASY.
    with transaction.atomic():
        attempt = pending(request, athlete).select_for_update().first()
        if not attempt or attempt.callback_received:
            response = redirect("mysasy")
            messages.error(request, "This connection request expired or was already used. Please start again.")
        else:
            attempt.callback_received = True
            attempt.save(update_fields=["callback_received"])
            token = request.GET.get("token", "")
            accepted = request.GET.getlist("success") == ["1"] and len(request.GET.getlist("token")) == 1
            if not accepted or not token or len(token) > 4096 or any(ord(c) < 33 or ord(c) > 126 for c in token):
                attempt.delete()
                request.session.pop(PENDING, None)
                messages.info(request, "mySASY authorization was declined or invalid. You can try again.")
                response = redirect("mysasy")
            else:
                attempt.auth_token = token
                attempt.save(update_fields=["auth_token"])
                response = redirect("mysasy_confirm")
    response["Referrer-Policy"] = "no-referrer"
    return response


@login_required
@never_cache
@require_GET
@sensitive_variables()
def mysasy_confirm(request):
    athlete = own_athlete(request)
    if not athlete:
        return HttpResponseForbidden()
    with transaction.atomic():
        attempt = pending(request, athlete).select_for_update().first()
        if not attempt or not attempt.auth_token:
            return redirect("mysasy")
        # Fetch once per attempt; even an empty successful response is cached.
        if not attempt.measurements:
            try:
                rows = measurements(attempt.auth_token)
            except MySasyError as error:
                attempt.delete()
                request.session.pop(PENDING, None)
                messages.error(request, str(error))
                return redirect("mysasy")
            attempt.measurements = {"rows": rows}
            attempt.save(update_fields=["measurements"])
        response = render(request, "core/mysasy.html", {
            "confirm": True, "attempt_id": str(attempt.pk), "rows": attempt.measurements["rows"],
        })
    response["Referrer-Policy"] = "no-referrer"
    return response


@login_required
@never_cache
@require_POST
@sensitive_variables()
def mysasy_finish(request):
    athlete = own_athlete(request)
    if not athlete:
        return HttpResponseForbidden()
    with transaction.atomic():
        # Serialize permission changes/disconnect with the permanent write.
        athlete = Athlete.objects.select_for_update().get(pk=athlete.pk)
        attempt = pending(request, athlete).select_for_update().first()
        if not athlete.mysasy_connection_enabled or not attempt or request.POST.get("attempt") != str(attempt.pk):
            return HttpResponseForbidden()
        if request.POST.get("cancel") != "on":
            if request.POST.get("own_account") != "on" or not attempt.auth_token or not attempt.measurements:
                return HttpResponseForbidden()
            MySasyConnection.objects.update_or_create(athlete=athlete, defaults={
                "auth_token": attempt.auth_token, "consented_by": request.user,
                "consented_at": timezone.now(), "last_checked_at": timezone.now(),
                "measurements": attempt.measurements["rows"],
                "diagnostic_payload": None, "diagnostic_checked_at": None,
            })
            messages.success(request, "Your mySASY account is connected.")
        attempt.delete()
        request.session.pop(PENDING, None)
    return redirect("mysasy")


@login_required
@never_cache
@require_POST
@sensitive_variables()
def mysasy_refresh(request):
    athlete = own_athlete(request)
    if not athlete:
        return HttpResponseForbidden()
    with transaction.atomic():
        connection = MySasyConnection.objects.select_for_update().filter(athlete=athlete).first()
        if connection and connection.last_checked_at <= timezone.now() - timedelta(minutes=10):
            # Record failed checks too, to protect the shared quota.
            connection.last_checked_at = timezone.now()
            connection.save(update_fields=["last_checked_at"])
            try:
                connection.measurements = measurements(connection.auth_token)
                connection.save(update_fields=["measurements"])
                messages.success(request, "mySASY measurements updated.")
            except MySasyError as error:
                messages.error(request, str(error))
        elif connection:
            messages.info(request, "Recent measurements are already loaded. Refresh is available every 10 minutes.")
    return redirect("mysasy")


@login_required
@never_cache
@require_POST
def mysasy_disconnect(request):
    athlete = own_athlete(request)
    if not athlete:
        return HttpResponseForbidden()
    with transaction.atomic():
        Athlete.objects.select_for_update().get(pk=athlete.pk)
        MySasyConnection.objects.filter(athlete=athlete).delete()
        MySasyLinkAttempt.objects.filter(athlete=athlete).delete()
        request.session.pop(PENDING, None)
    messages.info(request, "mySASY disconnected from MiLa. You can also withdraw access in your mySASY account.")
    return redirect("mysasy")


@login_required
@never_cache
@require_http_methods(["GET", "POST"])
def mysasy_coach_view(request, athlete_id):
    if not (request.user.is_staff or request.user.is_superuser or _is_ayc_coach_user(request.user)):
        return HttpResponseForbidden()
    athlete = get_object_or_404(_filter_owned(Athlete.objects.all(), request), pk=athlete_id)
    if not athlete.mysasy_connection_enabled or not evaluation_visibility_for_request(request, athlete.owner)["vitals"]:
        return HttpResponseForbidden()
    connection = MySasyConnection.objects.filter(athlete=athlete).first()
    if request.method == "POST":
        if not _active_coach_can_edit(request):
            return HttpResponseForbidden()
        with transaction.atomic():
            connection = MySasyConnection.objects.select_for_update().filter(athlete=athlete).first()
            if not connection:
                messages.info(request, "Connect the athlete's mySASY account first.")
            elif connection.diagnostic_checked_at and connection.diagnostic_checked_at > timezone.now() - timedelta(minutes=10):
                messages.info(request, "The latest API test is shown below. A new request is available every 10 minutes.")
            else:
                connection.diagnostic_checked_at = timezone.now()
                connection.save(update_fields=["diagnostic_checked_at"])
                try:
                    connection.diagnostic_payload = diagnostic_response(connection.auth_token)
                    connection.save(update_fields=["diagnostic_payload"])
                    messages.success(request, "API test data received.")
                except MySasyError as error:
                    messages.error(request, str(error))
        return redirect("mysasy_coach", athlete_id=athlete.pk)
    return render(request, "core/mysasy.html", {
        "connection": connection, "rows": connection.measurements if connection else [],
        "read_only": True, "athlete_name": athlete.name,
        "can_test": _active_coach_can_edit(request),
        "back_url": reverse("coach_athlete_edit", args=[athlete.pk]),
        "diagnostic_json": json.dumps(connection.diagnostic_payload, indent=2, ensure_ascii=False)
            if connection and connection.diagnostic_payload is not None else None,
    })
