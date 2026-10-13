"""Primary-habitat CONCEPT generator: ledger/primary.yaml -> geometry, volume metrics and a VR scene spec.

    uv run python -m habitat.primary

A design-study tool, not the team's design: modules are the ledger's study variables. Reports internal pressurised
volume, an NHV estimate bracketed by the habitable-fraction sweep (airlock excluded, as in the guideline), deck area,
and the comparison with the NASA NHV guideline (25 m3/person for a crew of 6; Whitmire et al. 2014).
Geometry: spherical node at the origin (centre at cradle height); modules radial along +x, +y, -x, -y joined through
hatch tunnels; the airlock coaxial at the outer end of the 'eclss' module.
"""
from __future__ import annotations

import json
import math

import numpy as np

from . import OUT, ROOT
from .provenance import Ledger

DIRS = [(1, 0), (0, 1), (-1, 0), (0, -1)]


def build(L: Ledger | None = None) -> dict:
    L = L or Ledger()
    wall = L.num("primary.wall_thickness", "m")
    node_d = L.val("primary.node")["diameter"]
    mods = L.val("primary.modules")
    tun = L.val("primary.hatch_tunnel")
    al = L.val("primary.airlock")
    deck_dz = L.num("primary.deck_below_axis", "m")
    crew = int(L.num("primary.crew", "-"))
    if len(mods) > len(DIRS):
        raise ValueError("the concept places at most four radial modules")
    zc = max([node_d] + [m["diameter"] for m in mods]) / 2 + 0.3     # axis height: largest radius + cradle
    R = node_d / 2
    els, vols = [], {}
    els.append({"id": "node", "type": "sphere_shell", "layer": "primary", "center": [0, 0, zc], "r_out": R,
                "r_in": R - wall, "ports": [], "illustrative": True})
    vols["node"] = 4 / 3 * math.pi * (R - wall) ** 3
    for (dx, dy), m in zip(DIRS, mods):
        d = np.array([dx, dy, 0.0])
        t0 = np.array([0, 0, zc]) + d * (R - 0.05)
        t1 = t0 + d * (tun["length"] + 0.05)
        els[0]["ports"].append({"dir": d.tolist(), "radius": tun["diameter"] / 2})
        els.append({"id": f"tunnel_{m['name']}", "type": "tube", "layer": "primary", "p0": t0.tolist(),
                    "p1": t1.tolist(), "r_out": tun["diameter"] / 2, "r_in": tun["diameter"] / 2 - wall / 2,
                    "cap_end": False, "illustrative": True})
        vols[f"tunnel_{m['name']}"] = math.pi * (tun["diameter"] / 2 - wall / 2) ** 2 * tun["length"]
        p0, p1 = t1, t1 + d * m["length"]
        ro = m["diameter"] / 2
        els.append({"id": f"module_{m['name']}", "type": "tube", "layer": "primary", "p0": p0.tolist(), "p1": p1.tolist(),
                    "r_out": ro, "r_in": ro - wall, "cap_start": True, "cap_end": True, "hatch_r": tun["diameter"] / 2,
                    "illustrative": True, "label": f"{m['name']} module"})
        ri = ro - wall
        vols[f"module_{m['name']}"] = math.pi * ri ** 2 * m["length"]
        half_w = math.sqrt(ri ** 2 - deck_dz ** 2)
        # deck plate and function zones (alternating sides, evenly along the module)
        perp = np.array([-dy, dx, 0.0])
        a = p0 + perp * (-half_w); b = p1 + perp * half_w
        lo = np.minimum(a, b); hi = np.maximum(a, b)
        lo[2] = zc - deck_dz - 0.05; hi[2] = zc - deck_dz
        els.append({"id": f"deck_{m['name']}", "type": "box", "layer": "primary", "lo": lo.tolist(), "hi": hi.tolist(),
                    "mat": "deck", "illustrative": True, "deck_area_m2": 2 * half_w * m["length"]})
        n = len(m["functions"])
        seg = m["length"] / n
        for k, fn in enumerate(m["functions"]):
            side = 1 if k % 2 == 0 else -1
            c0 = p0 + d * (k * seg + 0.3) + perp * side * (half_w - 0.75)
            c1 = p0 + d * ((k + 1) * seg - 0.3) + perp * side * (half_w - 0.15)
            zlo, zhi = zc - deck_dz, zc - deck_dz + 1.9
            lo = np.minimum(c0, c1); hi = np.maximum(c0, c1)
            els.append({"id": f"{m['name']}_{k}_{''.join(ch if ch.isalnum() else '_' for ch in fn.lower())[:30]}",
                        "type": "concept_box", "layer": "primary", "lo": [lo[0], lo[1], zlo], "hi": [hi[0], hi[1], zhi],
                        "illustrative": True, "label": fn, "mat": "white"})
        if m["name"] == "eclss":
            a0, a1 = p1, p1 + d * al["length"]
            els.append({"id": "airlock", "type": "tube", "layer": "primary", "p0": a0.tolist(), "p1": a1.tolist(),
                        "r_out": al["diameter"] / 2, "r_in": al["diameter"] / 2 - wall, "cap_start": True,
                        "cap_end": True, "illustrative": True, "label": "airlock (concept)"})
            airlock_vol = math.pi * (al["diameter"] / 2 - wall) ** 2 * al["length"]
    # ---- normalise to the scene-spec form (lo/hi, params, refs) and check for clashes between modules
    std = []
    for e in els:
        if e["type"] == "sphere_shell":
            c = np.array(e["center"]); lo, hi = c - e["r_out"], c + e["r_out"]
        elif e["type"] == "tube":
            a, b = np.array(e["p0"]), np.array(e["p1"])
            ax = (b - a) / np.linalg.norm(b - a)
            ext = e["r_out"] * np.sqrt(np.clip(1 - ax ** 2, 0, 1))      # AABB of a cylinder
            lo, hi = np.minimum(a, b) - ext, np.maximum(a, b) + ext
            if e["id"].startswith("module_"):
                lo[2] = 0.0                                 # cradles under each module reach the ground
        else:
            lo, hi = np.array(e["lo"]), np.array(e["hi"])
        params = {k: v for k, v in e.items() if k not in ("id", "type", "layer", "lo", "hi", "illustrative")}
        std.append({"id": e["id"], "type": e["type"], "layer": e["layer"], "parent": e["id"].split("_")[0],
                    "lo": lo.tolist(), "hi": hi.tolist(), "illustrative": True,
                    "refs": ["primary.modules", "primary.node", "primary.wall_thickness"], "params": params})
    tubes = [e for e in std if e["id"].startswith(("module_", "airlock"))]
    for i, a in enumerate(tubes):
        for b in tubes[i + 1:]:
            if {a["id"], b["id"]} == {"module_eclss", "airlock"}:
                continue                                    # joined end-to-end by design
            ov = [min(a["hi"][k], b["hi"][k]) - max(a["lo"][k], b["lo"][k]) for k in range(3)]
            if all(o > 1e-6 for o in ov):
                raise ValueError(f"concept modules clash: {a['id']} and {b['id']}")
    els = std
    pressurised = sum(vols.values())                       # excludes the airlock
    fr = L.val("primary.habitable_fraction")
    g = L.num("primary.nhv_guideline", "m3/person")
    nhv = {f"{f:.2f}": {"nhv_m3": f * pressurised, "per_crew_m3": f * pressurised / crew,
                        "meets_guideline": f * pressurised / crew >= g} for f in fr}
    deck = sum(e["params"]["deck_area_m2"] for e in els if "deck_area_m2" in e["params"])
    metrics = {"crew": crew, "internal_pressurised_m3_excl_airlock": pressurised, "airlock_m3": airlock_vol,
               "by_element_m3": vols, "deck_area_m2": deck, "deck_per_crew_m2": deck / crew,
               "nhv_guideline_m3_per_person": g, "nhv_by_habitable_fraction": nhv,
               "min_habitable_fraction_for_guideline": g * crew / pressurised}
    return {"name": "primary_concept", "ledger_digest": L.digest(), "frame": "metres, z up, node at origin",
            "elements": els, "metrics": metrics, "ledger_used": L.usage_report()}


