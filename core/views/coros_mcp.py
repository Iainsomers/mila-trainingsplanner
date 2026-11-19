"""Per-athlete COROS EU MCP connection, activity preview and explicit FIT import."""
import base64
import hashlib
import json
import secrets
import re
import struct
from datetime import timedelta
from urllib.parse import urlencode, urlsplit, urljoin

import requests
from django.contrib.auth.decorators import login_required
from django.core import signing
from django.db import transaction
from django.http import HttpResponseForbidden
from django.shortcuts import redirect, render as django_render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from core.models import CorosMCPConnection, GarminActivity, Athlete
from core.fit_reader import parse_fit, json_safe_fit_data, fit_bytes_from_upload
from core.views.oura import _athlete_user as _own_athlete


def _athlete_user(request):
    athlete = _own_athlete(request)
    return athlete if athlete and athlete.coros_connection_enabled else None

BASE = "https://mcpeu.coros.com"
PENDING = "coros_mcp_pending"
MAX_FIT_BYTES = 12 * 1024 * 1024


def render(request, template, context):
    athlete = _athlete_user(request)
    if athlete:
        from core.views.garmin import fit_ai_allowed
        context["sync_connection"] = CorosMCPConnection.objects.filter(athlete=athlete).first()
        context["fit_ai_allowed"] = fit_ai_allowed(athlete)
    return django_render(request, template, context)


def _text(content):
    """COROS sometimes JSON-encodes its text a second time."""
    value = "\n\n".join(item.get("text", "") for item in content.get("content", [])
                        if item.get("type") == "text" and isinstance(item.get("text"), str))
    for _ in range(2):
        try:
            decoded = json.loads(value)
        except (ValueError, TypeError):
            break
        if not isinstance(decoded, str):
            break
        value = decoded
    return value


def _activity_rows(text, request, connection):
    rows = []
    for block in re.split(r"(?m)^\s*(?=\d+\.\s)", text):
        heading = re.match(r"\s*\d+\.\s+(.+?)\s+[—–]\s+(\d{4}-\d{2}-\d{2})", block)
        identity = re.search(r"LabelId:\s*([A-Za-z0-9_-]{1,100})\s*\|\s*SportType:\s*(\d{1,6})", block, re.I)
        if not heading or not identity:
            continue
        label, sport = identity.groups()
        row = {"sport":heading[1], "date":heading[2], "label":label, "sport_code":int(sport)}
        for key, caption in (("duration", "Duration"), ("distance", "Distance"), ("pace", "Average Pace"), ("hr", "Avg HR")):
            match = re.search(r"\b" + caption + r":\s*([^|\n]+)", block, re.I)
            row[key] = match[1].strip() if match else ""
        if request is not None:
            row["ticket"] = signing.dumps({"user":request.user.pk, "athlete":connection.athlete_id,
                "connection":connection.pk, "label":label, "sport":int(sport)}, salt="coros-fit-selection")
        row["imported"] = GarminActivity.objects.filter(athlete_id=connection.athlete_id,
            parsed_data__coros_mcp_label=label).exists()
        rows.append(row)
    return rows


def _start_session(connection):
    if connection.expires_at and connection.expires_at <= timezone.now() + timedelta(seconds=60):
        token = _json(requests.post(BASE + "/oauth2/token", data={"grant_type":"refresh_token",
            "refresh_token":connection.refresh_token, "client_id":connection.client_id}, timeout=15))
        access = token["access_token"]
        if not isinstance(access, str) or not access:
            raise ValueError()
        connection.access_token = access
        connection.refresh_token = token.get("refresh_token", connection.refresh_token)
        connection.expires_at = timezone.now() + timedelta(seconds=int(token.get("expires_in", 2592000)))
        connection.save(update_fields=["access_token", "refresh_token", "expires_at"])
    _, session = _rpc(connection, {"jsonrpc":"2.0", "id":1, "method":"initialize", "params":{
        "protocolVersion":"2025-03-26", "capabilities":{}, "clientInfo":{"name":"MiLa Planner", "version":"1.0"}}})
    _rpc(connection, {"jsonrpc":"2.0", "method":"notifications/initialized"}, session)
    return session


