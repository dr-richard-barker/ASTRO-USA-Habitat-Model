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
# ladder shifted coarser by user decision (2026-10-12): the 80/57/40 mm transient ladder needs ~110 h here.
# GCI roles (fine, medium, coarse) -> mesh names
LADDER = {"fine": "medium", "medium": "coarse", "coarse": "xcoarse"}       # 57 / 80 / 113 mm
MESHES = tuple(LADDER)


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
    f = lambda k: np.asarray(vol.cell_data[f"{k}Mean"] if f"{k}Mean" in vol.cell_data.keys() else vol.cell_data[k])  # noqa
    T, co2, h2o, age = (f(k) for k in ("T", "dCO2", "dH2O", "AoA"))
    U = np.linalg.norm(f("U"), axis=1)
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
        g = lambda k: s.point_data[f"{k}Mean"] if f"{k}Mean" in s.point_data.keys() else s.point_data[k]  # noqa
        q[f"aisle_x{x:g}:T_excess_K"] = float(g("T")[0] - Ts)
        q[f"aisle_x{x:g}:dCO2_ppm"] = float(g("dCO2")[0])
        q[f"aisle_x{x:g}:U_m_s"] = float(np.linalg.norm(g("U")[0]))
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
    """Steady initialisation (1500 iterations; only a starting field) then the 3-flush transient run."""
    from .transient import free_cpus, make as make_tr, solve as solve_tr
    tr = RUNS / f"fpm_m0_{mesh}_tr"
    if status(tr).startswith("DONE"):
        return tr
    steady = RUNS / f"fpm_m0_{mesh}"
    if not status(steady).startswith("DONE"):
        n = free_cpus()
        steady = build_case(mesh, n, end_iter=1500)
        print(f"[gci] {mesh}: steady initialisation on {n} ranks", flush=True)
        r = subprocess.run([sys.executable, "-m", "habitat.cfd.run", str(steady), "--np", str(n), "--mesh"])
        if r.returncode != 0:
            raise RuntimeError(f"{mesh} steady initialisation failed: {status(steady)}")
    n = free_cpus()
    tr = make_tr(steady, nprocs=n)
    (tr / "STATUS").write_text("RUNNING 0\n")
    print(f"[gci] {mesh}: transient on {n} ranks", flush=True)
    solve_tr(tr, n)
    (tr / "STATUS").write_text("DONE\n")
    return tr


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    base = RUNS / "fpm_m0_coarse_tr"
    print("[gci] waiting for the coarse transient run ...", flush=True)
    if not wait_done(base):
        (OUT / "gci_m0_BLOCKED.json").write_text(json.dumps({"reason": f"coarse transient did not finish: {status(base)}"}))
        return 1
    ok, g = gate_ok(base)
    if not ok:
        (OUT / "gci_m0_BLOCKED.json").write_text(json.dumps({"reason": "coarse transient failed its gates",
                                                             "gates": g["gates"], "rel_err": g["rel_err"]},
                                                            indent=1, default=float))
        print("[gci] BLOCKED: coarse transient did not pass its gates", flush=True)
        return 1
    (OUT / "gci_m0_BLOCKED.json").unlink(missing_ok=True)
    cases = {"coarse": base}
    for mesh in ("xcoarse", "medium"):
        cases[mesh] = run_case(mesh)
    gates = {m: gate_ok(c)[1]["gates"] for m, c in cases.items()}
    Q = {m: quantities(c) for m, c in cases.items()}
    H = {m: h_of(c) for m, c in cases.items()}
    order = [LADDER[r] for r in MESHES]                       # fine, medium, coarse roles -> mesh names
    rows = {k: gci3([Q[m]["quantities"][k] for m in order], [H[m][0] for m in order]) for k in Q["coarse"]["quantities"]}
    res = {"ladder": LADDER, "meshes": {m: {"h_m": H[m][0], "cells": H[m][1], "time": Q[m]["iteration"]} for m in order},
           "gates": gates, "gci": rows, "all_gates_pass": all(all(v.values()) for v in gates.values()),
           "note": "time-averaged transient solutions; GCI 'fine' level is the 57 mm mesh"}
    (OUT / "gci_m0.json").write_text(json.dumps(res, indent=1, default=float) + "\n")
    lines = ["# GCI — M0 baseline, time-averaged transient (Celik et al. 2008)\n\n",
             "Ladder shifted coarser by decision (57 / 80 / 113 mm); the 'fine' level is the 57 mm mesh.\n\n",
             "| Role | Mesh | h (mm) | cells |\n|---|---|---|---|\n"] + \
            [f"| {r} | {LADDER[r]} | {H[LADDER[r]][0] * 1000:.1f} | {H[LADDER[r]][1]:,} |\n" for r in MESHES] + \
            ["\n| Quantity | 57 mm | 80 mm | 113 mm | p | GCI_fine % | convergence |\n|---|---|---|---|---|---|---|\n"] + \
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
