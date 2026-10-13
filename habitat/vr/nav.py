"""Engine-pack extras: box colliders and a walkable-floor navmesh for the FPM VR scene, from the scene spec.

    uv run python -m habitat.vr.nav          (after `make vr`)

Colliders: one box per physical element (named UCX_<element>, the prefix Unreal reads as collision) plus the room's
floor, ceiling, long walls, door-end wall and attic partition. Navmesh: the floor of the living space minus the
footprints of elements whose underside is below head clearance, grown by the agent radius (ledger vr.nav_*).

Gates (out/vr/NAV_QA.json): the navmesh is one connected piece; it reaches both the door end and the attic partition;
no navmesh vertex lies inside an obstacle footprint; every collider is a finite, non-empty box.
Outputs: out/vr/fpm_colliders.glb, out/vr/fpm_navmesh.glb, and a copy of the navmesh for the viewer's teleport.
"""
from __future__ import annotations

import json
import shutil

import manifold3d as mf
import numpy as np
import trimesh

from .. import OUT, ROOT
from ..provenance import Ledger

NOT_OBSTACLE = {"shell", "floor", "partition", "grille", "conduit", "solar_array", "mannequin"}
VR = OUT / "vr"


def to_gltf(p):
    p = np.asarray(p, float)
    return np.c_[p[:, 0], p[:, 2], -p[:, 1]]


def box(lo, hi) -> trimesh.Trimesh:
    lo, hi = np.asarray(lo, float), np.asarray(hi, float)
    m = trimesh.creation.box(extents=hi - lo)
    m.apply_translation((lo + hi) / 2)
    m.vertices = to_gltf(m.vertices)
    return m


def run() -> dict:
    L = Ledger()
    spec = json.loads((VR / "scene_spec.json").read_text())
    el = {e["id"]: e for e in spec["elements"]}
    r = L.num("vr.nav_agent_radius", "m")
    head = L.num("vr.nav_head_clearance", "m")
    part = el["attic_partition"]
    X, Y, Z = part["lo"][0], spec["interior_m"][1], spec["interior_m"][2]       # living space: door end to partition
    obstacles = [e for e in spec["elements"] if e["type"] not in NOT_OBSTACLE and e["lo"][2] < head
                 and e["lo"][0] < X and e["hi"][0] > 0]
    room = mf.CrossSection.square([X, Y])
    feet = [mf.CrossSection.square([e["hi"][0] - e["lo"][0], e["hi"][1] - e["lo"][1]]).translate([e["lo"][0], e["lo"][1]])
            for e in obstacles]
    blocked = mf.CrossSection.batch_boolean(feet, mf.OpType.Add) if feet else mf.CrossSection()
    walk = (room.offset(-r, mf.JoinType.Miter) - blocked.offset(r, mf.JoinType.Square)).simplify(1e-4)
    parts = walk.decompose()
    polys = walk.to_polygons()
    tri = np.asarray(mf.triangulate(polys))
    v2 = np.concatenate([np.asarray(p) for p in polys])
    nav = trimesh.Trimesh(vertices=to_gltf(np.c_[v2, np.full(len(v2), 0.005)]), faces=tri, process=False)
    # gates
    inside = 0
    for e in obstacles:
        m = ((v2[:, 0] > e["lo"][0] + 1e-6) & (v2[:, 0] < e["hi"][0] - 1e-6)
             & (v2[:, 1] > e["lo"][1] + 1e-6) & (v2[:, 1] < e["hi"][1] - 1e-6))
        inside += int(m.sum())
    lo2, hi2 = v2.min(0), v2.max(0)
    cols = {f"UCX_{e['id']}": box(e["lo"], e["hi"]) for e in obstacles}
    t = 0.05
    cols.update({"UCX_floor": box([0, 0, -t], [X, Y, 0]), "UCX_ceiling": box([0, 0, Z], [X, Y, Z + t]),
                 "UCX_wall_y0": box([0, -t, 0], [X, 0, Z]), "UCX_wall_ymax": box([0, Y, 0], [X, Y + t, Z]),
                 "UCX_wall_door_end": box([-t, 0, 0], [0, Y, Z]),
                 "UCX_attic_partition": box(part["lo"], part["hi"])})
    # narrowest clear aisle (no agent margin): along x, the gap between the nearest obstacles on either long side
    xs = np.arange(0.05, X - 0.05, 0.01)
    gap, sides = [], []
    for x in xs:
        here = [e for e in obstacles if e["lo"][0] <= x <= e["hi"][0]]
        lows = [e for e in here if e["hi"][1] < Y / 2 + 0.3]
        highs = [e for e in here if e["lo"][1] > Y / 2 - 0.3]
        lo_e = max(lows, key=lambda e: e["hi"][1], default=None)
        hi_e = min(highs, key=lambda e: e["lo"][1], default=None)
        gap.append((hi_e["lo"][1] if hi_e else Y) - (lo_e["hi"][1] if lo_e else 0.0))
        sides.append((lo_e["id"] if lo_e else "wall y=0", hi_e["id"] if hi_e else "wall y=max"))
    gap = np.array(gap)
    i_min = int(np.argmin(gap))
    gates = {"navmesh_connected": len(parts) == 1,
             "reaches_door_end": bool(lo2[0] <= r + 0.05),
             "reaches_partition": bool(hi2[0] >= X - r - 0.05),
             "no_vertex_inside_obstacle": inside == 0,
             "colliders_valid": all(np.isfinite(m.vertices).all() and m.volume > 0 for m in cols.values())}
    scene = trimesh.Scene()
    for name, m in cols.items():
        scene.add_geometry(m, node_name=name, geom_name=name)
    scene.export(VR / "fpm_colliders.glb")
    nav.export(VR / "fpm_navmesh.glb")
    shutil.copy(VR / "fpm_navmesh.glb", ROOT / "vr" / "web" / "assets" / "fpm_navmesh.glb")
    res = {"ledger_digest": L.digest(), "agent_radius_m": r, "head_clearance_m": head,
           "walkable_area_m2": round(walk.area(), 3), "floor_area_m2": round(X * Y, 3), "pieces": len(parts),
           "min_clear_aisle_m": round(float(gap[i_min]), 3), "min_clear_aisle_at_x_m": round(float(xs[i_min]), 2),
           "min_clear_aisle_between": list(sides[i_min]),
           "aisle_note": "clear width between equipment on the two long sides, no agent margin; a report, not a code check",
           "obstacles": [e["id"] for e in obstacles], "colliders": len(cols), "gates": gates,
           "pass": all(gates.values())}
    (VR / "NAV_QA.json").write_text(json.dumps(res, indent=1) + "\n")
    (ROOT / "results").mkdir(exist_ok=True)
    (ROOT / "results" / "nav.json").write_text(json.dumps(res, indent=1) + "\n")     # committed copy for the docs
    return res


if __name__ == "__main__":
    r = run()
    print(json.dumps({k: v for k, v in r.items() if k != "obstacles"}, indent=1))
    raise SystemExit(0 if r["pass"] else 1)
