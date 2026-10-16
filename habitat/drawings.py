"""Dimensioned drawings of the FPM from the parts registry: plan + both long-wall elevations (SVG and PDF).

    uv run python -m habitat.drawings

Every dimension printed is measured from the registry boxes (which come from the ledger), in inches to match
ICES-2026-251 Fig 2, with millimetres in brackets. Third-angle-style layout: plan on top, elevations below.
Illustrative / assumed parts are drawn dashed and listed in the title block's notes.
"""
from __future__ import annotations

import matplotlib
import numpy as np

matplotlib.use("Agg")
matplotlib.rcParams["svg.hashsalt"] = "astro-usa-fpm"     # stable SVG ids: rebuilds give identical files
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.backends.backend_pdf import PdfPages  # noqa: E402

from . import ROOT  # noqa: E402
from .registry import build  # noqa: E402
from .units import IN_TO_MM  # noqa: E402

OUT = ROOT / "results" / "drawings"
STYLE = {"blockage": dict(fc="#c9d6e3", ec="#2f5985", lw=1.0), "source_zone": dict(fc="#e2f0d9", ec="#4c8c2b", lw=0.8, ls="--"),
         "payload": dict(fc="#fde9c9", ec="#b26b00", lw=0.9, ls="-."), "opening": dict(fc="#3fb6a8", ec="#1d6e65", lw=1.0)}


SHORT = {"myco_enclosure": "bioreactor bay", "payload_photobioreactor": "PBR", "payload_sensor_module": "S",
         "payload_bioreactor_rack": "bioreactor rack", "payload_incubator": "incubator"}


def _name(pid: str) -> str:
    """Drawing label: short names in the crowded bay (PBR = photobioreactor, S = sensor module; see the sheet note)."""
    return SHORT.get(pid, pid.replace("_", " "))


def _dim(ax, x0, x1, y, text, above=True):
    ax.annotate("", xy=(x0, y), xytext=(x1, y), arrowprops=dict(arrowstyle="<->", lw=0.6))
    ax.text((x0 + x1) / 2, y + (1.2 if above else -3.2), text, ha="center", va="bottom", fontsize=5.5)


def _in(mm):
    return mm / IN_TO_MM


def plan(ax, parts):
    P = {p.id: p for p in parts}
    W, D = _in(P["interior"].hi[0]), _in(P["interior"].hi[1])
    ax.add_patch(plt.Rectangle((0, 0), W, D, fill=False, lw=1.6))
    a = P["attic"]
    ax.add_patch(plt.Rectangle((_in(a.lo[0]), 0), _in(a.hi[0] - a.lo[0]), D, fc="#eeeeee", ec="k", hatch="///", lw=0.8))
    ax.text(_in((a.lo[0] + a.hi[0]) / 2), D / 2, "ATTIC\n(HVAC)", ha="center", va="center", fontsize=6)
    for p in parts:
        if p.cfd_role not in STYLE or p.id.startswith("crew"):
            continue
        x0, y0, x1, y1 = _in(p.lo[0]), _in(p.lo[1]), _in(p.hi[0]), _in(p.hi[1])
        if p.cfd_role == "opening":
            ax.plot([x0, x0], [y0, y1], lw=3, color=STYLE["opening"]["fc"])
            continue
        ax.add_patch(plt.Rectangle((x0, y0), x1 - x0, y1 - y0, **STYLE[p.cfd_role]))
        if p.id == "myco_enclosure":         # label the bay along its aisle-side edge so the payload labels stay clear
            ax.text((x0 + x1) / 2, y0 + 0.8, _name(p.id), ha="center", va="bottom", fontsize=4.8)
        else:
            ax.text((x0 + x1) / 2, (y0 + y1) / 2, _name(p.id), ha="center",
                    va="center", fontsize=4.8, rotation=0 if x1 - x0 > 30 else 90)
    # overall + key chains (measured from the boxes)
    _dim(ax, 0, W, D + 6, f'{W:.2f}" [{W * IN_TO_MM:.0f} mm] interior (ICES Fig 2: 464.00")')
    ax.annotate("", xy=(W + 6, 0), xytext=(W + 6, D), arrowprops=dict(arrowstyle="<->", lw=0.6))
    ax.text(W + 8, D / 2, f'{D:.2f}"\n[{D * IN_TO_MM:.0f}]', fontsize=5.5, va="center")
    row = sorted([p for p in parts if p.id in ("battery_cabinet", "kratky_tub", "propagation_rack", "workbench_zone")],
                 key=lambda p: p.lo[0])
    for p in row:
        _dim(ax, _in(p.lo[0]), _in(p.hi[0]), -6, f'{_in(p.hi[0] - p.lo[0]):.1f}"', above=False)
    for pid in ("nft_canopy", "myco_enclosure"):
        p = P[pid]
        _dim(ax, _in(p.lo[0]), _in(p.hi[0]), D + 1.5, f'{_in(p.hi[0] - p.lo[0]):.1f}"')
    ax.text(1, -16, "DOOR END (disconnect)  ◀", fontsize=6)
    ax.set_xlim(-8, W + 22); ax.set_ylim(-20, D + 16); ax.set_aspect("equal"); ax.axis("off")
    ax.set_title("PLAN (y up = hydroponic wall, as printed top of ICES Fig 2)", fontsize=8, loc="left")


