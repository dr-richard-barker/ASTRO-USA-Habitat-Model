"""CAD-exchange drawings: DXF plan, long-wall elevations and cross-sections, plus a sections sheet (SVG/PDF/PNG).

    uv run python -m habitat.drawings_cad

Same source as habitat/drawings.py: the registry boxes (from the ledger), in millimetres, model frame (x from the door
end, y from the printed bottom wall of ICES-2026-251 Fig 2, z up). DXF layers separate equipment (CFD blockages),
source zones, payload envelopes, openings, the room outline and dimensions, so a Fusion 360 / AutoCAD user can
switch them independently. Cross-sections cut the room across its width at the x positions listed in SECTIONS.
"""
from __future__ import annotations

import ezdxf
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from . import ROOT  # noqa: E402
from .registry import build  # noqa: E402

OUT = ROOT / "results" / "drawings"
ROLE_LAYER = {"blockage": ("EQUIPMENT", 5), "source_zone": ("SOURCE_ZONE", 3), "payload": ("PAYLOAD", 30),
              "opening": ("OPENING", 4)}
# cross-section cuts (element whose centre the cut passes through): chosen to show both long walls at once
SECTIONS = {"A-A (battery cabinet / NFT wall)": "battery_cabinet", "B-B (workbench / bioreactor bay)": "payload_bioreactor_rack"}


def _rect(msp, x0, y0, x1, y1, layer):
    msp.add_lwpolyline([(x0, y0), (x1, y0), (x1, y1), (x0, y1)], close=True, dxfattribs={"layer": layer})


def _label(msp, text, x, y, layer="TEXT", h=40):
    msp.add_text(text, height=h, dxfattribs={"layer": layer}).set_placement((x, y), align=ezdxf.enums.TextEntityAlignment.MIDDLE_CENTER)


def views(parts) -> dict:
    """2-D rectangles per view: plan (x, y), elevation A (x, z; y-max wall side), B (x, z; y-0 side), sections (y, z)."""
    P = {p.id: p for p in parts}
    room = P["interior"]
    Dm = room.hi[1]
    keep = [p for p in parts if p.cfd_role in ROLE_LAYER and not p.id.startswith("crew")]
    v = {"plan": {"outline": (0, 0, room.hi[0], room.hi[1]),
                  "rects": [(p, p.lo[0], p.lo[1], p.hi[0], p.hi[1]) for p in keep]}}
    v["elevation_A"] = {"outline": (0, 0, room.hi[0], room.hi[2]),
                        "rects": [(p, p.lo[0], p.lo[2], p.hi[0], p.hi[2]) for p in keep if p.hi[1] > Dm * 0.6]}
    v["elevation_B"] = {"outline": (0, 0, room.hi[0], room.hi[2]),
                        "rects": [(p, p.lo[0], p.lo[2], p.hi[0], p.hi[2]) for p in keep if p.lo[1] < Dm * 0.4]}
    for name, pid in SECTIONS.items():
        x = (P[pid].lo[0] + P[pid].hi[0]) / 2
        v[f"section {name}"] = {"outline": (0, 0, room.hi[1], room.hi[2]), "cut_x": x,
                                "rects": [(p, p.lo[1], p.lo[2], p.hi[1], p.hi[2]) for p in keep if p.lo[0] <= x <= p.hi[0]]}
    return v


