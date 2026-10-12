"""Post-process a steady FPM case and apply the M0 CFD gates.

    uv run python -m habitat.cfd.post runs/fpm_m0_coarse

Gates (all from solver output on disk; nothing typed in):
  * mass:   |mdot_supply + mdot_return| / mdot  < 0.1 %
  * energy: mdot*cp*(T_return - T_supply) vs registry heat (case_meta)        within 1 %
  * CO2:    mdot/M_air*dCO2_return*1e-6 vs CO2 source                       within 1 %
  * H2O:    same for dH2O (mmol/mol)                                        within 1 %
  * age:    flux-weighted AoA at return vs rho0*V_mesh/mdot (Sandberg)      within 1 %
  * steady: over the last 500 iterations, return T within +/-0.05 K and dCO2 within +/-5 ppm
            (review-amended plan, item 7)
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

TOL = 0.01


def _dat(case: Path, fo: str) -> tuple[list[str], np.ndarray]:
    """Read a function-object .dat series (concatenating restarts)."""
    files = sorted((case / "postProcessing" / fo).glob("*/*.dat"), key=lambda p: float(p.parent.name))
    if not files:
        raise FileNotFoundError(f"{case}/postProcessing/{fo}: no data")
    cols, rows = None, []
    for f in files:
        for ln in f.read_text().splitlines():
            if ln.startswith("#"):
                if "Time" in ln:
                    cols = ln.lstrip("#").split()
                continue
            if ln.strip():
                rows.append([float(x) for x in ln.split()])
    return cols, np.array(rows)


def _col(cols, arr, name):
    for i, c in enumerate(cols):
        if c == name or c.startswith(f"{name}(") or c.endswith(f"({name})") or re.fullmatch(rf"\w+\({name}\)", c):
            return arr[:, i]
    raise KeyError(f"{name} not in {cols}")


def mesh_volume(case: Path) -> float:
    m = re.search(r"Total volume = ([0-9.eE+-]+)", (case / "log.checkMesh").read_text())
    return float(m.group(1))


def run(case: Path) -> dict:
    meta = json.loads((case / "case_meta.json").read_text())
    ph, src = meta["physics"], meta["sources_total"]
    cr, ar = _dat(case, "flux_hvac_return")
    cs, ms = _dat(case, "mflow_hvac_supply")
    cr2, mr = _dat(case, "mflow_hvac_return")
    it = ar[:, 0]
    Tr, dco2, dh2o, age = (_col(cr, ar, n) for n in ("T", "dCO2", "dH2O", "AoA"))
    md_s, md_r = _col(cs, ms, "phi")[-1], _col(cr2, mr, "phi")[-1]
    mdot = ph["mdot_kg_s"]
    V = mesh_volume(case)
    got = {
        "mass_imbalance": abs(md_s + md_r) / mdot,
        "heat_removed_W": mdot * ph["cp"] * (Tr[-1] - ph["supply_T_K"]),
        "co2_removed_mol_s": mdot / ph["M_air"] * dco2[-1] * 1e-6,
        "h2o_removed_mol_s": mdot / ph["M_air"] * dh2o[-1] * 1e-3,
        "age_return_s": age[-1],
    }
    want = {"heat_removed_W": src["heat_W"], "co2_removed_mol_s": src["co2_mol_s"],
            "h2o_removed_mol_s": src["h2o_mol_s"], "age_return_s": ph["rho0"] * V / mdot}
    gates = {"mass": got["mass_imbalance"] < 1e-3}
    for k, w in want.items():
        gates[k] = abs(got[k] - w) / abs(w) < TOL
    last = it >= it[-1] - 500
    steady = {"iterations": int(it[-1]), "window": int(last.sum()),
              "return_T_span_K": float(np.ptp(Tr[last])), "return_dCO2_span_ppm": float(np.ptp(dco2[last]))}
    # the plan's +/-0.05 K and +/-5 ppm are half-spans, so the allowed peak-to-peak span is twice that
    gates["steady"] = bool(it[-1] >= 1000 and steady["return_T_span_K"] <= 2 * 0.05
                           and steady["return_dCO2_span_ppm"] <= 2 * 5)

    fig, axs = plt.subplots(1, 4, figsize=(15, 3.2))
    for ax, y, w, lab in ((axs[0], Tr - 273.15, ph["supply_T_K"] - 273.15 + src["heat_W"] / (mdot * ph["cp"]), "return T (°C)"),
                          (axs[1], dco2, src["co2_mol_s"] * ph["M_air"] / mdot * 1e6, "return ΔCO₂ (ppm)"),
                          (axs[2], dh2o, src["h2o_mol_s"] * ph["M_air"] / mdot * 1e3, "return ΔH₂O (mmol/mol)"),
                          (axs[3], age, want["age_return_s"], "return age of air (s)")):
        ax.plot(it, y, lw=1.2)
        ax.axhline(w, color="k", ls="--", lw=0.8, label="balance target")
        ax.set_title(lab, fontsize=10); ax.set_xlabel("iteration")
    axs[0].legend(fontsize=8)
    fig.suptitle(f"{case.name}: convergence of return-grille quantities toward their global balances", fontsize=10)
    fig.tight_layout()
    out = case.parent.parent / "results" / "cfd"
    out.mkdir(parents=True, exist_ok=True)
    fig.savefig(out / f"{case.name}_convergence.png", dpi=130)
    plt.close(fig)
    res = {"case": case.name, "ledger_digest": meta["ledger_digest"], "cells": None, "mesh_volume_m3": V,
           "got": got, "want": want,
           "rel_err": {k: (got[k] - w) / w for k, w in want.items()}, "steady": steady, "gates": gates,
           "pass": all(gates.values())}
    m = re.search(r"cells:\s+(\d+)", (case / "log.checkMesh").read_text())
    res["cells"] = int(m.group(1)) if m else None
    (out / f"{case.name}_gates.json").write_text(json.dumps(res, indent=1) + "\n")
    return res


if __name__ == "__main__":
    r = run(Path(sys.argv[1]))
    print(json.dumps({k: r[k] for k in ("rel_err", "steady", "gates", "pass")}, indent=1))
    sys.exit(0 if r["pass"] else 1)