def elevation(ax, parts, wall: str):
    """Long-wall elevation: wall 'ymax' (hydroponic / bioreactor-bay side) or 'ymin' (battery / work side), seen from the aisle."""
    P = {p.id: p for p in parts}
    W, H = _in(P["interior"].hi[0]), _in(P["interior"].hi[2])
    Dm = P["interior"].hi[1]
    ax.add_patch(plt.Rectangle((0, 0), W, H, fill=False, lw=1.4))
    for p in parts:
        if p.cfd_role not in STYLE or p.cfd_role == "opening":
            continue
        near = p.hi[1] > Dm * 0.6 if wall == "ymax" else p.lo[1] < Dm * 0.4
        if not near or p.id.startswith("crew"):
            continue
        x0, x1, z0, z1 = _in(p.lo[0]), _in(p.hi[0]), _in(p.lo[2]), _in(p.hi[2])
        ax.add_patch(plt.Rectangle((x0, z0), x1 - x0, z1 - z0, **STYLE[p.cfd_role]))
        lab = _name(p.id) if x1 - x0 < 6 else f"{_name(p.id)}\nh {z1 - z0:.0f}\""   # tiny parts: name only
        if p.id == "myco_enclosure":         # label the bay at its top so the payload labels inside stay clear
            ax.text((x0 + x1) / 2, z1 - 1.0, lab, ha="center", va="top", fontsize=4.8)
        else:
            ax.text((x0 + x1) / 2, (z0 + z1) / 2, lab, ha="center",
                    va="center", fontsize=4.8, rotation=0 if x1 - x0 > 14 else 90)
    for p in parts:
        if p.cfd_role == "opening":
            ax.add_patch(plt.Rectangle((_in(p.lo[0]) - 1.5, _in(p.lo[2])), 1.5, _in(p.hi[2] - p.lo[2]), **STYLE["opening"]))
    ax.annotate("", xy=(W + 5, 0), xytext=(W + 5, H), arrowprops=dict(arrowstyle="<->", lw=0.6))
    ax.text(W + 7, H / 2, f'{H:.1f}"\n[{H * IN_TO_MM:.0f}]', fontsize=5.5, va="center")
    ax.set_xlim(-8, W + 22); ax.set_ylim(-6, H + 8); ax.set_aspect("equal"); ax.axis("off")
    title = ("ELEVATION A — hydroponic / bioreactor-bay wall" if wall == "ymax" else "ELEVATION B — battery / work-space wall")
    ax.set_title(title + " (door end left)", fontsize=8, loc="left")


def main():
    L, parts = build()
    OUT.mkdir(parents=True, exist_ok=True)
    fig = plt.figure(figsize=(16.5, 11.7))                    # A3 landscape
    P = {p.id: p for p in parts}
    D, H = _in(P["interior"].hi[1]), _in(P["interior"].hi[2])
    # panel heights proportional to each view's drawn y-range, so all three views share one scale
    gs = fig.add_gridspec(3, 1, height_ratios=[D + 36, H + 14, H + 14], hspace=0.25)
    plan(fig.add_subplot(gs[0]), parts)
    elevation(fig.add_subplot(gs[1]), parts, "ymax")
    elevation(fig.add_subplot(gs[2]), parts, "ymin")
    fig.text(0.01, 0.01, "\n".join(__import__("textwrap").wrap("ASTRO-USA Mini-Hab Food Production Module — block-level drawings generated from the sourced ledger "
             f"(digest {L.digest()}). Solid blue: equipment (CFD blockages); dashed green: source zones (canopy, work space); "
             "dash-dot orange: payload envelopes; teal: HVAC grilles. Heights of most equipment are ASSUMED (see "
             "ASSUMPTIONS.md); plan dimensions are from ICES-2026-251 Fig 2. In the bioreactor bay, PBR = photobioreactor and S = sensor module (generic placeholder envelopes). Not for construction.", 230)), fontsize=6.5)
    fig.savefig(OUT / "FPM_GA.svg", metadata={"Date": None})
    fig.savefig(OUT / "FPM_GA.pdf", metadata={"CreationDate": None})
    fig.savefig(OUT / "FPM_GA.png", dpi=110)
    plt.close(fig)
    print(f"wrote {OUT}/FPM_GA.(svg|pdf|png)")


if __name__ == "__main__":
    main()
