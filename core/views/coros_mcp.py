"""Per-athlete COROS EU MCP OAuth and a read-only activity preview."""
import base64
import hashlib
import json
import secrets
from datetime import timedelta
from urllib.parse import urlencode

import requests
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from core.models import CorosMCPConnection
from core.views.oura import _athlete_user

BASE = "https://mcpeu.coros.com"
PENDING = "coros_mcp_pending"


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
        if connection.expires_at and connection.expires_at <= timezone.now() + timedelta(seconds=60):
            token = _json(requests.post(BASE + "/oauth2/token", data={"grant_type":"refresh_token",
                "refresh_token":connection.refresh_token, "client_id":connection.client_id}, timeout=15))
            connection.access_token = token["access_token"]
            connection.refresh_token = token.get("refresh_token", connection.refresh_token)
            connection.expires_at = timezone.now() + timedelta(seconds=int(token.get("expires_in", 2592000)))
            connection.save()
        _, session = _rpc(connection, {"jsonrpc":"2.0", "id":1, "method":"initialize", "params":{
            "protocolVersion":"2025-03-26", "capabilities":{}, "clientInfo":{"name":"MiLa Planner", "version":"1.0"}}})
        _rpc(connection, {"jsonrpc":"2.0", "method":"notifications/initialized"}, session)
        result, _ = _rpc(connection, {"jsonrpc":"2.0", "id":2, "method":"tools/call",
            "params":{"name":"querySportRecords", "arguments":{"limit":20}}}, session)
        content = result.get("result", {})
        if content.get("isError"):
            raise ValueError()
        preview = "\n\n".join(item.get("text", "") for item in content.get("content", []) if item.get("type") == "text")
        return render(request, "core/coros_mcp.html", {"connected":True, "preview":preview})
    except (requests.RequestException, ValueError, KeyError, TypeError, StopIteration, OverflowError):
        return render(request, "core/coros_mcp.html", {"connected":True,
            "error":"COROS could not retrieve activities. Try again or reconnect your account."})
