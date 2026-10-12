"""Grid-convergence study for the M0 baseline (coarse 80 / medium 57 / fine 40 mm background cells, r = sqrt 2).

    HABITAT_FOAM_COEXIST=1 uv run python -m habitat.cfd.gci_study        # orchestrates; resumable

Order: waits for runs/fpm_m0_coarse (run 2) to finish AND pass every habitat.cfd.post gate (otherwise it stops and
writes results/cfd/gci_m0_BLOCKED.json); then builds + runs medium and fine (ranks chosen per run: 12 if no other
session's OpenFOAM container is running, else 2); a run that is not yet steady gets one extension from its latest
time. Finally computes the GCI (Celik et al. 2008, gci3 ported from Hardware_OSDR_review @ 97f09f5) on LOCAL
quantities taken from the final fields with one extraction routine for all meshes. Return-grille values are not
used: they are fixed by global conservation and therefore mesh-independent by construction.
"""
from __future__ import annotations

import json
import math
import re
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

from .. import ROOT, RUNS
from ..registry import build as build_registry
from . import foam, post
from .case import build as build_case, mesh_case

OUT = ROOT / "results" / "cfd"
MESHES = ("fine", "medium", "coarse")


# ----------------------------------------------------------------------------- Celik 2008 (ported unchanged)
def h_of(case: Path) -> tuple[float, int]:
    log = (case / "log.checkMesh").read_text()
    n = int(re.search(r"cells:\s+(\d+)", log).group(1))
    v = float(re.search(r"Total volume = ([0-9.eE+-]+)", log).group(1).rstrip("."))
    return (v / n) ** (1 / 3), n


def gci3(phi, h):
    """phi, h ordered fine, medium, coarse."""
    p1, p2, p3 = phi
    h1, h2, h3 = h
    r21, r32 = h2 / h1, h3 / h2
    e21, e32 = p2 - p1, p3 - p2
    out = {"phi_fine": p1, "phi_medium": p2, "phi_coarse": p3, "r21": r21, "r32": r32}
    if abs(e21) < 1e-14 * max(1, abs(p1)) or abs(e32) < 1e-14 * max(1, abs(p1)):
        out.update({"p": float("nan"), "phi_ext": p1, "gci_fine_pct": 0.0, "convergence": "converged to round-off"})
        return out
    ratio = e32 / e21
    s = math.copysign(1, ratio)
    p = 2.0
    for _ in range(200):
        q = math.log((r21 ** p - s) / (r32 ** p - s)) if (r21 ** p - s) > 0 and (r32 ** p - s) > 0 else 0.0
        p_new = abs(math.log(abs(ratio)) + q) / math.log(r21)
        if abs(p_new - p) < 1e-10:
            break
        p = p_new
    phi_ext = (r21 ** p * p1 - p2) / (r21 ** p - 1)
    ea = abs((p1 - p2) / p1) if p1 else float("nan")
    out.update({"p": p, "phi_ext": phi_ext, "e_a21_pct": 100 * ea,
                "e_ext21_pct": 100 * abs((phi_ext - p1) / phi_ext) if phi_ext else float("nan"),
                "gci_fine_pct": 100 * 1.25 * ea / (r21 ** p - 1),
                "convergence": "oscillatory" if ratio < 0 else "monotonic"})
    return out


# ----------------------------------------------------------------------------- local quantities
def quantities(case: Path) -> dict:
    """Same extraction for every mesh: volume-weighted zone means and interpolated probes from the final fields."""
    import pyvista as pv
    from .slices import load
    meta = json.loads((case / "case_meta.json").read_text())
    Ts = meta["physics"]["supply_T_K"]
    vol, it = load(case)
    vol = vol.compute_cell_sizes(length=False, area=False, volume=True)
    c = vol.cell_centers().points
    V = vol.cell_data["Volume"]
    T, co2, h2o, age = (np.asarray(vol.cell_data[k]) for k in ("T", "dCO2", "dH2O", "AoA"))
    U = np.linalg.norm(np.asarray(vol.cell_data["U"]), axis=1)
    _, parts = build_registry()
    P = {p.id: p for p in parts}

    def box_mean(pid, f):
        lo, hi = np.array(P[pid].lo) / 1000, np.array(P[pid].hi) / 1000
        m = np.all((c >= lo) & (c <= hi), axis=1)
        return float(np.sum(f[m] * V[m]) / np.sum(V[m]))

    q = {"domain:T_excess_K": float(np.sum((T - Ts) * V) / V.sum()),
         "domain:AoA_s": float(np.sum(age * V) / V.sum()),
         "domain:dCO2_ppm": float(np.sum(co2 * V) / V.sum()),
         "occupied:U_mean_m_s": float(np.sum(U[c[:, 2] < 1.8] * V[c[:, 2] < 1.8]) / V[c[:, 2] < 1.8].sum())}
    for pid in ("crew_1", "crew_2"):
        q[f"{pid}:dCO2_ppm"] = box_mean(pid, co2)
        q[f"{pid}:T_excess_K"] = box_mean(pid, T - Ts)
    q["nft_canopy:T_excess_K"] = box_mean("nft_canopy", T - Ts)
    q["nft_canopy:dH2O_mmol_mol"] = box_mean("nft_canopy", h2o)
    # probes along the aisle at seated/standing head height (interpolated, point data)
    pts_vol = vol.cell_data_to_point_data()
    y_aisle = (P["crew_1"].lo[1] + P["crew_1"].hi[1]) / 2000
    for x in (2.0, 5.0, 8.0):
        s = pv.PolyData(np.array([[x, y_aisle, 1.1]])).sample(pts_vol)
        q[f"aisle_x{x:g}:T_excess_K"] = float(s.point_data["T"][0] - Ts)
        q[f"aisle_x{x:g}:dCO2_ppm"] = float(s.point_data["dCO2"][0])
        q[f"aisle_x{x:g}:U_m_s"] = float(np.linalg.norm(s.point_data["U"][0]))
    return {"iteration": it, "quantities": q}


