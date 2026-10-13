"""CFD-informed sensor placement: where does one wall-mounted sensor best represent the air the crew breathe?

    uv run python -m habitat.cfd.sensors runs/fpm_m0_coarse_tr [runs/fpm_s2_coarse_tr ...]

For every case given (time-averaged transient runs that PASSED their gates; others are refused), candidate sensor
points are laid along the long walls and the attic partition at the ledger's mount heights, `wall_offset` off the
lining. Points inside equipment are dropped. Each candidate's time-mean T, CO2 and H2O excess are compared with the
occupied-zone volume mean (the reference) of the same case:
    T error in K; CO2 and H2O errors in % of the occupied-zone excess over supply air.
A candidate's score is its WORST error over all cases, so the ranking favours positions that stay representative
when occupancy and airflow change. 
Outputs: results/cfd/sensor_placement.json / .md / .png. Settings: ledger/sensors.yaml.
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
from ..provenance import Ledger  # noqa: E402

QTY = (("T", "T (K)", "abs"), ("dCO2", "CO₂ (%)", "rel"), ("dH2O", "H₂O (%)", "rel"))
OUT = ROOT / "results" / "cfd"


def clearance(pts: np.ndarray, L: Ledger) -> tuple[np.ndarray, list[str]]:
    """Distance (m) from each candidate to the nearest part in the exclusion layers, and that part's id."""
    from ..registry import build
    _, parts = build(L)
    near = [p for p in parts if p.layer in L.val("sensors.exclusion_layers") and p.cfd_role != "ignore"]
    d = np.full(len(pts), np.inf); who = [""] * len(pts)
    for p in near:
        lo, hi = np.array(p.lo) / 1000, np.array(p.hi) / 1000
        dist = np.linalg.norm(np.maximum(0, np.maximum(lo - pts, pts - hi)), axis=1)
        for i in np.where(dist < d)[0]:
            who[i] = p.id
        d = np.minimum(d, dist)
    return d, who


def excluded(pts: np.ndarray, L: Ledger, scenario: str = "m0") -> tuple[np.ndarray, list[str]]:
    """Mask of candidates near parts whose real gas exchange the CFD does not model (ledger sensors.exclusion_*)."""
    from ..registry import build
    _, parts = build(L, scenario=scenario)
    m = L.num("sensors.exclusion_margin", "m")
    near = [p for p in parts if p.layer in L.val("sensors.exclusion_layers") and p.cfd_role != "ignore"]
    mask = np.zeros(len(pts), bool)
    for p in near:
        lo, hi = np.array(p.lo) / 1000 - m, np.array(p.hi) / 1000 + m
        mask |= np.all((pts >= lo) & (pts <= hi), axis=1)
    return mask, sorted(p.id for p in near)


def candidates(lo, hi, L: Ledger) -> tuple[np.ndarray, list[str]]:
    off, step = L.num("sensors.wall_offset", "m"), L.num("sensors.spacing", "m")
    pts, wall = [], []
    for z in L.val("sensors.mount_heights"):
        for x in np.arange(lo[0] + step, hi[0] - step / 2, step):
            pts += [[x, lo[1] + off, z], [x, hi[1] - off, z]]
            wall += ["wall y=0 (battery / work side)", "wall y=max (hydroponic / Mycoponics side)"]
        for y in np.arange(lo[1] + step, hi[1] - step / 2, step):
            pts.append([hi[0] - off, y, z]); wall.append("attic partition")
    return np.array(pts), wall


def case_fields(case: Path):
    import pyvista as pv
    from .slices import load
    meta = json.loads((case / "case_meta.json").read_text())
    if not meta.get("transient"):
        raise ValueError(f"{case.name}: not a time-averaged transient run")
    gates = json.loads((OUT / f"{case.name}_gates.json").read_text())
    if not gates.get("pass"):
        raise ValueError(f"{case.name}: did not pass its gates; refusing to place sensors from it")
    vol, it = load(case)
    vol = vol.compute_cell_sizes(length=False, area=False, volume=True)
    for f, *_ in QTY:
        vol.cell_data[f] = vol.cell_data[f + "Mean"]
    return meta, vol, pv


