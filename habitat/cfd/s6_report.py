"""S6 payload-siting report: where does the bioreactor rack's off-gas CO2 end up for each route?

    uv run python -m habitat.cfd.s6_report runs/fpm_s6_coarse

All three routes release the same CO2 (10 tubes x the ledger rate) into ONE converged flow field as separate
passive tracers, so they differ only in WHERE the CO2 is released. Results are reported as
  * ppm above supply air at each zone / probe, and
  * enrichment factor = local excess / flux-weighted return excess (the well-mixed value: 1 = no better than
    mixing the whole room; > 1 = the CO2 is concentrated there).
Gates: each tracer's return-grille balance closes within 1 % (the solver delivered what the case released), plus
the general energy / species / age / steadiness gates of habitat.cfd.post.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from .. import ROOT  # noqa: E402
from . import post  # noqa: E402

TOL = 0.01


META: dict = {}


def _last(cols, arr, name):
    """Last value (steady) or time mean over the averaging window (transient)."""
    return post.window_value(None, META, arr[:, 0], post._col(cols, arr, name))


def probe_values(case: Path, field: str) -> list[float]:
    files = sorted((case / "postProcessing" / "probes").glob(f"*/{field}"), key=lambda p: float(p.parent.name))
    rows = []
    for i, f in enumerate(files):                      # stitch restarts, dropping the re-run overlap (as post._dat)
        t_next = float(files[i + 1].parent.name) if i + 1 < len(files) else float("inf")
        rows += [r for r in ([float(v) for v in ln.split()] for ln in f.read_text().splitlines()
                             if ln.strip() and not ln.startswith("#")) if r[0] < t_next]
    rows = np.array(rows)
    return [post.window_value(None, META, rows[:, 0], rows[:, k]) for k in range(1, rows.shape[1])]


def run(case: Path) -> dict:
    meta = json.loads((case / "case_meta.json").read_text())
    META.clear(); META.update(meta)
    ph = meta["physics"]
    mdot = ph["mdot_kg_s"]
    routes = list(meta["tracers"])
    cr, ar = post._dat(case, "flux_hvac_return")
    rows, gates = {}, {}
    ret = {}
    for r in routes:
        total = sum(z["mol_s"] for z in meta["tracers"][r])
        ret[r] = _last(cr, ar, f"tr_{r}")
        got = mdot / ph["M_air"] * ret[r] * 1e-6
        gates[f"balance_{r}"] = abs(got - total) / total < TOL
    for zn in ("nft_canopy", "crew_1", "crew_2", "workbench_zone"):
        c, a = post._dat(case, f"zone_{zn}")
        rows[f"zone:{zn}"] = {r: _last(c, a, f"tr_{r}") for r in routes} | {"crew_dCO2": _last(c, a, "dCO2")}
    names = list(meta["probes"])
    pv = {r: probe_values(case, f"tr_{r}") for r in routes}
    pcrew = probe_values(case, "dCO2")
    for k, nm in enumerate(names):
        rows[f"probe:{nm}"] = {r: pv[r][k] for r in routes} | {"crew_dCO2": pcrew[k]}
    for row in rows.values():
        for r in routes:
            row[f"factor_{r}"] = row[r] / ret[r] if ret[r] else float("nan")
    base = post.run(case)            # general gates (mass, energy, crew CO2/H2O, age identity, steadiness)
    gates.update({f"general_{k}": v for k, v in base["gates"].items()})

    out = ROOT / "results" / "cfd"
    out.mkdir(parents=True, exist_ok=True)
    # table
    lines = [f"# S6 payload siting — {case.name} (ledger {meta['ledger_digest']})\n",
             f"Same bioreactor CO₂ release in every route: {meta['tracer_info']['tubes']} tubes × "
             f"{meta['tracer_info']['co2_per_tube_mol_s'] * 86400 * 44.0095:.2f} g/day. The photobioreactor can take "
             f"{meta['tracer_info']['sparge_capacity_units']} units' off-gas (sparger max flow); the rest vent in the bay.\n",
             f"Well-mixed (return-grille) excess: " + ", ".join(f"{r} {ret[r]:.3f} ppm" for r in routes) + ".\n",
             "\n| Location | " + " | ".join(f"{r} ppm (×mixed)" for r in routes) + " | crew-generated ΔCO₂ ppm |\n",
             "|---|" + "---|" * (len(routes) + 1) + "\n"]
    for loc, row in rows.items():
        lines.append(f"| {loc} | " + " | ".join(f"{row[r]:.3f} (×{row['factor_' + r]:.2f})" for r in routes)
                     + f" | {row['crew_dCO2']:.1f} |\n")
    lines.append("\nGates: " + ", ".join(f"{k} {'PASS' if v else 'FAIL'}" for k, v in gates.items()) + "\n")
    (out / f"{case.name}_siting.md").write_text("".join(lines))
    # bar chart of enrichment factors
    locs = list(rows)
    fig, ax = plt.subplots(figsize=(12, 4.2))
    w = 0.8 / len(routes)
    for i, r in enumerate(routes):
        ax.bar(np.arange(len(locs)) + i * w, [rows[l][f"factor_{r}"] for l in locs], w, label=f"off-gas → {r}")
    ax.axhline(1.0, color="k", lw=0.8, ls="--", label="well mixed")
    ax.set_xticks(np.arange(len(locs)) + w, [l.split(":")[1] for l in locs], rotation=30, ha="right", fontsize=8)
    ax.set_ylabel("bioreactor CO₂ excess / well-mixed value")
    ax.set_yscale("log")
    ax.set_title(f"S6: where the bioreactor off-gas goes ({case.name}; screening mesh, placeholder HVAC)", fontsize=10)
    ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(out / f"{case.name}_siting_factors.png", dpi=130)
    plt.close(fig)
    res = {"case": case.name, "ledger_digest": meta["ledger_digest"], "return_ppm": ret, "rows": rows,
           "tracer_info": meta["tracer_info"], "gates": gates, "pass": all(gates.values())}
    (out / f"{case.name}_siting.json").write_text(json.dumps(res, indent=1, default=float) + "\n")
    return res


def maps(case: Path, z_m: float | None = None) -> Path:
    """Plan maps of the three route tracers (log scale) at canopy mid-height."""
    from .slices import load
    meta = json.loads((case / "case_meta.json").read_text())
    vol, it = load(case)
    vol = vol.cell_data_to_point_data()
    if z_m is None:
        z_m = meta["probes"]["nft_canopy_1"][2] / 1000
    sl = vol.slice(normal="z", origin=(0, 0, z_m)).triangulate()
    faces = sl.faces.reshape(-1, 4)[:, 1:]
    routes = list(meta["tracers"])
    keys = {r: (f"tr_{r}Mean" if f"tr_{r}Mean" in sl.point_data else f"tr_{r}") for r in routes}  # time mean if transient
    vals = {r: np.log10(np.clip(sl.point_data[keys[r]], 1e-3, None)) for r in routes}
    # one colour range for all routes, from the data (fixed decades washed out a field spanning < 1 decade)
    lo, hi = np.percentile(np.concatenate(list(vals.values())), [1, 99])
    (x0, x1), (y0, y1) = (sl.points[:, 0].min(), sl.points[:, 0].max()), (sl.points[:, 1].min(), sl.points[:, 1].max())
    fig, axs = plt.subplots(len(routes), 1, figsize=(12, 1.1 + len(routes) * 12 * (y1 - y0) / (x1 - x0) * 1.25),
                            layout="constrained")
    for ax, r in zip(np.atleast_1d(axs), routes):
        tc = ax.tripcolor(sl.points[:, 0], sl.points[:, 1], faces, vals[r], shading="gouraud", cmap="viridis",
                          vmin=lo, vmax=hi)
        ax.set_aspect("equal"); ax.set_ylabel("y (m)", fontsize=8)
        ax.set_title(f"off-gas → {r}: bioreactor CO₂ excess over supply air at z = {z_m:.2f} m", fontsize=9)
    np.atleast_1d(axs)[-1].set_xlabel("x from the door end (m)", fontsize=8)
    fig.colorbar(tc, ax=axs, label="log10 ppm", shrink=0.9)
    fig.suptitle(f"{case.name}: time-averaged plan slices; same release in each route (data: {case.name} fields)",
                 fontsize=9)
    p = ROOT / "results" / "cfd" / f"{case.name}_siting_maps.png"
    fig.savefig(p, dpi=110)
    plt.close(fig)
    return p


if __name__ == "__main__":
    c = Path(sys.argv[1])
    r = run(c)
    print((ROOT / "results" / "cfd" / f"{c.name}_siting.md").read_text())
    print("maps:", maps(c))
    sys.exit(0 if r["pass"] else 1)
