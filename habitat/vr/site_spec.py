"""Mini-Hab site (Fig 10, concept level) -> out/vr/site_spec.json, in the FPM model frame (metres, z up).

    uv run python -m habitat.vr.site_spec

Separate from the FPM scene so the FPM gates stay exact; the viewer loads it as an overlay. Every interior item is
illustrative. Assumed orientation: Fig 10 is drawn like Fig 2 (FPM door end on the left), so the second row of
modules sits beside the FPM's printed bottom wall (-y in the model frame).
"""
from __future__ import annotations

import json

from .. import OUT
from ..provenance import Ledger
from .spec import build_spec


def _container(L, name, x0, y0, z0, layer="site"):
    ex, ey, ez = (v / 1000 for v in L.val("site.container_20ft.external"))
    ix, iy, iz = (v / 1000 for v in L.val("site.container_20ft.internal"))
    roof = L.num("container.roof_thickness", "mm") / 1000
    lo, hi = [x0, y0, z0], [x0 + ex, y0 + ey, z0 + ez]
    cav_lo = [x0 + (ex - ix) / 2, y0 + (ey - iy) / 2, z0 + (ez - iz - roof)]
    cav_hi = [cav_lo[0] + ix, cav_lo[1] + iy, cav_lo[2] + iz]
    el = {"id": f"{name}_shell", "type": "shell", "layer": layer, "parent": name, "lo": lo, "hi": hi,
          "illustrative": False, "refs": ["site.container_20ft.external", "site.container_20ft.internal",
                                           "site.module_container"],
          "params": {"cavity_lo": cav_lo, "cavity_hi": cav_hi, "corrugation": L.val("vr.side_corrugation"),
                     "door_opening": None}}
    floor = {"id": f"{name}_floor", "type": "floor", "layer": layer, "parent": name,
             "lo": [cav_lo[0], cav_lo[1], cav_lo[2] - 0.028], "hi": [cav_hi[0], cav_hi[1], cav_lo[2]],
             "illustrative": True, "refs": ["site.container_20ft.internal"], "params": {}}
    return [el, floor], cav_lo, cav_hi


def _interior(layout, name, cav_lo, cav_hi, ref):
    out = []
    for k, it in enumerate(layout):
        x0 = cav_lo[0] + it["x0"]
        if it["wall"] == "north":
            y1 = cav_hi[1] - 0.02; y0 = y1 - it["d"]
        else:
            y0 = cav_lo[1] + 0.02; y1 = y0 + it["d"]
        slug = "".join(ch if ch.isalnum() else "_" for ch in it["item"].lower()).strip("_")
        out.append({"id": f"{name}_{k:02d}_{slug}"[:60], "type": "concept_box", "layer": "site", "parent": name,
                    "lo": [x0, y0, cav_lo[2]], "hi": [x0 + it["w"], y1, cav_lo[2] + it["h"]],
                    "illustrative": True, "refs": [ref], "params": {"label": it["item"], "mat": it["mat"]}})
        if x0 + it["w"] > cav_hi[0] + 1e-9:
            raise ValueError(f"{name}: {it['item']} runs past the module end")
    return out


def build_site_spec() -> dict:
    L = Ledger()
    fpm = next(e for e in build_spec()["elements"] if e["id"] == "container_shell")
    flo, fhi = fpm["lo"], fpm["hi"]
    gap = L.num("site.row_gap", "m")
    ey = L.val("site.container_20ft.external")[1] / 1000
    ex = L.val("site.container_20ft.external")[0] / 1000
    y0 = flo[1] - gap - ey
    x_crew = flo[0] + L.num("site.crew_offset_x", "m")
    els = []
    crew, c_lo, c_hi = _container(L, "crew_quarters", x_crew, y0, flo[2])
    lab, l_lo, l_hi = _container(L, "laboratory_module", x_crew + ex, y0, flo[2])
    els += crew + lab
    els += _interior(L.val("site.crew_layout"), "crew_quarters", c_lo, c_hi, "site.crew_layout")
    els += _interior(L.val("site.lab_layout"), "laboratory_module", l_lo, l_hi, "site.lab_layout")
    tl, tw, th = L.num("site.trailer.length", "m"), L.num("site.trailer.width", "m"), L.num("site.trailer.height", "m")
    yc = (flo[1] + fhi[1]) / 2
    els.append({"id": "biowaterr_trailer", "type": "trailer", "layer": "site", "parent": "biowaterr_trailer",
                "lo": [fhi[0], yc - tw / 2, flo[2]], "hi": [fhi[0] + tl, yc + tw / 2, flo[2] + th],
                "illustrative": True, "refs": ["site.trailer.length", "site.trailer.width", "site.trailer.height",
                                                "site.fig10_topology"],
                "params": {"label": "BioWaTERR trailer (NASA KSC; envelope placeholder)"}})
    # footprints must not overlap each other or the FPM
    boxes = [("fpm", flo, fhi)] + [(e["id"], e["lo"], e["hi"]) for e in els if e["type"] in ("shell", "trailer")]
    for i, (a, alo, ahi) in enumerate(boxes):
        for b, blo, bhi in boxes[i + 1:]:
            ov = [min(ahi[k], bhi[k]) - max(alo[k], blo[k]) for k in (0, 1)]
            if ov[0] > 1e-6 and ov[1] > 1e-6:
                raise ValueError(f"site footprints overlap: {a} and {b}")
    return {"name": "fpm_site", "ledger_digest": L.digest(), "frame": "FPM model frame, metres, z up",
            "elements": els, "ledger_used": L.usage_report()}


def main():
    out = OUT / "vr"
    out.mkdir(parents=True, exist_ok=True)
    s = build_site_spec()
    (out / "site_spec.json").write_text(json.dumps(s, indent=1))
    print(f"{len(s['elements'])} site elements ({sum(e['illustrative'] for e in s['elements'])} illustrative)")


if __name__ == "__main__":
    main()