def write_dxf(L, parts, V) -> list:
    out = []
    for name, view in V.items():
        doc = ezdxf.new("R2010", setup=True)
        doc.header["$INSUNITS"] = 4                                   # millimetres
        for lay, col in list(ROLE_LAYER.values()) + [("OUTLINE", 7), ("DIMS", 1), ("TEXT", 7)]:
            if lay not in doc.layers:
                doc.layers.add(lay, color=col)
        msp = doc.modelspace()
        x0, y0, x1, y1 = view["outline"]
        _rect(msp, x0, y0, x1, y1, "OUTLINE")
        for p, a, b, c, d in view["rects"]:
            _rect(msp, a, b, c, d, ROLE_LAYER[p.cfd_role][0])
            _label(msp, p.id, (a + c) / 2, (b + d) / 2, h=30 if (c - a) > 300 else 18)
        dim = msp.add_linear_dim(base=(0, y1 + 250), p1=(x0, y1), p2=(x1, y1), dxfattribs={"layer": "DIMS"})
        dim.render()
        dim = msp.add_linear_dim(base=(x1 + 250, 0), p1=(x1, y0), p2=(x1, y1), angle=90, dxfattribs={"layer": "DIMS"})
        dim.render()
        title = f"ASTRO-USA FPM - {name}" + (f" at x = {view['cut_x']:.0f} mm" if "cut_x" in view else "")
        _label(msp, title, (x0 + x1) / 2, y0 - 250, h=60)
        _label(msp, f"generated from ledger {L.digest()}; mm; not for construction", (x0 + x1) / 2, y0 - 380, h=35)
        fn = OUT / f"FPM_{name.split(' (')[0].replace(' ', '_').replace('-', '')}.dxf"
        doc.saveas(fn)
        out.append(fn)
    return out


def sections_sheet(L, V) -> None:
    secs = [(n, v) for n, v in V.items() if n.startswith("section")]
    fig, axs = plt.subplots(1, len(secs), figsize=(11.7, 5.2), layout="constrained")
    for ax, (name, v) in zip(axs, secs):
        x0, y0, x1, y1 = v["outline"]
        ax.add_patch(plt.Rectangle((x0, y0), x1 - x0, y1 - y0, fill=False, lw=1.4))
        style = {"blockage": dict(fc="#c9d6e3", ec="#2f5985"), "source_zone": dict(fc="#e2f0d9", ec="#4c8c2b", ls="--"),
                 "payload": dict(fc="#fde9c9", ec="#b26b00", ls="-."), "opening": dict(fc="#3fb6a8", ec="#1d6e65")}
        for p, a, b, c, d in v["rects"]:
            ax.add_patch(plt.Rectangle((a, b), c - a, d - b, lw=0.8, **style[p.cfd_role]))
            holds = any(q is not p and a <= qa and qc <= c and b <= qb and qd <= d for q, qa, qb, qc, qd in v["rects"])
            ax.text((a + c) / 2, d - 60 if holds else (b + d) / 2, p.id.replace("_", " "), ha="center",
                    va="top" if holds else "center", fontsize=6, rotation=0 if c - a > 400 else 90)
        ax.set_xlim(-100, x1 + 100); ax.set_ylim(-100, y1 + 100); ax.set_aspect("equal")
        ax.set_xlabel("y across the container (mm; 0 = battery / work-side wall)", fontsize=8)
        ax.set_ylabel("z (mm)", fontsize=8); ax.tick_params(labelsize=7)
        ax.set_title(f"{name}, cut at x = {v['cut_x']:.0f} mm from the door end", fontsize=9)
    fig.suptitle(f"ASTRO-USA FPM cross-sections from the registry (ledger {L.digest()}); heights of most equipment are "
                 "assumptions (ASSUMPTIONS.md). Not for construction.", fontsize=8)
    for ext in ("svg", "pdf"):
        fig.savefig(OUT / f"FPM_sections.{ext}", metadata={"Date": None} if ext == "svg" else {"CreationDate": None})
    fig.savefig(OUT / "FPM_sections.png", dpi=110)
    plt.close(fig)


def main():
    matplotlib.rcParams["svg.hashsalt"] = "astro-usa-fpm"
    ezdxf.options.write_fixed_meta_data_for_testing = True   # no save timestamps / random GUIDs: rebuilds are identical
    L, parts = build()
    OUT.mkdir(parents=True, exist_ok=True)
    V = views(parts)
    files = write_dxf(L, parts, V)
    sections_sheet(L, V)
    for f in files:                                                   # every file must read back with its entities
        d = ezdxf.readfile(f)
        n = len(d.modelspace())
        assert n > 5, f"{f.name}: only {n} entities"
    print("wrote", ", ".join(f.name for f in files), "+ FPM_sections.(svg|pdf|png)")


if __name__ == "__main__":
    main()