def score(cases: list[Path]) -> dict:
    L = Ledger()
    z0, z1 = L.val("sensors.occupied_zone_z")
    per_case, pts, walls = {}, None, None
    for case in cases:
        meta, vol, pv = case_fields(case)
        lo, hi = np.array(vol.bounds[0::2]), np.array(vol.bounds[1::2])
        if pts is None:
            pts, walls = candidates(lo, hi, L)
        c = vol.cell_centers().points
        occ = (c[:, 2] >= z0) & (c[:, 2] <= z1)
        V = vol.cell_data["Volume"][occ]
        ref = {f: float(np.sum(vol.cell_data[f][occ] * V) / V.sum()) for f, *_ in QTY}
        pv_vol = vol.cell_data_to_point_data()
        s = pv.PolyData(pts).sample(pv_vol)
        valid = np.asarray(s.point_data["vtkValidPointMask"]).astype(bool)
        err = {}
        for f, _, kind in QTY:
            v = np.asarray(s.point_data[f], float)
            e = v - ref[f] if kind == "abs" else 100 * (v - ref[f]) / ref[f]
            err[f] = np.where(valid, e, np.nan)
        per_case[case.name] = {"ref": ref, "err": err, "valid": valid}
    near, near_ids = excluded(pts, L)
    valid_all = np.all([d["valid"] for d in per_case.values()], axis=0) & ~near
    worst = {f: np.nanmax(np.abs(np.stack([d["err"][f] for d in per_case.values()])), axis=0) for f, *_ in QTY}
    # combined rank: worst error of each quantity normalised by that quantity's best achievable worst error
    norm = np.stack([worst[f] / np.nanmin(np.where(valid_all, worst[f], np.nan)) for f, *_ in QTY])
    combined = np.where(valid_all, norm.max(axis=0), np.nan)
    order = [int(i) for i in np.argsort(np.where(np.isnan(combined), np.inf, combined)) if valid_all[i]]
    clr, who = clearance(pts, L)
    rows = [{"x_m": round(float(pts[i, 0]), 2), "y_m": round(float(pts[i, 1]), 2), "z_m": float(pts[i, 2]),
             "wall": walls[i], **{f"worst_{f}": round(float(worst[f][i]), 3) for f, *_ in QTY},
             "combined": round(float(combined[i]), 3), "clearance_m": round(float(clr[i]), 2),
             "nearest_living_part": who[i]} for i in order]
    return {"cases": list(per_case), "ledger_digest": L.digest(), "n_candidates": int(len(pts)),
            "n_valid": int(valid_all.sum()), "n_excluded_near_living_systems": int(near.sum()), "excluded_parts": near_ids, "references": {k: v["ref"] for k, v in per_case.items()},
            "ranked": rows, "pts": pts, "walls": walls, "worst": worst, "valid": valid_all}