def _tool(connection, session, name, arguments):
    result, _ = _rpc(connection, {"jsonrpc":"2.0", "id":2, "method":"tools/call",
        "params":{"name":name, "arguments":arguments}}, session)
    content = result.get("result", {})
    if content.get("isError"):
        raise ValueError()
    return content


def _download_fit(url):
    # Only COROS-hosted HTTPS downloads. Never forward OAuth credentials to
    # file hosts, and recheck every redirect before making the next request.
    for _ in range(4):
        parsed = urlsplit(url)
        host = (parsed.hostname or "").lower()
        if (parsed.scheme != "https" or parsed.username or parsed.password or parsed.port not in (None, 443)
                or not (host == "coros.com" or host.endswith(".coros.com"))):
            raise ValueError("Unsupported COROS download host.")
        with requests.get(url, timeout=(10, 30), stream=True, allow_redirects=False) as response:
            if response.status_code in (301, 302, 303, 307, 308):
                url = urljoin(url, response.headers.get("Location", ""))
                continue
            response.raise_for_status()
            chunks, size = [], 0
            for chunk in response.iter_content(65536):
                size += len(chunk)
                if size > MAX_FIT_BYTES:
                    raise ValueError("FIT file exceeds 12 MB.")
                chunks.append(chunk)
            raw = b"".join(chunks)
            filename = "activity.zip" if raw.startswith(b"PK") else "activity.fit"
            return fit_bytes_from_upload(filename, raw)[1]
    raise ValueError("Too many download redirects.")


def _json(response):
    response.raise_for_status()
    if len(response.content) > 2_000_000:
        raise ValueError("Response too large")
    return response.json()


@login_required
@require_GET
def coros_mcp_view(request):
    athlete = _athlete_user(request)
    if not athlete:
        return HttpResponseForbidden("Connect from your own athlete account.")
    connection = CorosMCPConnection.objects.filter(athlete=athlete).first()
    return render(request, "core/coros_mcp.html", {"connected": bool(connection)})


@login_required
@require_POST
def coros_mcp_ai_permission(request):
    athlete = _athlete_user(request)
    if not athlete:
        return HttpResponseForbidden("Only the athlete can change AI permission.")
    from core.views.garmin import CONSENT_VERSION
    now = timezone.now()
    if request.POST.get("consent_fit_ai") == "on":
        athlete.fit_ai_consent_at = now
        athlete.fit_ai_consent_version = CONSENT_VERSION
        athlete.fit_ai_withdrawn_at = None
    else:
        athlete.fit_ai_withdrawn_at = now
    athlete.save(update_fields=[
        "fit_ai_consent_at", "fit_ai_consent_version", "fit_ai_withdrawn_at",
    ])
    if request.POST.get("next") == "hardware":
        return redirect(reverse("planning_overview") + "?section=hardware")
    return redirect("coros_mcp")


@login_required
@require_POST
def coros_mcp_connect(request):
    athlete = _athlete_user(request)
    if not athlete:
        return HttpResponseForbidden()
    if request.POST.get("consent") != "on":
        return redirect("coros_mcp")
    callback = request.build_absolute_uri(reverse("coros_mcp_callback"))
    try:
        registration = _json(requests.post(BASE + "/connect/register", json={
            "client_name":"MiLa Planner", "redirect_uris":[callback],
            "grant_types":["authorization_code", "refresh_token"],
            "response_types":["code"], "token_endpoint_auth_method":"none",
        }, timeout=15))
        client = registration["client_id"]
        if not isinstance(client, str) or not client:
            raise ValueError()
    except (requests.RequestException, ValueError, KeyError):
        return render(request, "core/coros_mcp.html", {"error":"COROS registration failed. Please try again."})
    verifier = secrets.token_urlsafe(64)
    state = secrets.token_urlsafe(32)
    request.session[PENDING] = {"state":state, "verifier":verifier, "client":client,
        "athlete":athlete.pk, "user":request.user.pk, "started":timezone.now().timestamp(), "callback":callback}
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
    return redirect(BASE + "/oauth2/authorize?" + urlencode({"response_type":"code", "client_id":client,
        "redirect_uri":callback, "state":state, "code_challenge":challenge, "code_challenge_method":"S256",
        "scope":"mcp.tools offline_access", "resource":BASE + "/mcp"}))