# ----------------------------------------------------------------------------- orchestration
def status(case: Path) -> str:
    return (case / "STATUS").read_text().strip() if (case / "STATUS").exists() else ""


def wait_done(case: Path, poll: float = 60.0) -> bool:
    while True:
        s = status(case)
        if s.startswith("DONE"):
            return True
        if s.startswith("FAILED"):
            return False
        if s.startswith("RUNNING"):
            pid = int(s.split()[1])
            try:
                import os
                os.kill(pid, 0)
            except OSError:
                return False
        time.sleep(poll)


def ranks() -> int:
    return 2 if foam.foreign_containers() else 12


def gate_ok(case: Path) -> tuple[bool, dict]:
    r = post.run(case)
    return r["pass"], r


def run_case(mesh: str) -> Path:
    case = RUNS / f"fpm_m0_{mesh}"
    if status(case).startswith("DONE"):
        return case
    np_ = ranks()
    case = build_case(mesh, np_)
    print(f"[gci] {mesh}: built with {np_} ranks", flush=True)
    r = subprocess.run([sys.executable, "-m", "habitat.cfd.run", str(case), "--np", str(np_), "--mesh"])
    if r.returncode != 0:
        raise RuntimeError(f"{mesh} run failed: {status(case)}")
    ok, g = gate_ok(case)
    if not g["gates"].get("steady", False):          # one extension from the latest time
        cd = case / "system" / "controlDict"
        cd.write_text(re.sub(r"endTime\s+\d+;", "endTime 8000;", cd.read_text()))
        foam.run(case, ["decomposePar -force -latestTime", "par:buoyantSimpleFoam", "reconstructPar -latestTime"],
                 nprocs=np_)
    return case


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    coarse = RUNS / "fpm_m0_coarse"
    print("[gci] waiting for run 2 (coarse) ...", flush=True)
    if not wait_done(coarse):
        (OUT / "gci_m0_BLOCKED.json").write_text(json.dumps({"reason": f"run 2 did not finish: {status(coarse)}"}))
        return 1
    ok, g = gate_ok(coarse)
    if not ok:
        (OUT / "gci_m0_BLOCKED.json").write_text(json.dumps({"reason": "run 2 failed its gates", "gates": g["gates"],
                                                             "rel_err": g["rel_err"]}, indent=1, default=float))
        print("[gci] BLOCKED: run 2 did not pass its gates", flush=True)
        return 1
    cases = {"coarse": coarse}
    for mesh in ("medium", "fine"):
        cases[mesh] = run_case(mesh)
    gates = {m: gate_ok(c)[1]["gates"] for m, c in cases.items()}
    Q = {m: quantities(c) for m, c in cases.items()}
    H = {m: h_of(c) for m, c in cases.items()}
    rows = {}
    for k in Q["fine"]["quantities"]:
        rows[k] = gci3([Q[m]["quantities"][k] for m in MESHES], [H[m][0] for m in MESHES])
    res = {"meshes": {m: {"h_m": H[m][0], "cells": H[m][1], "iteration": Q[m]["iteration"]} for m in MESHES},
           "gates": gates, "gci": rows,
           "all_gates_pass": all(all(v.values()) for v in gates.values())}
    (OUT / "gci_m0.json").write_text(json.dumps(res, indent=1, default=float) + "\n")
    lines = ["# GCI — M0 baseline (Celik et al. 2008)\n\n",
             "| Mesh | h (mm) | cells |\n|---|---|---|\n"] + \
            [f"| {m} | {H[m][0] * 1000:.1f} | {H[m][1]:,} |\n" for m in MESHES] + \
            ["\n| Quantity | fine | medium | coarse | p | GCI_fine % | convergence |\n|---|---|---|---|---|---|---|\n"] + \
            [f"| {k} | {r['phi_fine']:.4g} | {r['phi_medium']:.4g} | {r['phi_coarse']:.4g} | {r['p']:.2f} | "
             f"{r['gci_fine_pct']:.2f} | {r['convergence']} |\n" for k, r in rows.items()] + \
            ["\nAll mesh gates pass: " + str(res["all_gates_pass"]) + "\n"]
    (OUT / "gci_m0.md").write_text("".join(lines))
    print("".join(lines), flush=True)
    return 0


if __name__ == "__main__":
    import os
    import traceback
    st = OUT / "gci_m0.STATUS"
    OUT.mkdir(parents=True, exist_ok=True)
    st.write_text(f"RUNNING {os.getpid()}\n")
    try:
        rc = main()
        st.write_text("DONE\n" if rc == 0 else "FAILED: blocked (see gci_m0_BLOCKED.json)\n")
    except BaseException as e:  # noqa: BLE001
        (OUT / "gci_m0.STATUS.log").write_text(traceback.format_exc())
        st.write_text(f"FAILED: {type(e).__name__}: {e}\n")
        raise
    sys.exit(rc)