def main():
    s = build()
    out = OUT / "vr"
    out.mkdir(parents=True, exist_ok=True)
    (out / "primary_spec.json").write_text(json.dumps(s, indent=1, default=float))
    m = s["metrics"]
    lines = ["# Primary habitat — concept design-study metrics (NOT the team's design)\n\n",
             f"Generated from `ledger/primary.yaml` (ledger {s['ledger_digest']}). Crew {m['crew']}.\n\n",
             f"- Internal pressurised volume (airlock excluded): **{m['internal_pressurised_m3_excl_airlock']:.0f} m³**"
             f" (airlock {m['airlock_m3']:.1f} m³)\n",
             f"- Deck area: {m['deck_area_m2']:.0f} m² ({m['deck_per_crew_m2']:.1f} m² per crewmember)\n",
             f"- NASA NHV guideline: {m['nhv_guideline_m3_per_person']:.0f} m³ per person (crew of 6; Whitmire et al. 2014)\n",
             f"- Habitable fraction needed to meet it: **{m['min_habitable_fraction_for_guideline']:.2f}**\n\n",
             "| habitable fraction (assumed) | NHV (m³) | per crewmember (m³) | meets 25 m³ |\n|---|---|---|---|\n"] + \
            [f"| {k} | {v['nhv_m3']:.0f} | {v['per_crew_m3']:.1f} | {'yes' if v['meets_guideline'] else 'no'} |\n"
             for k, v in m["nhv_by_habitable_fraction"].items()] + \
            ["\n| element | internal volume (m³) |\n|---|---|\n"] + \
            [f"| {k} | {v:.1f} |\n" for k, v in m["by_element_m3"].items()]
    (ROOT / "results" / "primary_concept.md").write_text("".join(lines))
    print("".join(lines))


if __name__ == "__main__":
    main()
