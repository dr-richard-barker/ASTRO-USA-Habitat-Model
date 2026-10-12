"""VR scene specification: registry parts + ledger detail -> out/vr/scene_spec.json for Blender.

    uv run python -m habitat.vr.spec

Every element carries the registry part it belongs to, its system layer, the ledger records it was
built from, and `illustrative: true` when the equipment is not described in ICES-2026-251 (generic
stand-ins so the scene reads correctly in VR; never presented as the team's design).
Units: metres, model frame (x along length from the door end, y from the printed bottom wall of
Fig 2 toward the hydroponics wall, z up) — the same frame as the CAD and CFD tiers.
"""
from __future__ import annotations

import json

from .. import OUT
from ..registry import build as build_registry
from ..units import to_m


def _m(v):
    return [x / 1000.0 for x in v]


def build_spec() -> dict:
    L, parts = build_registry()
    P = {p.id: p for p in parts}
    Lx, Ly, H = _m(P["interior"].hi)
    el = []

    def add(id_, type_, layer, lo, hi, parent, refs, illustrative=False, **params):
        el.append({"id": id_, "type": type_, "layer": layer, "parent": parent, "lo": lo, "hi": hi,
                   "illustrative": illustrative, "refs": refs, "params": params})

    # --- container shell (exterior from the spec sheet, cavity placed as in the CAD tier)
    ex, ey, ez = (v / 1000 for v in L.val("container.external"))
    ix, iy, iz = (v / 1000 for v in L.val("container.internal"))
    gap_x, gap_y = ix - Lx, (iy - Ly) / 2
    roof = L.num("container.roof_thickness", "mm") / 1000
    cav_lo = [-gap_x, -gap_y, -L.num("container.lining.floor", "mm") / 1000]
    ext_lo = [cav_lo[0] - (ex - ix) / 2, cav_lo[1] - (ey - iy) / 2, cav_lo[2] - (ez - iz - roof)]
    add("container_shell", "shell", "structure", ext_lo, [ext_lo[0] + ex, ext_lo[1] + ey, ext_lo[2] + ez], "interior",
        ["container.external", "container.internal", "container.roof_thickness", "vr.side_corrugation"],
        cavity_lo=cav_lo, cavity_hi=[cav_lo[0] + ix, cav_lo[1] + iy, cav_lo[2] + iz],
        corrugation=L.val("vr.side_corrugation"), door_opening=[v / 1000 for v in L.val("container.door_opening")])
    add("floor", "floor", "structure", [0, 0, -0.028], [Lx, Ly, 0], "interior", ["fpm.footprint.length"],
        illustrative=True)

    # --- attic partition with the two grilles
    ax = P["attic"].lo[0] / 1000
    grilles = [{"id": g, "lo": _m(P[g].lo), "hi": _m(P[g].hi)} for g in ("hvac_supply", "hvac_return")]
    add("attic_partition", "partition", "structure", [ax, 0, 0], [ax + 0.02, Ly, H], "attic",
        ["fpm.fig2_zones.attic"], openings=grilles)
    for g in grilles:
        add(g["id"], "grille", "air", g["lo"], [g["lo"][0] + 0.03, g["hi"][1], g["hi"][2]], g["id"],
            P[g["id"]].refs)
    sup = grilles[0]
    add("hvac_indoor_unit", "box_unit", "air", [ax + 0.03, sup["lo"][1] - 0.1, sup["lo"][2] - 0.15],
        [ax + 0.33, sup["hi"][1] + 0.1, H - 0.05], "attic", ["fpm.attic.purpose"], illustrative=True,
        label="HVAC (unit not specified)")

    # --- NFT wall
    can, tr = P["nft_canopy"], P["nft_trough"]
    ch = L.val("vr.nft_channel")
    add("nft_wall", "nft_wall", "plants", _m(can.lo), _m(can.hi), "nft_canopy", can.refs + ["vr.nft_channel", "vr.plant_radius"],
        towers=int(L.num("fpm.hydroponics.towers", "-")), sites=int(L.num("fpm.hydroponics.sites_per_tower", "-")),
        wall_y=Ly, channel_w=to_m(ch["width"], "in"), channel_d=to_m(ch["depth"], "in"),
        cup_d=to_m(ch["cup_diameter"], "in"), plant_r=L.val("vr.plant_radius")["nft"],
        trough_lo=_m(tr.lo), trough_hi=_m(tr.hi))

    # --- Mycoponics enclosure (payload bay)
    my = P["myco_enclosure"]
    pay = [p for p in parts if p.cfd_role == "payload"]
    top = max((p.hi[2] for p in pay), default=0.0) / 1000.0
    add("myco_enclosure", "glass_enclosure", "plants", _m(my.lo), _m(my.hi), "myco_enclosure", my.refs, shelves=3,
        shelves_above=top)
    for p in pay:     # PUBLIC envelopes only: outer box, label, ledger refs
        add(p.id, "payload_envelope", "payloads", _m(p.lo), _m(p.hi), p.id, p.refs, label=p.name,
            product=p.id.replace("payload_", ""), envelope_only=True)

    # --- bottom-wall row
    pr = P["propagation_rack"]
    add("propagation_rack", "shelf_rack", "plants", _m(pr.lo), _m(pr.hi), "propagation_rack", pr.refs + ["vr.plant_radius"],
        levels=int(L.num("fpm.propagation.levels", "-")), plant_r=L.val("vr.plant_radius")["seedling"])
    kt = P["kratky_tub"]
    kb = to_m(L.num("vr.kratky_small_bucket", "in"), "in")
    add("kratky", "kratky", "plants", _m(kt.lo), _m(kt.hi), "kratky_tub", kt.refs + ["vr.kratky_shelf_heights",
        "vr.kratky_small_bucket", "vr.plant_radius"], shelf_z=L.val("vr.kratky_shelf_heights"), bucket=kb,
        per_shelf=5, plant_r=L.val("vr.plant_radius")["kratky"])
    for k in (1, 2):
        d = P[f"dutch_bucket_{k}"]
        add(f"dutch_bucket_{k}", "dutch_bucket", "plants", _m(d.lo), _m(d.hi), d.id, d.refs + ["vr.plant_radius"],
            plant_r=L.val("vr.plant_radius")["dutch"], ceiling=H)
    bc = P["battery_cabinet"]
    add("battery_cabinet", "battery_cabinet", "power", _m(bc.lo), _m(bc.hi), bc.id, bc.refs + ["vr.battery_block"],
        n=int(L.num("fpm.electrical.batteries", "-")), block=[to_m(v, "in") for v in L.val("vr.battery_block")])
    wb = P["workbench_zone"]
    add("workbench", "workbench", "work", _m(wb.lo), _m(wb.hi), wb.id, wb.refs + ["vr.workbench_top_thickness"],
        top_t=to_m(L.num("vr.workbench_top_thickness", "in"), "in"))
    add("sensor_computer", "box_unit", "controls", [_m(wb.lo)[0] + 0.3, 0.15, _m(wb.hi)[2]],
        [_m(wb.lo)[0] + 0.65, 0.4, _m(wb.hi)[2] + 0.25], wb.id, ["fpm.electrical.feed_layout"], illustrative=True,
        label="sensor computer (RECP1, 5-12 VDC)")

    # --- electrical per Fig 7-9
    rx = [to_m(v, "in") for v in L.val("fig8.receptacle_x")]
    rz = to_m(L.num("vr.receptacle_height", "in"), "in")
    names_top, names_bot = ["RECP4", "RECP3", "RECP2", "RECP1"], ["RECP8", "RECP7", "RECP6", "RECP5"]
    for x, n_t, n_b in zip(rx, names_top, names_bot):
        add(n_t.lower(), "receptacle", "power", [x - 0.035, Ly - 0.04, rz - 0.06], [x + 0.035, Ly, rz + 0.06],
            "electrical", ["fig8.receptacle_x", "vr.receptacle_height", "fpm.electrical.receptacles"], label=n_t, wall="ymax")
        add(n_b.lower(), "receptacle", "power", [x - 0.035, 0.0, rz - 0.06], [x + 0.035, 0.04, rz + 0.06],
            "electrical", ["fig8.receptacle_x", "vr.receptacle_height", "fpm.electrical.receptacles"], label=n_b, wall="ymin")
    zc = L.num("vr.panel_center_height", "m")
    dx = to_m(L.num("fig8.disconnect_x", "in"), "in")
    add("disconnect", "box_unit", "power", [dx - 0.15, 0.0, zc - 0.2], [dx + 0.15, 0.15, zc + 0.2], "electrical",
        ["fig8.disconnect_x", "vr.panel_center_height"], label="DISC MAIN 100 A")
    py0, py1 = (Ly - to_m(v, "in") for v in L.val("fig8.panel_y_from_top"))
    add("breaker_panel", "box_unit", "power", [Lx - 0.1, min(py0, py1), zc - 0.3], [Lx, max(py0, py1), zc + 0.3],
        "electrical", ["fig8.panel_y_from_top", "vr.panel_center_height"], label="CBMAIN 100 A + CB1-CB4 20 A")
    cz = L.num("vr.conduit_height", "m")
    add("conduit_top", "conduit", "power", [rx[0], Ly - 0.03, cz], [Lx, Ly - 0.03, cz], "electrical",
        ["vr.conduit_height"], illustrative=True, drops=[[x, rz] for x in rx])
    add("conduit_bottom", "conduit", "power", [rx[0], 0.03, cz], [Lx, 0.03, cz], "electrical",
        ["vr.conduit_height"], illustrative=True, drops=[[x, rz] for x in rx] + [[dx, zc]])

    # --- roof solar array (10 panels, 4.4 kW nominal)
    sp = L.val("vr.solar_panel")
    roof_z = ext_lo[2] + ez
    add("solar_array", "solar_array", "power", [ext_lo[0], ext_lo[1], roof_z], [ext_lo[0] + ex, ext_lo[1] + ey, roof_z + 0.15],
        "roof", ["fpm.electrical.solar_panels", "fpm.electrical.solar_nominal", "vr.solar_panel"],
        n=int(L.num("fpm.electrical.solar_panels", "-")), panel=sp)

    # --- crew
    for k in (1, 2):
        c = P[f"crew_{k}"]
        add(f"crew_{k}", "mannequin", "crew", _m(c.lo), _m(c.hi), c.id, c.refs)

    spec = {"ledger_digest": L.digest(), "frame": "model frame, metres, z up", "interior_m": [Lx, Ly, H],
            "elements": el, "ledger_used": L.usage_report()}
    return spec


def main():
    out = OUT / "vr"
    out.mkdir(parents=True, exist_ok=True)
    spec = build_spec()
    (out / "scene_spec.json").write_text(json.dumps(spec, indent=1))
    n_ill = sum(e["illustrative"] for e in spec["elements"])
    print(f"{len(spec['elements'])} elements ({n_ill} illustrative), ledger {spec['ledger_digest']}")


if __name__ == "__main__":
    main()
