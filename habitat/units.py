"""The only place unit conversions happen (ledger units -> CAD mm -> CFD m)."""
from __future__ import annotations

IN_TO_MM = 25.4          # exact, international inch (1959)
MM_TO_M = 1e-3
KJ_PER_H_TO_W = 1000.0 / 3600.0
G_PER_MIN_TO_KG_S = 1e-3 / 60.0
CFM_TO_M3_S = 0.3048 ** 3 / 60.0   # exact, international foot

_LENGTH_TO_MM = {"mm": 1.0, "m": 1000.0, "in": IN_TO_MM, "ft": 12 * IN_TO_MM}


def to_mm(value, unit: str):
    """Length (scalar or list) in `unit` -> mm."""
    f = _LENGTH_TO_MM[unit]
    return [v * f for v in value] if isinstance(value, (list, tuple)) else value * f


def to_m(value, unit: str):
    v = to_mm(value, unit)
    return [x * MM_TO_M for x in v] if isinstance(v, list) else v * MM_TO_M


def to_W(value: float, unit: str) -> float:
    return value * {"W": 1.0, "kW": 1000.0, "kJ/h": KJ_PER_H_TO_W, "kJ/hr": KJ_PER_H_TO_W}[unit]


def to_kg_s(value: float, unit: str) -> float:
    return value * {"kg/s": 1.0, "g/min": G_PER_MIN_TO_KG_S, "g/s": 1e-3, "kg/day": 1 / 86400}[unit]


def to_m3_s(value: float, unit: str) -> float:
    return value * {"m3/s": 1.0, "L/s": 1e-3, "cfm": CFM_TO_M3_S, "m3/h": 1 / 3600}[unit]
