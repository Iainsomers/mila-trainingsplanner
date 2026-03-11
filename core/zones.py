# core/zones.py
from typing import Dict, Tuple

# -----------------------------
# Constants
# -----------------------------

# Interne vaste sprint-norm (Z6), m/s
Z6_INTERNAL_MPS = 8.5

# Default zones (fallback)
DEFAULT_ZONE_SPEED_MPS = {
    "1": 3.0,
    "2": 3.5,
    "3": 4.0,
    "4": 4.5,
    "5": 5.0,
    "6": Z6_INTERNAL_MPS,
}


# -----------------------------
# Unit helpers
# -----------------------------

def zone_unit_label(unit: str) -> str:
    return "km/h" if unit == "kmh" else "min/km"


def pace_to_mps(pace_str: str) -> float:
    """
    Expects mm:ss or m:ss
    """
    parts = pace_str.split(":")
    if len(parts) != 2:
        raise ValueError("Ongeldig tempoformaat (gebruik mm:ss).")

    minutes = int(parts[0])
    seconds = int(parts[1])
    total_seconds = minutes * 60 + seconds

    if total_seconds <= 0:
        raise ValueError("Tempo moet groter dan 0 zijn.")

    return 1000.0 / total_seconds


def kmh_to_mps(kmh_str: str) -> float:
    v = float(kmh_str.replace(",", "."))
    if v <= 0:
        raise ValueError("Snelheid moet groter dan 0 zijn.")
    return v / 3.6


def mps_to_pace_str(mps: float) -> str:
    sec = int(round(1000.0 / mps))
    return f"{sec // 60}:{sec % 60:02d}"


def mps_to_kmh_str(mps: float) -> str:
    return f"{mps * 3.6:.1f}"


# -----------------------------
# Validation + parsing
# -----------------------------

def parse_manual_zones_required(
    post_data,
    unit: str,
) -> Tuple[Dict[str, float], list, dict, dict]:
    """
    Returns:
    - zone_speed_mps dict (incl Z6)
    - errors list
    - normalized_input (strings for form)
    - other_unit_under (strings for form)
    """
    errors = []
    speeds = {}
    normalized = {}
    other_under = {}

    last_mps = None

    for z in ("1", "2", "3", "4", "5"):
        raw = (post_data.get(f"z{z}_pace") or "").strip()

        if not raw:
            errors.append(f"Z{z} is verplicht.")
            continue

        try:
            if unit == "kmh":
                mps = kmh_to_mps(raw)
                normalized[z] = raw.replace(",", ".")
                other_under[z] = f"{mps_to_pace_str(mps)} min/km"
            else:
                mps = pace_to_mps(raw)
                normalized[z] = mps_to_pace_str(mps)
                other_under[z] = f"{mps_to_kmh_str(mps)} km/h"

        except Exception as e:
            errors.append(f"Z{z}: {e}")
            continue

        if last_mps is not None and mps <= last_mps:
            errors.append("Zones moeten oplopend sneller zijn (Z1 → Z5).")

        last_mps = mps
        speeds[z] = mps

    # Always inject Z6
    speeds["6"] = Z6_INTERNAL_MPS

    return speeds, errors, normalized, other_under


# -----------------------------
# Read helpers
# -----------------------------

def ensure_full_zone_dict(speeds: Dict[str, float]) -> Dict[str, float]:
    out = dict(DEFAULT_ZONE_SPEED_MPS)
    out.update({str(k): float(v) for k, v in speeds.items()})
    out["6"] = Z6_INTERNAL_MPS
    return out


def zones_form_from_speeds(unit: str, speeds: Dict[str, float]) -> dict:
    unit = (unit or "pace").lower()
    speeds = ensure_full_zone_dict(speeds)

    out = {}
    for z in ("1", "2", "3", "4", "5"):
        mps = speeds[z]
        if unit == "kmh":
            out[f"z{z}_pace"] = mps_to_kmh_str(mps)
            out[f"z{z}_other"] = f"{mps_to_pace_str(mps)} min/km"
        else:
            out[f"z{z}_pace"] = mps_to_pace_str(mps)
            out[f"z{z}_other"] = f"{mps_to_kmh_str(mps)} km/h"
    return out
