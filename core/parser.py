# core/parser.py
import re
from dataclasses import dataclass
from typing import Optional


@dataclass
class ParseResult:
    ok: bool
    zone: Optional[int] = None
    distance_m: Optional[int] = None
    duration_s: Optional[int] = None
    reps: Optional[int] = None
    rep_distance_m: Optional[int] = None
    special: Optional[str] = None
    t_type: Optional[str] = None
    message: str = ""
    raw: str = ""


_T_RE = re.compile(r"\b(?:TM|THM|T4|T\s*(10|5|3|15|8|800|1500|3000|5000|10000))\b", re.IGNORECASE)
_ZONE_RE = re.compile(r"Z\s*([1-6])\b", re.IGNORECASE)

_DISTANCE_RE = re.compile(r"\b(\d+(?:[.,]\d+)?)\s*(km|k|m)\b", re.IGNORECASE)
_REP_RE = re.compile(r"\b(\d+)\s*(?:x|\*|×)\s*(\d+(?:[.,]\d+)?)\s*(m|km|k)\b", re.IGNORECASE)

_SET_RE = re.compile(r"\b(\d+)\s*(?:x|\*|×)\s*\(\s*([^)]+?)\s*\)", re.IGNORECASE)
_SET_DISTANCE_TOKEN_RE = re.compile(r"^\s*(\d+(?:[.,]\d+)?)\s*(km|k|m)\s*$", re.IGNORECASE)


def _to_meters(value: float, unit: str) -> float:
    unit = unit.lower()
    if unit == "m":
        return value
    if unit in ("k", "km"):
        return value * 1000.0
    return value


def parse_segment_text(text: str, zone_required: bool = True) -> ParseResult:
    raw = text
    s = (text or "").strip()
    if not s:
        return ParseResult(ok=False, message="Lege tekst.", raw=raw)

    zm = _ZONE_RE.search(s)
    zone = int(zm.group(1)) if zm else None

    # --- SET ---
    sm = _SET_RE.search(s)
    if sm:
        reps = int(sm.group(1))
        inner = sm.group(2) or ""
        parts = [p.strip() for p in re.split(r"\s*-\s*", inner) if p.strip()]

        dist_tokens = []
        all_dist = True
        for p in parts:
            p_clean = _ZONE_RE.sub("", p)
            p_clean = _T_RE.sub("", p_clean)
            p_clean = p_clean.strip()

            tm = _SET_DISTANCE_TOKEN_RE.match(p_clean)
            if not tm:
                all_dist = False
                break

            v = float(tm.group(1).replace(",", "."))
            u = tm.group(2).lower()
            dist_tokens.append(_to_meters(v, u))

        if all_dist:
            rep_m = int(round(sum(dist_tokens)))
            total_m = int(round(reps * rep_m))
            return ParseResult(
                ok=True,
                zone=zone,
                distance_m=total_m,
                reps=reps,
                rep_distance_m=rep_m,
                message=f"Herkend: {reps}×({inner}) → {total_m}m",
                raw=raw,
            )

    # --- REP ---
    rm = _REP_RE.search(s)
    if rm:
        reps = int(rm.group(1))
        rep_value = float(rm.group(2).replace(",", "."))
        unit = rm.group(3).lower()
        rep_m = _to_meters(rep_value, unit)
        total_m = int(round(reps * rep_m))
        return ParseResult(
            ok=True,
            zone=zone,
            distance_m=total_m,
            reps=reps,
            rep_distance_m=int(round(rep_m)),
            message=f"Herkend: {reps}×{int(round(rep_m))}m → {total_m}m",
            raw=raw,
        )

    # --- SINGLE DISTANCE (FIX) ---
    dm = _DISTANCE_RE.search(s)
    if dm:
        value = float(dm.group(1).replace(",", "."))
        unit = dm.group(2).lower()
        dist_m = int(round(_to_meters(value, unit)))
        return ParseResult(
            ok=True,
            zone=zone,
            distance_m=dist_m,
            reps=1,
            rep_distance_m=dist_m,
            message=f"Herkend: {int(dist_m)}m",
            raw=raw,
        )

    return ParseResult(
        ok=False,
        zone=zone,
        message="Niet herkend",
        raw=raw,
    )
