# core/parser.py
import re
from dataclasses import dataclass
from typing import Optional


@dataclass
class ParseResult:
    ok: bool
    zone: Optional[int] = None          # 1..6
    distance_m: Optional[int] = None    # totale afstand in meters
    duration_s: Optional[int] = None    # totale duur in seconden
    reps: Optional[int] = None          # bij interval
    rep_distance_m: Optional[int] = None
    special: Optional[str] = None       # RACE / IMPORTANT_RACE / STRENGTH
    message: str = ""
    raw: str = ""


# --- Special keywords (geen zone nodig) ---
_RACE_BANG_RE = re.compile(r"\brace!\b", re.IGNORECASE)
_RACE_RE = re.compile(r"\brace\b", re.IGNORECASE)         # let op: matcht ook in "race!" maar race! checken we eerst
_STRENGTH_RE = re.compile(r"\bstrength\b", re.IGNORECASE)

# --- Zone & reguliere parsing ---
_ZONE_RE = re.compile(r"Z\s*([1-6])\b", re.IGNORECASE)

_DURATION_APOS_RE = re.compile(r"(\d+)\s*['’‘´`′]", re.IGNORECASE)     # 30' / 30’ etc
_DURATION_MINWORD_RE = re.compile(r"(\d+)\s*min\b", re.IGNORECASE)     # 30 min
_DURATION_M_RE = re.compile(r"(\d+)\s*m\b", re.IGNORECASE)             # 30m  (AMBIGU met meters!)
_DURATION_HMS_RE = re.compile(r"\b(\d{1,2}):(\d{2})(?::(\d{2}))?\b")    # 45:00 / 1:15:00

_DISTANCE_RE = re.compile(r"\b(\d+(?:[.,]\d+)?)\s*(km|k|m)\b", re.IGNORECASE)

_REP_RE = re.compile(
    r"\b(\d+)\s*(?:x|\*|×)\s*(\d+(?:[.,]\d+)?)\s*(m|km|k)\b",
    re.IGNORECASE,
)

_DUR_REP_RE = re.compile(
    r"\b(\d+)\s*(?:x|\*|×)\s*(\d+)\s*(?:['’‘´`′]|min\b|m\b)",
    re.IGNORECASE,
)

# --- nested reps, bv 2*(10*400m) of 2*10*400m ---
# Fix: geen trailing \b (faalt bij afsluiten op ')'); gebruik lookahead (?=\s|$)
_NESTED_REP_DISTANCE_RE = re.compile(
    r"\b(\d+)\s*(?:x|\*|×)\s*\(?\s*(\d+)\s*(?:x|\*|×)\s*(\d+(?:[.,]\d+)?)\s*(m|km|k)\s*\)?(?=\s|$)",
    re.IGNORECASE,
)

_NESTED_DUR_REP_RE = re.compile(
    r"\b(\d+)\s*(?:x|\*|×)\s*\(?\s*(\d+)\s*(?:x|\*|×)\s*(\d+)\s*(?:['’‘´`′]|min\b|m\b)\s*\)?(?=\s|$)",
    re.IGNORECASE,
)

# --- set-notatie, bv 3*(600m-400m-300m) of 3*(4'-3'-2') ---
_SET_RE = re.compile(
    r"\b(\d+)\s*(?:x|\*|×)\s*\(\s*([^)]+?)\s*\)",
    re.IGNORECASE,
)

# Tokens (fullmatch) voor binnen de ()
_SET_DISTANCE_TOKEN_RE = re.compile(r"^\s*(\d+(?:[.,]\d+)?)\s*(km|k|m)\s*$", re.IGNORECASE)
_SET_MINUTES_TOKEN_RE = re.compile(r"^\s*(\d+)\s*['’‘´`′]\s*$", re.IGNORECASE)
_SET_MINWORD_TOKEN_RE = re.compile(r"^\s*(\d+)\s*min\s*$", re.IGNORECASE)


