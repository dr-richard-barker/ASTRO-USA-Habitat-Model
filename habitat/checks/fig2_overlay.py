"""Gate: the built CAD's plan view must reproduce Figure 2.

Independent of the registry's own arithmetic: footprints are re-measured from the exported
STL files, converted back into Figure 2's printed frame (inches, y down from the top wall),
and compared with the zones extracted from the PDF (sources/fig2_geometry.json). A wrong
axis convention or a mirrored plan builds and stays watertight but fails here (L010).

    uv run python -m habitat.checks.fig2_overlay
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import matplotlib
import numpy as np
import trimesh

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from .. import OUT, ROOT  # noqa: E402
from ..units import IN_TO_MM  # noqa: E402

TOL_IN = 0.5
# registry part -> Figure 3 label (the parts whose plan footprint is a Figure 2 zone)
PAIRS = {"nft_canopy": ("Hydroponics", 0), "myco_enclosure": ("Mycoponics™", 0),
         "battery_cabinet": ("Battery Cabinet", 0), "kratky_tub": ("Kratcky-DWC", 0),
         "dutch_bucket_1": ("Dutch Buckets", 0), "dutch_bucket_2": ("Dutch Buckets", 1),
         "propagation_rack": ("Propagation Station", 0), "workbench_zone": ("Work Space", 0)}


def run(cad_dir: Path = OUT / "cad", fig2: Path = ROOT / "sources" / "fig2_geometry.json",
        out_dir: Path = OUT / "checks") -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    g = json.loads(fig2.read_text())
    W = g["footprint_in"][1]
    zones: dict[str, list] = {}
    for z in g["zones"]:
        zones.setdefault(z["label"], []).append(z["bbox_in"])
    rows, worst = [], 0.0
    fig, ax = plt.subplots(figsize=(14, 3.4))
    for lab, boxes in zones.items():
        for b in boxes:
            ax.add_patch(plt.Rectangle((b[0], b[1]), b[2] - b[0], b[3] - b[1], fill=False, lw=2.2,
                                       ec="#9aa5b1"))
    for pid, (lab, k) in PAIRS.items():
        m = trimesh.load(cad_dir / "stl" / f"{pid}.stl")
        (x0, y0, _), (x1, y1, _) = m.bounds / IN_TO_MM
        cad_fig = [x0, W - y1, x1, W - y0]                    # model frame -> printed frame
        ref = zones[lab][k]
        err = float(np.max(np.abs(np.array(cad_fig) - np.array(ref))))
        worst = max(worst, err)
        rows.append({"part": pid, "fig2_label": lab, "cad_bbox_in": np.round(cad_fig, 3).tolist(),
                     "fig2_bbox_in": ref, "max_dev_in": round(err, 4), "ok": err <= TOL_IN})
        ax.add_patch(plt.Rectangle((cad_fig[0], cad_fig[1]), cad_fig[2] - cad_fig[0], cad_fig[3] - cad_fig[1],
                                   fill=True, alpha=0.35, lw=0.8, ec="#0b5394", fc="#3d85c6"))
        ax.text((cad_fig[0] + cad_fig[2]) / 2, (cad_fig[1] + cad_fig[3]) / 2, pid, ha="center", va="center",
                fontsize=6)
    ax.add_patch(plt.Rectangle((0, 0), g["footprint_in"][0], W, fill=False, lw=1.2, ec="k"))
    ax.set_xlim(-5, g["footprint_in"][0] + 5)
    ax.set_ylim(W + 5, -5)                                      # printed orientation: y down
    ax.set_aspect("equal")
    ax.set_xlabel("in (Figure 2 frame)")
    ax.set_title(f"CAD plan (blue, re-measured from STL) over Figure 2 zones (grey) — max deviation {worst:.3f} in")
    fig.tight_layout()
    fig.savefig(out_dir / "fig2_overlay.png", dpi=150)
    plt.close(fig)
    res = {"tolerance_in": TOL_IN, "max_dev_in": round(worst, 4), "rows": rows, "pass": worst <= TOL_IN}
    (out_dir / "fig2_overlay.json").write_text(json.dumps(res, indent=1) + "\n")
    return res


if __name__ == "__main__":
    r = run()
    for row in r["rows"]:
        print(f"{row['part']:18s} {row['max_dev_in']:.4f} in  {'ok' if row['ok'] else 'FAIL'}")
    print("PASS" if r["pass"] else "FAIL", "max deviation", r["max_dev_in"], "in")
    sys.exit(0 if r["pass"] else 1)
