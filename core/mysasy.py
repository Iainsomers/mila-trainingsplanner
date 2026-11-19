"""Small, bounded mySASY client. No health values or credentials are logged."""
import math
import json
from datetime import timedelta
from urllib.parse import urlsplit

import requests
from django.conf import settings
from django.db.models import F
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from core.models import MySasyMonthlyUsage


class MySasyError(Exception):
    pass


def configured():
    return bool(settings.MYSASY_CLIENT_SECRET and str(settings.MYSASY_APPLICATION_ID).isdigit())


def measurement_response(token):
    """Return the complete measurements response, including undocumented fields."""
    if not configured():
        raise MySasyError("mySASY is not configured yet.")
    month = timezone.now().strftime("%Y-%m")
    MySasyMonthlyUsage.objects.get_or_create(month=month)
    if not MySasyMonthlyUsage.objects.filter(
        month=month, requests__lt=settings.MYSASY_MONTHLY_REQUEST_LIMIT
    ).update(requests=F("requests") + 1):
        raise MySasyError("The monthly mySASY request limit has been reached. Please try next month.")
    today = timezone.localdate()
    try:
        with requests.get(
            "https://api.mysasy.com/myapi/v1/measurements",
            headers={"X-Client-Secret": settings.MYSASY_CLIENT_SECRET, "X-Auth-Token": token},
            params={"dateFrom": (today - timedelta(days=30)).isoformat(), "dateTo": today.isoformat()},
            timeout=15, allow_redirects=False, stream=True,
        ) as response:
            if response.status_code != 200:
                raise MySasyError("mySASY could not retrieve the measurements. Please try again later or reconnect.")
            chunks = []
            size = 0
            for chunk in response.iter_content(65536):
                size += len(chunk)
                if size > 1024 * 1024:
                    raise ValueError()
                chunks.append(chunk)
            data = json.loads(b"".join(chunks))
        if not isinstance(data, list) or len(data) > 1000:
            raise ValueError()
        return data
    except (requests.RequestException, ValueError, TypeError, OverflowError):
        raise MySasyError("mySASY could not retrieve the measurements. Please try again later.") from None


def diagnostic_response(token):
    """Preserve fields for coach inspection while removing credential values."""
    data = measurement_response(token)
    secrets = [value for value in (token, settings.MYSASY_CLIENT_SECRET) if value]

    def clean(value, depth=0):
        if depth > 20:
            return "[nested data omitted]"
        if isinstance(value, dict):
            result = {}
            for key, item in value.items():
                normalized = "".join(c for c in key.lower() if c.isalnum())
                name = clean(key, depth + 1)
                result[name] = "[redacted]" if any(part in normalized for part in (
                    "token", "secret", "password", "authorization", "cookie", "apikey"
                )) or normalized in {"auth", "credential", "credentials"} else clean(item, depth + 1)
            return result
        if isinstance(value, list):
            return [clean(item, depth + 1) for item in value]
        if isinstance(value, str):
            for secret in secrets:
                value = value.replace(secret, "[redacted]")
            return value
        if isinstance(value, float) and not math.isfinite(value):
            return None
        return value

    return clean(data)


def measurements(token):
    data = measurement_response(token)
    try:
        rows = []
        for item in data:
            if not isinstance(item, dict):
                raise ValueError()
            stamp = item.get("timestamp")
            if not isinstance(stamp, str) or len(stamp) > 40 or not parse_datetime(stamp):
                raise ValueError()
            row = {"timestamp": stamp}
            for key in ("compensation", "totalPower", "consumption", "replenishment", "functionalAge"):
                value = item.get(key)
                row[key] = value if type(value) in (int, float) and math.isfinite(value) else None
            link = item.get("detailUrl", "")
            parsed = urlsplit(link) if isinstance(link, str) else None
            row["detailUrl"] = link if parsed and parsed.scheme == "https" and parsed.netloc == "client.mysasy.com" else ""
            rows.append(row)
        return sorted(rows, key=lambda row: row["timestamp"], reverse=True)
    except (requests.RequestException, ValueError, TypeError, OverflowError):
        raise MySasyError("mySASY could not retrieve the measurements. Please try again later.") from None
