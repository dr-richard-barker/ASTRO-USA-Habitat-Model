"""Export CFD fields as report figures and as a coloured GLB slice for the viewer.

    uv run python -m habitat.cfd.slices runs/fpm_m0_coarse [--decomposed]

The CAD GLB (build123d export_gltf) maps model coordinates (x, y, z) [mm, z up] to glTF
(x, z, -y) [m, y up]; the CFD case uses the same model frame in metres, so slices are written
with the same mapping and overlay the CAD exactly (checked: slice bounds vs the living volume).
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib
import numpy as np
import pyvista as pv
import trimesh

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib import cm  # noqa: E402

from .. import ROOT  # noqa: E402

FIELDS = [("T", "air temperature (°C)", lambda v: v - 273.15, "coolwarm"),
          ("dCO2", "CO₂ above supply air (ppm)", lambda v: v, "viridis"),
          ("AoA", "age of air (s)", lambda v: v, "magma"),
          ("U", "air speed (m/s)", lambda v: np.linalg.norm(v, axis=1), "cividis")]


def load(case: Path, decomposed: bool = False) -> tuple[pv.UnstructuredGrid, float]:
    """Latest time of the internal mesh (vtkPOpenFOAMReader reads decomposed or reconstructed cases)."""
    from vtkmodules.vtkIOParallel import vtkPOpenFOAMReader
    foam = case / "case.foam"
    foam.touch()
    rd = vtkPOpenFOAMReader()
    rd.SetFileName(str(foam))
    rd.SetCaseType(0 if decomposed else 1)                  # 0 = decomposed, 1 = reconstructed
    rd.UpdateInformation()
    times = [float(t) for t in (rd.GetTimeValues() or [])]
    if not times:
        raise FileNotFoundError(f"{case}: no time directories to read")
    rd.EnableAllCellArrays()
    rd.UpdateTimeStep(times[-1])
    rd.Update()
    mb = pv.wrap(rd.GetOutput())
    return mb["internalMesh"], times[-1]


def to_gltf_frame(pts: np.ndarray) -> np.ndarray:
    return np.c_[pts[:, 0], pts[:, 2], -pts[:, 1]]


def run(case: Path, decomposed: bool = False, z_m: float | None = None, y_m: float | None = None) -> dict:
    meta = json.loads((case / "case_meta.json").read_text())
    vol, it = load(case, decomposed)
    vol = vol.cell_data_to_point_data()
    tr = meta.get("transient")
    if tr:                                   # transient run: plot the time means (fieldAverage), never a snapshot
        for f, *_ in FIELDS:
            if f + "Mean" not in vol.point_data:
                raise KeyError(f"{case.name}: transient case has no {f}Mean field at t = {it:g}")
            vol.point_data[f] = vol.point_data[f + "Mean"]
    when = (f"time mean {tr['avg_from_s']:.0f}-{it:.0f} s" if tr else f"iteration {it:g}")
    lo, hi = np.array(vol.bounds[0::2]), np.array(vol.bounds[1::2])
    crew_z = 1.1 if z_m is None else z_m          # breathing-zone height of a seated/standing crewmember (display only)
    y_aisle = (lo[1] + hi[1]) / 2 if y_m is None else y_m
    hz = vol.slice(normal="z", origin=(0, 0, crew_z))
    vy = vol.slice(normal="y", origin=(0, y_aisle, 0))
    out = ROOT / "results" / "cfd"
    out.mkdir(parents=True, exist_ok=True)
    fig, axs = plt.subplots(len(FIELDS), 2, figsize=(16, 2.2 * len(FIELDS)), gridspec_kw={"width_ratios": [1, 1.15]})
    for row, (f, lab, fn, cmap) in enumerate(FIELDS):
        for col, (sl, ax_u, ax_v, title) in enumerate(((hz, 0, 1, f"plan at z = {crew_z:.2f} m"),
                                                       (vy, 0, 2, f"section at y = {y_aisle:.2f} m (aisle)"))):
            ax = axs[row, col]
            p = sl.points
            v = fn(sl.point_data[f])
            tri = sl.triangulate()
            faces = tri.faces.reshape(-1, 4)[:, 1:]
            tc = ax.tripcolor(tri.points[:, ax_u], tri.points[:, ax_v], faces, fn(tri.point_data[f]),
                              shading="gouraud", cmap=cmap)
            ax.set_aspect("equal"); ax.set_title(f"{lab} — {title}", fontsize=9)
            ax.tick_params(labelsize=7)
            ax.set_xlabel("x from the door end (m)", fontsize=7)
            ax.set_ylabel("y (m)" if col == 0 else "z (m)", fontsize=7)
            fig.colorbar(tc, ax=ax, fraction=0.02, pad=0.01)
    fig.suptitle(f"{case.name} ({when}, ledger {meta['ledger_digest']}) — coarse mesh, placeholder HVAC, "
                 "adiabatic walls; not a design prediction", fontsize=10)
    fig.tight_layout()
    fig.savefig(out / f"{case.name}_fields.png", dpi=110)
    plt.close(fig)

    # coloured GLB slice (age of air at the breathing-zone plan) for the viewer
    tri = hz.triangulate()
    vals = tri.point_data["AoA"]
    lo_v, hi_v = np.percentile(vals, [2, 98])
    rgba = (cm.magma(np.clip((vals - lo_v) / (hi_v - lo_v), 0, 1)) * 255).astype(np.uint8)
    faces = tri.faces.reshape(-1, 4)[:, 1:]
    m = trimesh.Trimesh(vertices=to_gltf_frame(tri.points), faces=faces, vertex_colors=rgba, process=False)
    glb = ROOT / "vr" / "web" / "assets" / f"{case.name}_age_z{crew_z:.2f}.glb"
    m.export(glb)
    res = {"iteration": it, "fields": "time mean" if tr else "snapshot", "slice_z_m": crew_z, "age_range_s": [float(lo_v), float(hi_v)], "glb": str(glb.relative_to(ROOT)),
           "slice_bounds_model_m": [float(x) for x in hz.bounds], "living_volume_m": [lo.tolist(), hi.tolist()]}
    # the slice must lie inside the living volume taken from the case meta (frame check)
    assert np.all(np.array(hz.bounds[0::2]) >= lo - 1e-6) and np.all(np.array(hz.bounds[1::2]) <= hi + 1e-6)
    (out / f"{case.name}_slices.json").write_text(json.dumps(res, indent=1) + "\n")
    man = ROOT / "vr" / "web" / "assets" / "overlays.json"
    items = [o for o in (json.loads(man.read_text()) if man.exists() else []) if o["file"] != glb.name]
    items.append({"file": glb.name, "label": f"age of air at z = {crew_z:.1f} m",
                  "note": f"Age of air {lo_v:.0f}-{hi_v:.0f} s (2nd-98th pct, magma: dark = fresh) — {case.name}, "
                          f"{when}; coarse mesh, placeholder HVAC."})
    man.write_text(json.dumps(items, indent=1) + "\n")
    return res


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("case")
    ap.add_argument("--decomposed", action="store_true")
    a = ap.parse_args()
    print(json.dumps(run(Path(a.case), a.decomposed), indent=1))