def write(res: dict) -> Path:
    OUT.mkdir(parents=True, exist_ok=True)
    top = res["ranked"][:8]
    lines = [f"# Sensor placement — {len(res['cases'])} case(s): {', '.join(res['cases'])}\n\n",
             f"Ledger {res['ledger_digest']}. {res['n_valid']} of {res['n_candidates']} wall positions are usable: "
             f"outside equipment in every case and more than the exclusion margin from parts whose gas exchange the "
             f"CFD does not model ({res['n_excluded_near_living_systems']} dropped near: {', '.join(res['excluded_parts'])}). "
             "In these runs CO₂ and H₂O both come only from the crew, so their errors coincide; plant and fungal "
             "gas exchange will change the picture near the growing systems. Error = sensor reading minus the occupied-zone volume mean of the same case "
             "(T in K; CO₂ and H₂O in % of the occupied-zone excess over supply air); each position's WORST case "
             "across the runs is shown. Coarse mesh, placeholder HVAC: a screening ranking, to be confirmed by "
             "measurement.\n\n",
             "| rank | wall | along the wall (m) | height (m) | worst T err (K) | worst CO₂ err (%) | worst H₂O err (%) | "
             "clearance to nearest plant / water / payload part |\n",
             "|---|---|---|---|---|---|---|---|\n"]
    for k, r in enumerate(top, 1):
        along = f"y = {r['y_m']:.2f}" if "attic" in r["wall"] else f"x = {r['x_m']:.2f}"
        lines.append(f"| {k} | {r['wall']} | {along} | {r['z_m']:.1f} | {r['worst_T']:.2f} | "
                     f"{r['worst_dCO2']:.1f} | {r['worst_dH2O']:.1f} | {r['clearance_m']:.2f} m ({r['nearest_living_part']}) |\n")
    (OUT / "sensor_placement.md").write_text("".join(lines))
    js = {k: v for k, v in res.items() if k not in ("pts", "walls", "worst", "valid")}
    (OUT / "sensor_placement.json").write_text(json.dumps(js, indent=1) + "\n")
    # figure: worst-case error along each wall at each mount height
    pts, worst, valid = res["pts"], res["worst"], res["valid"]
    wall_names = sorted(set(res["walls"]))
    fig, axs = plt.subplots(len(QTY), len(wall_names), figsize=(15, 8), sharey="row", layout="constrained",
                            gridspec_kw={"width_ratios": [1 if "attic" in w else 4 for w in wall_names]})
    for row, (f, lab, _) in enumerate(QTY):
        for col, w in enumerate(wall_names):
            ax = axs[row, col]
            for z in sorted(set(pts[:, 2])):
                m = np.array([res["walls"][i] == w and pts[i, 2] == z for i in range(len(pts))])
                xv = pts[m, 1] if "attic" in w else pts[m, 0]
                yv = np.where(valid[m], worst[f][m], np.nan)          # NaN breaks the line across excluded stretches
                ax.plot(xv, yv, ".-", ms=3, lw=0.8, label=f"z = {z:.1f} m")
            if "attic" not in w:
                ax.set_xlim(0, float(pts[:, 0].max()) + 0.25)    # whole wall, so excluded stretches show as gaps
            if row == 0:
                ax.set_title(w, fontsize=9)
            if col == 0:
                ax.set_ylabel(f"worst |error| {lab}", fontsize=8)
            if row == len(QTY) - 1:
                ax.set_xlabel("y (m)" if "attic" in w else "x from the door end (m)", fontsize=8)
            ax.tick_params(labelsize=7)
    axs[0, 0].legend(fontsize=7)
    fig.suptitle(f"Wall sensor representativeness vs the occupied-zone mean, worst case over: {', '.join(res['cases'])} "
                 "(gaps = inside equipment or near plants / water culture / Mycoponics / payloads)", fontsize=9)
    p = OUT / "sensor_placement.png"
    fig.savefig(p, dpi=110)
    plt.close(fig)
    viewer_overlay(res)
    return p


def viewer_overlay(res: dict, n: int = 5) -> Path:
    """Top-n positions as coloured spheres for the viewer (same model->glTF mapping as the CFD slices)."""
    import trimesh
    from .slices import to_gltf_frame
    cols = matplotlib.colormaps["viridis"](np.linspace(0.9, 0.2, n))
    parts = []
    for k, r in enumerate(res["ranked"][:n]):
        m = trimesh.creation.icosphere(subdivisions=2, radius=0.06 - 0.006 * k)
        m.apply_translation(to_gltf_frame(np.array([[r["x_m"], r["y_m"], r["z_m"]]]))[0])
        m.visual.vertex_colors = (np.tile(cols[k], (len(m.vertices), 1)) * 255).astype(np.uint8)
        parts.append(m)
    glb = ROOT / "vr" / "web" / "assets" / "sensor_positions.glb"
    trimesh.util.concatenate(parts).export(glb)
    man = ROOT / "vr" / "web" / "assets" / "overlays.json"
    items = [o for o in (json.loads(man.read_text()) if man.exists() else []) if o["file"] != glb.name]
    where = "; ".join(f"{k}. {r['wall'].split(' (')[0]} {'y' if 'attic' in r['wall'] else 'x'} = "
                      f"{r['y_m'] if 'attic' in r['wall'] else r['x_m']:.2f} m, z {r['z_m']:.1f} m"
                      for k, r in enumerate(res["ranked"][:n], 1))
    items.append({"file": glb.name, "label": f"suggested sensor positions (top {n})",
                  "note": f"Wall sensor positions most representative of the occupied zone, worst case over "
                          f"{', '.join(res['cases'])} (largest sphere = best): {where}. Screening result; "
                          "positions near plants, water culture, Mycoponics and payloads excluded."})
    man.write_text(json.dumps(items, indent=1) + "\n")
    return glb


if __name__ == "__main__":
    r = score([Path(a) for a in sys.argv[1:]])
    write(r)
    print((OUT / "sensor_placement.md").read_text())
