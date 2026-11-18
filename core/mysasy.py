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


def measurements(token):
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
