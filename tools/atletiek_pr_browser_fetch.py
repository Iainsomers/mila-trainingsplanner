"""
Fetch Atletiek.nu athlete PRs through a real local browser.

This is intentionally a local helper, not a Render feature. Atletiek.nu may show
Cloudflare/Turnstile to scripts, while a real browser session can pass it.

Usage:
  python tools/atletiek_pr_browser_fetch.py https://www.atletiek.nu/atleet/profiel/876749/#records

First-time setup:
  pip install playwright
  python -m playwright install chromium
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SESSION_DIR = ROOT / ".local" / "atletiek-browser-profile"


def _setup_django() -> None:
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "mila.settings")
    import django

    django.setup()


def _clean_profile_text(value: str) -> str:
    text = str(value or "").replace("\xa0", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def records_section_from_profile_text(page_text: str) -> str:
    text = _clean_profile_text(page_text)
    start_match = re.search(r"(?im)^persoonlijke records\b", text)
    if not start_match:
        start_match = re.search(r"(?im)^records\b", text)
    if not start_match:
        return ""

    section = text[start_match.end():].strip()
    stop_patterns = [
        r"(?im)^\[?toon alle records\]?\b",
        r"(?im)^resultaten\b",
        r"(?im)^statistieken\b",
        r"(?im)^inschrijvingen\b",
        r"(?im)^external links\b",
    ]
    stop_positions = [
        match.start()
        for pattern in stop_patterns
        for match in [re.search(pattern, section)]
        if match
    ]
    if stop_positions:
        section = section[: min(stop_positions)].strip()
    return section


def normalise_records_for_mila(records_text: str) -> dict:
    _setup_django()
    from core.views.coach import _parse_match_athlete_records

    return _parse_match_athlete_records(records_text)


def mila_paste_text(records: dict) -> str:
    lines = []
    for item in sorted(records.values(), key=lambda record: str(record.get("event") or "").lower()):
        event = str(item.get("event") or "").strip()
        value = str(item.get("value") or "").strip().replace(".", ",")
        date = str(item.get("date") or "").strip()
        if not event or not value:
            continue
        lines.append(event)
        lines.append(f"{value}\t{date}".rstrip())
    return "\n".join(lines)


def fetch_text_with_browser(url: str, timeout_ms: int = 120_000) -> str:
    try:
        from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise RuntimeError(
            "Playwright is not installed in this venv.\n"
            "Run:\n"
            "  pip install playwright\n"
            "  python -m playwright install chromium"
        ) from exc

    SESSION_DIR.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as playwright:
        context = playwright.chromium.launch_persistent_context(
            str(SESSION_DIR),
            headless=False,
            viewport={"width": 1400, "height": 1000},
        )
        page = context.pages[0] if context.pages else context.new_page()
        page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)

        records_locator = page.get_by_text("Persoonlijke records", exact=False).first
        try:
            records_locator.wait_for(timeout=timeout_ms)
        except PlaywrightTimeoutError:
            print(
                "Could not see 'Persoonlijke records' yet. "
                "If a browser check is visible, complete it in the opened browser.",
                file=sys.stderr,
            )
            records_locator.wait_for(timeout=timeout_ms)

        text = page.locator("body").inner_text(timeout=timeout_ms)
        context.close()
        return text


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Fetch Atletiek.nu PRs with a real browser.")
    parser.add_argument("url", nargs="?", help="Atletiek.nu athlete profile URL.")
    parser.add_argument("--text-file", help="Parse a saved page text file instead of opening a browser.")
    parser.add_argument("--json", action="store_true", help="Print parsed records as JSON.")
    args = parser.parse_args(argv)

    if args.text_file:
        page_text = Path(args.text_file).read_text(encoding="utf-8")
    elif args.url:
        page_text = fetch_text_with_browser(args.url)
    else:
        parser.error("Provide a profile URL or --text-file.")

    records_text = records_section_from_profile_text(page_text)
    if not records_text:
        print("No 'Persoonlijke records' section found.")
        return 2

    records = normalise_records_for_mila(records_text)
    if args.json:
        print(json.dumps(records, ensure_ascii=False, indent=2))
    else:
        print("=== Records section ===")
        print(records_text)
        print("\n=== Mila paste text ===")
        print(mila_paste_text(records))
        print(f"\nParsed {len(records)} record(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