@login_required
@require_GET
def coros_mcp_callback(request):
    pending = request.session.pop(PENDING, None)
    athlete = _athlete_user(request)
    if (not athlete or not pending or pending.get("athlete") != athlete.pk
            or pending.get("user") != request.user.pk
            or not 0 <= timezone.now().timestamp() - pending.get("started", 0) <= 600
            or not secrets.compare_digest(pending.get("state", ""), request.GET.get("state", ""))):
        return HttpResponseForbidden("Authorization expired. Start a new connection.")
    try:
        if request.GET.get("error") or not request.GET.get("code"):
            raise ValueError()
        token = _json(requests.post(BASE + "/oauth2/token", data={"grant_type":"authorization_code",
            "client_id":pending["client"], "code":request.GET["code"], "redirect_uri":pending["callback"],
            "code_verifier":pending["verifier"], "resource":BASE + "/mcp"}, timeout=15))
        access = token["access_token"]
        if not isinstance(access, str) or not access:
            raise ValueError()
        expires = timezone.now() + timedelta(seconds=int(token.get("expires_in", 2592000)))
        CorosMCPConnection.objects.update_or_create(athlete=athlete, defaults={"client_id":pending["client"],
            "access_token":access, "refresh_token":token.get("refresh_token", ""),
            "expires_at":expires, "consented_at":timezone.now()})
    except (requests.RequestException, ValueError, KeyError, TypeError, OverflowError):
        return render(request, "core/coros_mcp.html", {"error":"COROS authorization failed. Please reconnect."})
    return redirect("coros_mcp")


@login_required
@require_POST
def coros_mcp_disconnect(request):
    athlete = _athlete_user(request)
    if not athlete:
        return HttpResponseForbidden()
    connection = CorosMCPConnection.objects.filter(athlete=athlete).first()
    if connection:
        try:
            requests.post(BASE + "/oauth2/revoke", data={"token":connection.refresh_token or connection.access_token,
                "client_id":connection.client_id}, timeout=10)
        except requests.RequestException:
            pass
        connection.delete()
    return redirect("coros_mcp")


def _rpc(connection, payload, session=None):
    headers = {"Authorization":"Bearer " + connection.access_token,
        "Accept":"application/json, text/event-stream", "MCP-Protocol-Version":"2025-03-26"}
    if session:
        headers["Mcp-Session-Id"] = session
    response = requests.post(BASE + "/mcp", json=payload, headers=headers, timeout=20)
    response.raise_for_status()
    if len(response.content) > 2_000_000:
        raise ValueError()
    if response.status_code == 202 or not response.content:
        return {}, session
    if "text/event-stream" in response.headers.get("Content-Type", ""):
        values = [json.loads(line[5:].strip()) for line in response.text.splitlines() if line.startswith("data:")]
        result = next(value for value in values if value.get("id") == payload.get("id"))
    else:
        result = response.json()
    if result.get("error"):
        raise ValueError()
    return result, response.headers.get("Mcp-Session-Id", session)


@login_required
@require_POST
def coros_mcp_preview(request):
    athlete = _athlete_user(request)
    if not athlete:
        return HttpResponseForbidden()
    connection = CorosMCPConnection.objects.filter(athlete=athlete).first()
    if not connection:
        return redirect("coros_mcp")
    try:
        session = _start_session(connection)
        preview = _text(_tool(connection, session, "querySportRecords", {"limit":20}))
        return render(request, "core/coros_mcp.html", {"connected":True, "preview":preview,
            "activities":_activity_rows(preview, request, connection), "preview_loaded":True})
    except (requests.RequestException, ValueError, KeyError, TypeError, StopIteration, OverflowError):
        return render(request, "core/coros_mcp.html", {"connected":True,
            "error":"COROS could not retrieve activities. Try again or reconnect your account."})


