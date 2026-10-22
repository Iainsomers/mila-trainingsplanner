"""Helpers for separating independently prescribed Main segments."""


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
