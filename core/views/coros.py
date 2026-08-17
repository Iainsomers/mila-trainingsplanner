import hashlib
import json
import os
import secrets

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from core.models import CorosWorkoutPush


def _coros_result(result, message, status=200):
    return JsonResponse({"message": message, "result": result}, status=status)


@require_GET
def coros_status_view(request):
    """Public health check required by the COROS partner application."""
    return JsonResponse({"status": "ok", "service": "mila-coros-workout-receiver"})


@csrf_exempt
@require_POST
def coros_workout_push_view(request):
    """Receive idempotent workout summary pushes as specified by COROS 5.3."""
    expected_client = (os.environ.get("COROS_PUSH_CLIENT") or "").strip()
    expected_secret = (os.environ.get("COROS_PUSH_SECRET") or "").strip()
    if not expected_client or not expected_secret:
        return _coros_result("1001", "COROS push credentials are not configured", status=503)

    supplied_client = (request.headers.get("client") or "").strip()
    supplied_secret = (request.headers.get("secret") or "").strip()
    if not (
        secrets.compare_digest(supplied_client, expected_client)
        and secrets.compare_digest(supplied_secret, expected_secret)
    ):
        return _coros_result("1002", "Invalid COROS push credentials", status=403)

    try:
        payload = json.loads(request.body.decode("utf-8")) if request.body else {}
    except (UnicodeDecodeError, json.JSONDecodeError):
        return _coros_result("1003", "Invalid JSON payload", status=400)
    if not isinstance(payload, (dict, list)):
        return _coros_result("1003", "Invalid JSON payload", status=400)

    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    payload_hash = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    CorosWorkoutPush.objects.get_or_create(
        payload_hash=payload_hash,
        defaults={"payload": payload},
    )
    return _coros_result("0000", "ok")
