"""T1 engineering CAD (M0: block level) from the parts registry -> STEP, STL, GLB + QA.

    uv run python -m habitat.cad.build

Every export is checked after writing (L009: silent no-ops are the house failure mode):
  * export_step / export_gltf return status is asserted (build123d's export_gltf does NOT raise);
  * the GLB is reloaded and its node names must equal the registry ids exported;
  * every part's reloaded bounding box must match the registry box within 0.5 mm (L010:
    valid is not correct — measure against the independently known value);
  * the shell's measured external envelope must equal the container spec.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import trimesh
from build123d import Box, Compound, Location, Unit, export_gltf, export_step, export_stl

from .. import OUT
from ..provenance import Ledger
from ..registry import Part, build as build_registry

CAD_ROLES = {"blockage", "source_zone", "opening"}     # parts with a physical/visual body in M0
GRILLE_PLATE_MM = 1.0   # visual-only plate for a grille (the CFD uses the face patch itself); not a design value


def _box(lo, hi, label: str):
    lo, hi = np.asarray(lo, float), np.asarray(hi, float)
    size = hi - lo
    b = Box(*size)
    b = b.moved(Location(tuple((lo + hi) / 2)))
    b.label = label
    return b


def shell(L: Ledger, parts: dict[str, Part]):
    """Hollow steel shell: external envelope minus internal cavity, placed around the FPM footprint."""
    ex, ey, ez = L.val("container.external")
    ix, iy, iz = L.val("container.internal")
    interior = parts["interior"]
    gap_x = ix - interior.size[0]             # unexplained length difference, placed at the door end
    gap_y = (iy - interior.size[1]) / 2       # lining, split evenly
    roof = L.num("container.roof_thickness", "mm")
    cav_lo = np.array([-gap_x, -gap_y, -L.num("container.lining.floor", "mm")])
    cav_hi = cav_lo + [ix, iy, iz]
    ext_lo = cav_lo - [(ex - ix) / 2, (ey - iy) / 2, ez - iz - roof]
    ext_hi = ext_lo + [ex, ey, ez]
    outer = _box(ext_lo, ext_hi, "shell")
    cavity = _box(cav_lo, cav_hi, "cavity")
    s = outer - cavity
    if abs(s.volume - (outer.volume - cavity.volume)) > 1e-6 * outer.volume:   # BooleanNoOp guard (L009)
        raise RuntimeError("shell boolean did not remove the cavity")
    s.label = "container_shell"
    L.rec("container.external"), L.rec("container.internal")
    return s, ext_lo, ext_hi


def build(out: Path = OUT / "cad") -> dict:
    out.mkdir(parents=True, exist_ok=True)
    (out / "stl").mkdir(exist_ok=True)
    L, plist = build_registry()
    parts = {p.id: p for p in plist}
    solids = []
    sh, ext_lo, ext_hi = shell(L, parts)
    solids.append(sh)
    for p in plist:
        if p.cfd_role not in CAD_ROLES:
            continue
        lo, hi = list(p.lo), list(p.hi)
        if p.cfd_role == "opening":            # grille drawn as a thin plate on the attic side of the partition
            hi[0] = lo[0] + GRILLE_PLATE_MM
        solids.append(_box(lo, hi, p.id))
    asm = Compound(children=solids, label="astro_usa_fpm_m0")

    step_ok = export_step(asm, out / "fpm_m0.step", unit=Unit.MM)
    assert step_ok, "export_step reported failure"
    glb = out / "fpm_m0.glb"
    glb_ok = export_gltf(asm, glb, unit=Unit.MM, binary=True)
    assert glb_ok, "export_gltf reported failure (build123d does not raise)"
    for s in solids:
        export_stl(s, out / "stl" / f"{s.label}.stl")

    # ---- QA: reload and measure
    scene = trimesh.load(glb)
    names = set(scene.graph.nodes)
    labels = {s.label for s in solids}
    missing = sorted(labels - names)           # build123d writes each solid's label as its node name
    qa = {"ledger_digest": L.digest(), "n_solids": len(solids), "glb_nodes": len(names), "missing_in_glb": missing,
          "parts": []}
    assert not missing, f"labels missing from GLB nodes: {missing}"
    for s in solids:
        m = trimesh.load(out / "stl" / f"{s.label}.stl")
        bb = m.bounds
        if s.label == "container_shell":
            want = np.array([ext_lo, ext_hi])
        else:
            p = parts[s.label]
            want = np.array([p.lo, p.hi])
            if p.cfd_role == "opening":
                want[1][0] = want[0][0] + GRILLE_PLATE_MM
        err = float(np.abs(bb - want).max())
        qa["parts"].append({"id": s.label, "bbox_mm": bb.round(2).tolist(), "max_err_mm": round(err, 4),
                            "watertight": bool(m.is_watertight), "volume_mm3": round(float(m.volume), 1),
                            "digest": parts[s.label].digest() if s.label in parts else None})
        assert err < 0.5, f"{s.label}: STL bbox {bb.tolist()} differs from registry {want.tolist()} by {err} mm"
        assert m.is_watertight, f"{s.label}: STL not watertight"
    # GLB is in metres with Y up (glTF convention): its extent must equal the shell envelope / 1000
    ext = scene.bounds[1] - scene.bounds[0]
    want_ext = np.array(L.val("container.external"), float) / 1000.0
    gl = np.sort(ext)
    assert np.allclose(np.sort(want_ext), gl, rtol=1e-3), f"GLB extent {ext} m != container external {want_ext} m"
    qa["glb_extent_m"] = ext.round(4).tolist()
    qa["ledger_used"] = L.usage_report()
    (out / "CAD_QA.json").write_text(json.dumps(qa, indent=1) + "\n")
    return qa


if __name__ == "__main__":
    q = build()
    print(f"{q['n_solids']} solids, GLB nodes {q['glb_nodes']}, extent {q['glb_extent_m']} m, ledger {q['ledger_digest']}")
    for p in q["parts"]:
        print(f"  {p['id']:18s} err={p['max_err_mm']:.4f} mm watertight={p['watertight']}")
