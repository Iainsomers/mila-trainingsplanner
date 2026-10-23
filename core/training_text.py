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
    """Split Main text on top-level ``//``, ``+`` or block ``-`` separators.

    A plus, double slash or hyphen inside parentheses belongs to the
    repeated-set expression and is therefore preserved as part of that
    expression.  At the top level a hyphen is a separator only when its right
    side starts a new distance/repetition expression; this keeps text such as
    ``Z1-Z2`` and time ranges intact.
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
        if depth == 0 and char == "-":
            left = value[start:index].strip()
            right = value[index + 1:].lstrip()
            right_starts_distance = re.match(
                r"(?:\d+\s*(?:x|\*|×)\s*)?\d+(?:[.,]\d+)?\s*(?:km|k|m)\b",
                right,
                re.IGNORECASE,
            )
            left_has_distance = re.search(
                r"\d+(?:[.,]\d+)?\s*(?:km|k|m)\b",
                left,
                re.IGNORECASE,
            )
            if left and left_has_distance and right_starts_distance:
                parts.append(left)
                start = index + 1
                index += 1
                continue
        index += 1

    final_part = value[start:].strip()
    if final_part:
        parts.append(final_part)
    return parts