def parse_segment_text(text: str, zone_required: bool = True) -> ParseResult:
    """
    Parseert een segment-tekst.
    - Standaard (zone_required=True): verwacht Z1..Z6 en parsed afstand/duur.
    - zone_required=False: accepteert tekst zónder zone (handig voor 'alternative' die nu nog niet meetelt).
      In die modus wordt alleen specials herkend; anders wordt de tekst als 'ok' opgeslagen zonder parsing.
    """
    raw = text
    s = (text or "").strip()
    if not s:
        return ParseResult(ok=False, message="Lege tekst.", raw=raw)

    # -------------------------------------------------
    # 0) SPECIALS (Race / Race! / Strength) -> geen zone vereist
    # -------------------------------------------------
    if _STRENGTH_RE.search(s):
        return ParseResult(
            ok=True,
            zone=None,
            distance_m=None,
            duration_s=None,
            reps=None,
            rep_distance_m=None,
            special="STRENGTH",
            message="Herkannt: Strength (geen zone/afstand parsing nodig).",
            raw=raw,
        )

    if _RACE_BANG_RE.search(s):
        am = _DISTANCE_RE.search(s)
        if not am:
            return ParseResult(
                ok=False,
                zone=None,
                special="IMPORTANT_RACE",
                message="Herkannt: Race! maar geen afstand gevonden (bv. 5km of 5000m).",
                raw=raw,
            )
        value = float(am.group(1).replace(",", "."))
        unit = am.group(2).lower()
        total_m = int(round(_to_meters(value, unit)))
        return ParseResult(
            ok=True,
            zone=None,
            distance_m=total_m,
            duration_s=None,
            reps=1,
            rep_distance_m=None,
            special="IMPORTANT_RACE",
            message=f"Herkannt: Race! → {total_m}m",
            raw=raw,
        )

    if _RACE_RE.search(s):
        am = _DISTANCE_RE.search(s)
        if not am:
            return ParseResult(
                ok=False,
                zone=None,
                special="RACE",
                message="Herkannt: Race maar geen afstand gevonden (bv. 5km of 5000m).",
                raw=raw,
            )
        value = float(am.group(1).replace(",", "."))
        unit = am.group(2).lower()
        total_m = int(round(_to_meters(value, unit)))
        return ParseResult(
            ok=True,
            zone=None,
            distance_m=total_m,
            duration_s=None,
            reps=1,
            rep_distance_m=None,
            special="RACE",
            message=f"Herkannt: Race → {total_m}m",
            raw=raw,
        )

    # -------------------------------------------------
    # 1) Zone parsing (optioneel)
    # -------------------------------------------------
    zm = _ZONE_RE.search(s)
    if not zm and zone_required:
        return ParseResult(
        ok=False,
        message="Geen zone gevonden (verwacht bv. Z2).",
        raw=raw,
    )

    zone = zm.group(1) if zm else None


    zone = int(zm.group(1))

    # -------------------------------------------------
    # 1a) nested reps
    # -------------------------------------------------
    nd = _NESTED_REP_DISTANCE_RE.search(s)
    if nd:
        outer = int(nd.group(1))
        inner = int(nd.group(2))
        rep_value = float(nd.group(3).replace(",", "."))
        unit = nd.group(4).lower()

        rep_m = float(_to_meters(rep_value, unit))
        total_reps = outer * inner
        total_m = int(round(total_reps * rep_m))

        return ParseResult(
            ok=True,
            zone=zone,
            distance_m=total_m,
            duration_s=None,
            reps=total_reps,
            rep_distance_m=int(round(rep_m)),
            special=None,
            message=f"Herkannt: {outer}×({inner}×{int(round(rep_m))}m) in Z{zone} → {total_m}m",
            raw=raw,
        )

    ndr = _NESTED_DUR_REP_RE.search(s)
    if ndr:
        outer = int(ndr.group(1))
        inner = int(ndr.group(2))
        minutes = int(ndr.group(3))

        if minutes > 300:
            return ParseResult(
                ok=False,
                zone=zone,
                special=None,
                message="Waarde lijkt meters (te groot voor minuten). Gebruik bij minuten bv 30' of 30 min.",
                raw=raw,
            )

        total_reps = outer * inner
        total_s = total_reps * minutes * 60

        return ParseResult(
            ok=True,
            zone=zone,
            distance_m=None,
            duration_s=total_s,
            reps=total_reps,
            rep_distance_m=None,
            special=None,
            message=f"Herkannt: {outer}×({inner}×{minutes} min) in Z{zone} → {total_s}s",
            raw=raw,
        )

    # -------------------------------------------------
    # 1b) set-notatie
    # -------------------------------------------------
    sm = _SET_RE.search(s)
    if sm:
        reps = int(sm.group(1))
        inner = sm.group(2) or ""
        parts = [p.strip() for p in re.split(r"\s*-\s*", inner) if p.strip()]

        if not parts:
            return ParseResult(
                ok=False,
                zone=zone,
                message="Set-notatie gevonden, maar geen items binnen de haakjes.",
                raw=raw,
            )

        # Probeer eerst afstanden
        dist_tokens = []
        all_dist = True
        for p in parts:
            tm = _SET_DISTANCE_TOKEN_RE.match(p)
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
                duration_s=None,
                reps=reps,
                rep_distance_m=rep_m,
                special=None,
                message=f"Herkannt: {reps}×({inner}) in Z{zone} → {total_m}m",
                raw=raw,
            )

        # Probeer tijden (minuten) met ' of 'min'
        minutes_list = []
        all_min = True
        for p in parts:
            tm1 = _SET_MINUTES_TOKEN_RE.match(p)
            tm2 = _SET_MINWORD_TOKEN_RE.match(p)
            if tm1:
                minutes_list.append(int(tm1.group(1)))
            elif tm2:
                minutes_list.append(int(tm2.group(1)))
            else:
                all_min = False
                break

        if all_min:
            if any(m > 300 for m in minutes_list):
                return ParseResult(
                    ok=False,
                    zone=zone,
                    message="Minutenwaarde te groot in set-notatie. Gebruik bij afstand bv 5000m of 5km.",
                    raw=raw,
                )

            rep_minutes = sum(minutes_list)
            total_s = reps * rep_minutes * 60
            return ParseResult(
                ok=True,
                zone=zone,
                distance_m=None,
                duration_s=total_s,
                reps=reps,
                rep_distance_m=None,
                special=None,
                message=f"Herkannt: {reps}×({inner}) in Z{zone} → {total_s}s",
                raw=raw,
            )

        return ParseResult(
            ok=False,
            zone=zone,
            message="Set-notatie gevonden, maar items binnen () zijn niet herkend als afstand (m/km) of tijd (minuten met ' of 'min').",
            raw=raw,
        )

    # -------------------------------------------------
    # 2) Reps-afstand (intervalvorm) bv "6×1000m Z3"
    # -------------------------------------------------
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
            duration_s=None,
            reps=reps,
            rep_distance_m=int(round(rep_m)),
            special=None,
            message=f"Herkannt: {reps}×{int(round(rep_m))}m in Z{zone} → {total_m}m",
            raw=raw,
        )

    # -------------------------------------------------
    # 3) Reps-duur (minuten) bv "2*30'Z2"
    # -------------------------------------------------
    drm = _DUR_REP_RE.search(s)
    if drm:
        reps = int(drm.group(1))
        minutes = int(drm.group(2))

        if minutes <= 300:
            total_s = reps * minutes * 60
            return ParseResult(
                ok=True,
                zone=zone,
                duration_s=total_s,
                distance_m=None,
                reps=reps,
                rep_distance_m=None,
                special=None,
                message=f"Herkannt: {reps}×{minutes} min in Z{zone} → {total_s}s",
                raw=raw,
            )

    # -------------------------------------------------
    # 4) Afstand zonder reps (bv. "5000m Z3", "5kmZ2")
    # -------------------------------------------------
    am = _DISTANCE_RE.search(s)
    if am:
        value = float(am.group(1).replace(",", "."))
        unit = am.group(2).lower()
        total_m = int(round(_to_meters(value, unit)))
        return ParseResult(
            ok=True,
            zone=zone,
            distance_m=total_m,
            duration_s=None,
            reps=None,
            rep_distance_m=None,
            special=None,
            message=f"Herkannt: {value:g}{unit} in Z{zone} → {total_m}m",
            raw=raw,
        )

    # -------------------------------------------------
    # 5) Duur in minuten (30' / 30 min / 30m)
    # -------------------------------------------------
    dm = _DURATION_APOS_RE.search(s) or _DURATION_MINWORD_RE.search(s) or _DURATION_M_RE.search(s)
    if dm:
        minutes = int(dm.group(1))

        if minutes > 300:
            return ParseResult(
                ok=False,
                zone=zone,
                special=None,
                message="Waarde lijkt meters (te groot voor minuten). Gebruik bij minuten bv 30' of 30 min.",
                raw=raw,
            )

        total_s = minutes * 60
        return ParseResult(
            ok=True,
            zone=zone,
            duration_s=total_s,
            distance_m=None,
            reps=None,
            rep_distance_m=None,
            special=None,
            message=f"Herkannt: {minutes} min in Z{zone} → {total_s}s",
            raw=raw,
        )

    # -------------------------------------------------
    # 6) Duur als hh:mm:ss of mm:ss
    # -------------------------------------------------
    tm = _DURATION_HMS_RE.search(s)
    if tm:
        a = int(tm.group(1))
        b = int(tm.group(2))
        c = tm.group(3)
        if c is None:
            total_s = a * 60 + b
            return ParseResult(
                ok=True,
                zone=zone,
                duration_s=total_s,
                distance_m=None,
                reps=None,
                rep_distance_m=None,
                special=None,
                message=f"Herkannt: {a:02d}:{b:02d} in Z{zone} → {total_s}s",
                raw=raw,
            )
        else:
            h = a
            m = b
            sec = int(c)
            total_s = h * 3600 + m * 60 + sec
            return ParseResult(
                ok=True,
                zone=zone,
                duration_s=total_s,
                distance_m=None,
                reps=None,
                rep_distance_m=None,
                special=None,
                message=f"Herkannt: {h:02d}:{m:02d}:{sec:02d} in Z{zone} → {total_s}s",
                raw=raw,
            )

    return ParseResult(
        ok=False,
        zone=zone,
        special=None,
        message="Zone gevonden, maar geen duur/afstand herkend (nog).",
        raw=raw,
    )


def _to_meters(value: float, unit: str) -> float:
    unit = unit.lower()
    if unit == "m":
        return value
    if unit in ("k", "km"):
        return value * 1000.0
    return value