@login_required
@require_POST
def coros_mcp_import(request):
    athlete = _athlete_user(request)
    if not athlete:
        return HttpResponseForbidden()
    connection = CorosMCPConnection.objects.filter(athlete=athlete).first()
    if not connection:
        return redirect("coros_mcp")
    try:
        selection = signing.loads(request.POST.get("selection", ""), salt="coros-fit-selection", max_age=3600)
        if (selection.get("user") != request.user.pk or selection.get("athlete") != athlete.pk
                or selection.get("connection") != connection.pk):
            raise ValueError()
    except (signing.BadSignature, ValueError, TypeError, AttributeError):
        return HttpResponseForbidden("Refresh the activities list before importing.")
    try:
        existing = GarminActivity.objects.filter(athlete=athlete, parsed_data__coros_mcp_label=selection["label"]).first()
        if existing:
            return render(request, "core/coros_mcp.html", {"connected":True, "notice":"This activity was already imported.", "saved_activity":existing})
        session = _start_session(connection)
        activity, created = import_activity(connection, session, selection["label"], selection["sport"])
        return render(request, "core/coros_mcp.html", {"connected":True, "saved_activity":activity,
            "notice":"FIT imported. Open the activity date in Athlete Diary to analyze it." if created else "This FIT file was already imported."})
    except PermissionError:
        return HttpResponseForbidden("COROS connection is no longer enabled.")
    except (requests.RequestException, ValueError, KeyError, TypeError, StopIteration, OverflowError, OSError, struct.error):
        return render(request, "core/coros_mcp.html", {"connected":True,
            "error":"The COROS FIT file could not be imported. Refresh the list and try again. The activity may still be processing, or the daily COROS download limit may have been reached."})


def import_activity(connection, session, label, sport):
    """Shared manual/background import, including quota and permission checks."""
    now = timezone.now()
    with transaction.atomic():
        current = CorosMCPConnection.objects.select_for_update().filter(pk=connection.pk,
            athlete__coros_connection_enabled=True).first()
        if not current:
            raise PermissionError()
        existing = GarminActivity.objects.filter(athlete_id=current.athlete_id, parsed_data__coros_mcp_label=label).first()
        if existing:
            return existing, False
        if not current.download_window_at or current.download_window_at <= now - timedelta(hours=24):
            current.download_window_at, current.download_requests = now, 0
        if current.download_requests >= 50:
            raise ValueError("COROS download quota reached")
        current.download_requests += 1
        current.save(update_fields=["download_window_at", "download_requests"])
    content = _tool(connection, session, "queryActivityFitFileDownloadUrls", {
        "labelId":label, "sportType":sport, "limit":1})
    text = _text(content)
    candidates = re.findall(r'https://[^\s<>"\\]+', text + "\n" + json.dumps(content.get("structuredContent", {})))
    urls = list(dict.fromkeys(value.rstrip(").,]'") for value in candidates))
    if len(urls) != 1:
        raise ValueError("COROS returned no single FIT download.")
    raw = _download_fit(urls[0])
    parsed = parse_fit(raw)
    name = "coros-" + label + ".fit"
    parsed["file_name"] = name
    parsed["human"]["file_name"] = name
    parsed.update(coros_mcp_label=label, coros_mcp_sport=sport)
    with transaction.atomic():
        athlete = Athlete.objects.select_for_update().get(pk=connection.athlete_id)
        if not athlete.coros_connection_enabled or not CorosMCPConnection.objects.filter(pk=connection.pk, athlete=athlete).exists():
            raise PermissionError()
        activity, created = GarminActivity.objects.get_or_create(athlete=athlete,
            file_hash=hashlib.sha256(raw).hexdigest(), defaults={"activity_start":parsed["human"].get("activity_start"),
                "original_filename":name, "raw_file":raw, "parsed_data":json_safe_fit_data(parsed)})
        if not created and not (activity.parsed_data or {}).get("coros_mcp_label"):
            activity.parsed_data = dict(activity.parsed_data or {}, coros_mcp_label=label, coros_mcp_sport=sport)
            activity.save(update_fields=["parsed_data"])
        if created:
            CorosMCPConnection.objects.filter(pk=connection.pk).update(last_import_at=timezone.now())
    return activity, created
