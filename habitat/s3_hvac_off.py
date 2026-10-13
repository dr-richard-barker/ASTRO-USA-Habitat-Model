"""S3 HVAC-off, door closed: how fast does CO2 build up? A zero-dimensional (well-mixed) model.

    uv run python -m habitat.s3_hvac_off

Well-mixed room of air volume V (the CFD mesh's fluid volume: the living space without equipment or the attic),
N crew exhaling CO2 at BVAD's awake rate G each, outdoor air leaking in at lambda air changes per hour:

    dC/dt = N G / n_air - lambda (C - C_out),     C(0) = C_out
    C(t)  = C_out + (N G / (n_air lambda)) (1 - exp(-lambda t))      (lambda > 0;  linear growth when lambda = 0)

with n_air = p V / (R T) moles of air, C in mole fraction. Starting at the outdoor level is the best case (a room
that was already occupied starts higher). Plants are left out: their CO2 uptake is not modelled yet (light budget).
Only CO2 is assessed: the room's temperature rise depends on the heat stored in walls and equipment, which is unknown.

Outputs: results/s3_hvac_off.json / .md / .png.
"""
from __future__ import annotations

import json
import math

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from . import ROOT  # noqa: E402
from .provenance import Ledger  # noqa: E402

R, M_CO2 = 8.314462618, 44.0095          # J/mol/K (exact), g/mol
OUT = ROOT / "results"


def co2(t_h: np.ndarray, n_crew: int, ach: float, V: float, T: float, p: float, G_g_min: float, c_out: float):
    """CO2 (ppm) after t_h hours."""
    n_air = p * V / (R * T)
    g = n_crew * G_g_min / M_CO2 / 60 / n_air * 1e6 * 3600          # ppm per hour
    if ach == 0:
        return c_out + g * t_h
    return c_out + g / ach * (1 - np.exp(-ach * t_h))


def time_to(limit: float, n_crew: int, ach: float, V, T, p, G, c_out) -> float | None:
    n_air = p * V / (R * T)
    g = n_crew * G / M_CO2 / 60 / n_air * 1e6 * 3600
    rise = limit - c_out
    if ach == 0:
        return rise / g
    if g / ach <= rise:                                               # steady state stays below the limit
        return None
    return -math.log(1 - rise * ach / g) / ach


def run() -> dict:
    L = Ledger()
    gates = json.loads((OUT / "cfd" / "fpm_m0_coarse_tr_gates.json").read_text())
    V = gates["mesh_volume_m3"]
    T = L.num("scenario_m0.hvac.setpoint_T", "C") + 273.15
    p = 101325.0
    G = L.num("crew.awake.co2", "g/min")
    c_out = L.num("scenario_s3.co2_outdoor", "ppm")
    lim = L.num("scenario_s3.co2_limit_osha_pel", "ppm")
    cases = []
    for n in L.val("scenario_s3.crew_cases"):
        for ach in L.val("scenario_s3.infiltration_ach"):
            t = time_to(lim, n, ach, V, T, p, G, c_out)
            steady = None if ach == 0 else c_out + (co2(np.array([1e6]), n, ach, V, T, p, G, c_out)[0] - c_out)
            cases.append({"crew": n, "ach": ach, "hours_to_limit": None if t is None else round(t, 2),
                          "steady_ppm": None if steady is None else round(float(steady), 0),
                          "rise_ppm_per_h_initial": round(float(co2(np.array([1.0]), n, 0.0, V, T, p, G, c_out)[0] - c_out), 1)})
    return {"ledger_digest": L.digest(), "air_volume_m3": V, "volume_source": "results/cfd/fpm_m0_coarse_tr_gates.json",
            "T_K": T, "co2_per_crew_g_min": G, "co2_outdoor_ppm": c_out, "limit_ppm": lim, "cases": cases}


def write(res: dict) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "s3_hvac_off.json").write_text(json.dumps(res, indent=1) + "\n")
    lines = [f"# S3 HVAC off, door closed: CO₂ build-up (ledger {res['ledger_digest']})\n\n",
             f"Well-mixed {res['air_volume_m3']:.1f} m³ of air (CFD fluid volume), crew at BVAD's awake "
             f"{res['co2_per_crew_g_min']} g CO₂/min each, starting from outdoor air ({res['co2_outdoor_ppm']} ppm, NOAA). "
             f"Limit: OSHA PEL {res['limit_ppm']:.0f} ppm, an 8-hour time-weighted average, so reaching it is a "
             "warning level, not an instant hazard. Plants (CO₂ uptake not modelled) and temperature (thermal mass "
             "unknown) are left out.\n\n",
             "| crew | infiltration (ACH) | initial rise (ppm/h) | hours to 5000 ppm | steady level (ppm) |\n|---|---|---|---|---|\n"]
    for c in res["cases"]:
        lines.append(f"| {c['crew']} | {c['ach']:g} | {c['rise_ppm_per_h_initial']:.0f} | "
                     f"{c['hours_to_limit'] if c['hours_to_limit'] is not None else 'never'} | "
                     f"{c['steady_ppm'] if c['steady_ppm'] is not None else 'keeps rising'} |\n")
    (OUT / "s3_hvac_off.md").write_text("".join(lines))
    fig, ax = plt.subplots(figsize=(8, 4.2), layout="constrained")
    t = np.linspace(0, 12, 400)
    for c in res["cases"]:
        y = co2(t, c["crew"], c["ach"], res["air_volume_m3"], res["T_K"], 101325.0, res["co2_per_crew_g_min"],
                res["co2_outdoor_ppm"])
        ax.plot(t, y, ls="-" if c["crew"] == 6 else "--", label=f"{c['crew']} crew, {c['ach']:g} ACH")
    ax.axhline(res["limit_ppm"], color="k", lw=0.8)
    ax.text(0.2, res["limit_ppm"] * 1.02, "OSHA PEL (8-h TWA)", fontsize=8)
    ax.set_xlabel("hours after the HVAC stops (door closed)"); ax.set_ylabel("CO₂ (ppm)")
    ax.set_ylim(0, 12000); ax.legend(fontsize=7, ncol=2)
    ax.set_title("S3: CO₂ build-up with the HVAC off (well-mixed 0-D model; plants not included)", fontsize=9)
    fig.savefig(OUT / "s3_hvac_off.png", dpi=120)
    plt.close(fig)


if __name__ == "__main__":
    r = run()
    write(r)
    print((OUT / "s3_hvac_off.md").read_text())
