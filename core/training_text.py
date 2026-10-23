"""Helpers for separating independently prescribed Main segments."""

import re


def normalize_watch_main_text(text):
    """Make Watch A/B display notation acceptable to the planner parser.

    Watch summaries may include a pace after every zone and use ``+`` inside
    repeated sets.  The planner's set grammar uses ``-`` between distance
    items and treats the pace as display-only, so normalize those details
    before the text is saved as a training slot.
    """
    value = str(text or "").strip()
    if not value:
        return value
    value = re.sub(r"(Z[1-6])\s*\(\s*\d{1,3}:\d{2}\s*/?\s*(?:km)?\s*\)", r"\1", value, flags=re.IGNORECASE)
    value = re.sub(r"\s*\+\s*", " - ", value)
    return value


def split_main_segments(text):
    """Split Main text on top-level ``//`` or ``+`` separators.

    A plus or double slash inside parentheses belongs to the repeated-set
    expression and is therefore preserved as part of that expression.
    """
    value = str(text or "")
    parts = []
    start = 0
    depth = 0
    index = 0

    while index < len(value):
        char = value[index]
        if char == "(":
            depth += 1
            index += 1
            continue
        if char == ")":
            depth = max(0, depth - 1)
            index += 1
            continue

        if depth == 0 and value.startswith("//", index):
            part = value[start:index].strip()
            if part:
                parts.append(part)
            index += 2
            start = index
            continue
        if depth == 0 and char == "+":
            part = value[start:index].strip()
            if part:
                parts.append(part)
            index += 1
            start = index
            continue
        index += 1

    final_part = value[start:].strip()
    if final_part:
        parts.append(final_part)
    return parts
