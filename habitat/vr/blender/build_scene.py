"""Blender 5.2 headless builder for the hyper-detailed VR scene (run by habitat/vr/build.py).

    Blender --background --factory-startup --python build_scene.py -- SPEC.json OUT_DIR LOD [--render]

Reads out/vr/scene_spec.json (registry + ledger, metres, model frame, z up). Builds every element
procedurally at the requested level of detail (LOD0 hyper, LOD1 headset, LOD2 web) by re-generating
geometry at lower resolution, never by decimation. Each object carries custom properties exported as
glTF extras: part, layer, element, illustrative, refs.

Cosmetic proportions that are not dimensions of record (rail sections, bevels, leaf shapes, louvre
counts) are collected in VISUAL below; anything with a real-world meaning comes from the spec.
"""
import json
import math
import sys
from pathlib import Path

import bpy
from mathutils import Matrix, Vector

argv = sys.argv[sys.argv.index("--") + 1:]
SPEC, OUT, LOD = Path(argv[0]).resolve(), Path(argv[1]).resolve(), int(argv[2])
RENDER = "--render" in argv
OUT.mkdir(parents=True, exist_ok=True)
spec = json.loads(SPEC.read_text())

# --- cosmetic constants (not dimensions of record) ------------------------------------------------
VISUAL = {
    "rail": 0.08, "post": 0.12, "casting": (0.178, 0.162, 0.118), "door_bar": 0.03,
    "sheet": 0.002, "frame": 0.025, "shelf": 0.018, "pipe": 0.016, "conduit": 0.012,
}
SEG = {0: 24, 1: 12, 2: 8}[LOD]                     # cylinder segments
LEAVES = {0: 14, 1: 8, 2: 5}[LOD]                   # leaves per rosette
LEAF_GRID = {0: (5, 3), 1: (3, 2), 2: (2, 1)}[LOD]  # (along, across) leaf subdivisions
LOUVRES = {0: 10, 1: 5, 2: 0}[LOD]

# --- scene reset ----------------------------------------------------------------------------------
bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene
scene.unit_settings.system = "METRIC"

# --- materials (metallic-roughness PBR, glTF-compatible, no image textures) -----------------------
_mats = {}


def mat(name, rgb, rough=0.6, metal=0.0, alpha=1.0, transmission=0.0):
    if name in _mats:
        return _mats[name]
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    b = m.node_tree.nodes.get("Principled BSDF")
    b.inputs["Base Color"].default_value = (*rgb, 1.0)
    b.inputs["Roughness"].default_value = rough
    b.inputs["Metallic"].default_value = metal
    if transmission:
        b.inputs["Transmission Weight"].default_value = transmission
    if alpha < 1.0:
        b.inputs["Alpha"].default_value = alpha
        m.surface_render_method = "BLENDED" if hasattr(m, "surface_render_method") else m.blend_method
    _mats[name] = m
    return m


M = {
    "steel_ext": mat("container_paint", (0.55, 0.57, 0.60), 0.55, 0.3),
    "steel_int": mat("container_interior", (0.80, 0.81, 0.82), 0.6, 0.2),
    "plywood": mat("floor_plywood", (0.55, 0.40, 0.25), 0.8),
    "alu": mat("aluminium", (0.80, 0.81, 0.83), 0.35, 1.0),
    "pvc": mat("pvc_white", (0.92, 0.92, 0.90), 0.45),
    "hdpe": mat("hdpe_black", (0.05, 0.05, 0.05), 0.55),
    "hdpe_blue": mat("hdpe_blue", (0.12, 0.30, 0.55), 0.5),
    "glass": mat("glass_acrylic", (0.85, 0.92, 0.95), 0.05, 0.0, alpha=0.25, transmission=0.9),
    "leaf": mat("leaf_green", (0.20, 0.55, 0.15), 0.6),
    "leaf2": mat("leaf_green_light", (0.45, 0.72, 0.25), 0.6),
    "seed": mat("seedling_green", (0.35, 0.70, 0.25), 0.6),
    "myco": mat("mycelium", (0.90, 0.88, 0.80), 0.8),
    "battery": mat("battery_case", (0.12, 0.13, 0.15), 0.5),
    "copper": mat("terminal", (0.85, 0.55, 0.30), 0.3, 1.0),
    "cabinet": mat("cabinet_steel", (0.30, 0.32, 0.35), 0.45, 0.6),
    "elec": mat("electrical_grey", (0.70, 0.71, 0.72), 0.5, 0.2),
    "wood": mat("bench_wood", (0.70, 0.55, 0.38), 0.6),
    "solar": mat("solar_cell", (0.05, 0.08, 0.20), 0.15, 0.2),
    "suit": mat("crew_suit", (0.20, 0.35, 0.60), 0.7),
    "skin": mat("crew_head", (0.80, 0.65, 0.55), 0.6),
    "unit": mat("hvac_white", (0.94, 0.95, 0.96), 0.4),
}

# --- primitives -------------------------------------------------------------------------------------
_names = set()


def uname(n):
    base, k = n, 1
    while n in _names:
        n = f"{base}_{k}"; k += 1
    _names.add(n)
    return n


def new_obj(name, me, material, parent, extra=None):
    if material is not None and not me.materials:
        me.materials.append(material)
    o = bpy.data.objects.new(uname(name), me)
    scene.collection.objects.link(o)
    o.parent = parent
    for k, v in (extra or {}).items():
        o[k] = v
    return o


def mesh_from(name, verts, faces):
    me = bpy.data.meshes.new(uname(name + "_mesh"))
    me.from_pydata([tuple(v) for v in verts], [], faces)
    me.update()
    return me


def box(name, lo, hi, material, parent, extra=None):
    x0, y0, z0 = lo; x1, y1, z1 = hi
    v = [(x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0), (x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)]
    f = [(0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)]
    return new_obj(name, mesh_from(name, v, f), material, parent, extra)


def cyl(name, p0, p1, r, material, parent, segs=None, extra=None, caps=True):
    segs = segs or SEG
    a, b = Vector(p0), Vector(p1)
    ax = (b - a).normalized()
    t = Vector((1, 0, 0)) if abs(ax.x) < 0.9 else Vector((0, 1, 0))
    u = ax.cross(t).normalized(); w = ax.cross(u)
    v, f = [], []
    for c in (a, b):
        for i in range(segs):
            th = 2 * math.pi * i / segs
            v.append(c + r * (math.cos(th) * u + math.sin(th) * w))
    for i in range(segs):
        j = (i + 1) % segs
        f.append((i, j, segs + j, segs + i))
    if caps:
        f.append(tuple(reversed(range(segs)))); f.append(tuple(range(segs, 2 * segs)))
    return new_obj(name, mesh_from(name, v, f), material, parent, extra)


def open_box(name, lo, hi, t, material, parent, extra=None):
    """Tub / trough: floor + 4 walls, open top."""
    x0, y0, z0 = lo; x1, y1, z1 = hi
    g = empty(name, parent, extra)
    box(name + "_floor", (x0, y0, z0), (x1, y1, z0 + t), material, g)
    box(name + "_w0", (x0, y0, z0), (x1, y0 + t, z1), material, g)
    box(name + "_w1", (x0, y1 - t, z0), (x1, y1, z1), material, g)
    box(name + "_w2", (x0, y0, z0), (x0 + t, y1, z1), material, g)
    box(name + "_w3", (x1 - t, y0, z0), (x1, y1, z1), material, g)
    return g


def empty(name, parent=None, extra=None):
    o = bpy.data.objects.new(uname(name), None)
    scene.collection.objects.link(o)
    o.parent = parent
    for k, v in (extra or {}).items():
        o[k] = v
    return o


# --- shared plant meshes (linked duplicates -> one mesh in the GLB, instanced) --------------------
def rosette_mesh(name, radius, leaves, grid, lift=0.35):
    na, nc = grid
    v, f = [], []
    for k in range(leaves):
        th = 2 * math.pi * (k / leaves) + (0.37 if k % 2 else 0.0)
        L = radius * (0.65 + 0.35 * ((k * 7919) % 13) / 12)
        wmax = L * 0.42
        base = len(v)
        for i in range(na + 1):
            s = i / na
            r = L * s
            z = lift * L * math.sin(math.pi * 0.5 * s) + 0.15 * L * (1 - s)
            width = wmax * math.sin(math.pi * min(1.0, s * 1.15)) + 0.002
            for j in range(nc + 1):
                q = (j / nc - 0.5) * width
                cupz = 0.25 * abs(q)
                x = r * math.cos(th) - q * math.sin(th)
                y = r * math.sin(th) + q * math.cos(th)
                v.append((x, y, z + cupz))
        for i in range(na):
            for j in range(nc):
                a = base + i * (nc + 1) + j
                f.append((a, a + 1, a + nc + 2, a + nc + 1))
    return mesh_from(name, v, f)


PLANTS = {}


def plant_mesh(kind, radius):
    key = (kind, round(radius, 4))
    if key not in PLANTS:
        leaves = {"seedling": max(3, LEAVES // 3)}.get(kind, LEAVES)
        grid = LEAF_GRID if kind != "seedling" else (max(1, LEAF_GRID[0] - 2), 1)
        me = rosette_mesh(f"plant_{kind}", radius, leaves, grid, 0.45 if kind == "seedling" else 0.35)
        me.materials.append(M["seed"] if kind == "seedling" else (M["leaf"] if kind != "kratky" else M["leaf2"]))
        PLANTS[key] = me
    return PLANTS[key]


def plant(name, kind, radius, loc, parent, up=(0, 0, 1)):
    me = plant_mesh(kind, radius)
    o = bpy.data.objects.new(uname(name), me)
    scene.collection.objects.link(o)
    o.parent = parent
    upv = Vector(up).normalized()
    rot = Vector((0, 0, 1)).rotation_difference(upv).to_matrix().to_4x4()
    o.matrix_world = Matrix.Translation(Vector(loc)) @ rot
    return o


# --- element builders -------------------------------------------------------------------------------
def corrugated_wall(name, x0, x1, y_face, z0, z1, depth, pitch, flat, outward, material, parent):
    """Trapezoidal corrugation along x on a wall at y_face; outward = +1/-1 (ridges toward that side)."""
    n = max(1, round((x1 - x0) / pitch))
    p = (x1 - x0) / n
    a = flat * p / 2                 # flat valley and flat ridge widths
    r = (p - 2 * a) / 2              # each sloping web
    prof = []
    for i in range(n):
        xa = x0 + i * p
        prof += [(xa, 0.0), (xa + a, 0.0), (xa + a + r, depth), (xa + 2 * a + r, depth)]
    prof.append((x1, 0.0))
    t = VISUAL["sheet"] * 3
    v, f = [], []
    for (x, d) in prof:
        y = y_face + outward * d
        v += [(x, y, z0), (x, y, z1), (x, y + outward * t, z0), (x, y + outward * t, z1)]
    for i in range(len(prof) - 1):
        a, b = 4 * i, 4 * (i + 1)
        f += [(a, b, b + 1, a + 1), (a + 2, a + 3, b + 3, b + 2), (a, a + 2, b + 2, b), (a + 1, b + 1, b + 3, a + 3)]
    return new_obj(name, mesh_from(name, v, f), material, parent)


def build_shell(e, g):
    lo, hi = e["lo"], e["hi"]; p = e["params"]
    clo, chi = p["cavity_lo"], p["cavity_hi"]
    c = p["corrugation"]
    r, post = VISUAL["rail"], VISUAL["post"]
    # bottom/top side rails and corner posts (frame)
    for yy, nm in ((lo[1], "a"), (hi[1] - r, "b")):
        box(f"rail_bottom_{nm}", (lo[0], yy, lo[2]), (hi[0], yy + r, clo[2]), M["steel_ext"], g)
        box(f"rail_top_{nm}", (lo[0], yy, chi[2]), (hi[0], yy + r, hi[2]), M["steel_ext"], g)
    for xx in (lo[0], hi[0] - post):
        for yy in (lo[1], hi[1] - post):
            box("corner_post", (xx, yy, lo[2]), (xx + post, yy + post, hi[2]), M["steel_ext"], g)
    cx, cy, cz = VISUAL["casting"]
    for xx in (lo[0], hi[0] - cx):
        for yy in (lo[1], hi[1] - cy):
            for zz in (lo[2], hi[2] - cz):
                box("corner_casting", (xx, yy, zz), (xx + cx, yy + cy, zz + cz), M["hdpe"], g)
    # long walls (corrugated, steel visible inside: no lining declared)
    corrugated_wall("side_wall_ymin", lo[0] + post, hi[0] - post, clo[1], clo[2], chi[2], c["depth"], c["pitch"],
                    c["flat_fraction"], -1, M["steel_ext"], g)
    corrugated_wall("side_wall_ymax", lo[0] + post, hi[0] - post, chi[1], clo[2], chi[2], c["depth"], c["pitch"],
                    c["flat_fraction"], +1, M["steel_ext"], g)
    # floor structure, roof, front (blind) end wall
    box("base_structure", (lo[0], lo[1], lo[2]), (hi[0], hi[1], clo[2] - 0.028), M["steel_ext"], g)
    box("roof_panel", (lo[0], lo[1], chi[2]), (hi[0], hi[1], chi[2] + 0.012), M["steel_ext"], g)
    box("end_wall_rear", (chi[0], clo[1], clo[2]), (hi[0], chi[1], chi[2]), M["steel_ext"], g)
    # cargo doors at the door end (two leaves, locking bars) - kept inside the ISO external envelope
    x0 = lo[0]
    ymid = (lo[1] + hi[1]) / 2
    bar_r = VISUAL["door_bar"] / 2
    for side, (ya, yb) in (("L", (lo[1] + post, ymid - 0.004)), ("R", (ymid + 0.004, hi[1] - post))):
        box(f"door_leaf_{side}", (x0 + 2 * bar_r + 0.005, ya, clo[2]), (x0 + 2 * bar_r + 0.035, yb, chi[2]), M["steel_ext"], g)
        for k in range(2):
            yb_ = ya + (yb - ya) * (0.3 + 0.4 * k)
            cyl(f"door_lock_bar_{side}{k}", (x0 + bar_r + 0.002, yb_, clo[2] + 0.1), (x0 + bar_r + 0.002, yb_, chi[2] - 0.1),
                bar_r, M["alu"], g)
    # floor of record handled by the 'floor' element


def build_floor(e, g):
    box("floor_plywood", e["lo"], e["hi"], M["plywood"], g)


def rect_minus(y0, y1, z0, z1, holes):
    """Split a (y, z) rectangle into cells that avoid the hole rectangles."""
    ys = sorted({y0, y1, *[h[0] for h in holes], *[h[1] for h in holes]})
    zs = sorted({z0, z1, *[h[2] for h in holes], *[h[3] for h in holes]})
    cells = []
    for i in range(len(ys) - 1):
        for j in range(len(zs) - 1):
            cy, cz = (ys[i] + ys[i + 1]) / 2, (zs[j] + zs[j + 1]) / 2
            if not any(h[0] < cy < h[1] and h[2] < cz < h[3] for h in holes):
                cells.append((ys[i], ys[i + 1], zs[j], zs[j + 1]))
    return cells


def build_partition(e, g):
    lo, hi = e["lo"], e["hi"]
    holes = [(o["lo"][1], o["hi"][1], o["lo"][2], o["hi"][2]) for o in e["params"]["openings"]]
    for k, (ya, yb, za, zb) in enumerate(rect_minus(lo[1], hi[1], lo[2], hi[2], holes)):
        box(f"partition_{k}", (lo[0], ya, za), (hi[0], yb, zb), M["steel_int"], g)


def build_grille(e, g):
    lo, hi = e["lo"], e["hi"]; fr = VISUAL["frame"] * 0.6
    x0, x1 = lo[0] - 0.012, lo[0] + 0.004
    box("grille_frame_top", (x0, lo[1] - fr, hi[2]), (x1, hi[1] + fr, hi[2] + fr), M["unit"], g)
    box("grille_frame_bot", (x0, lo[1] - fr, lo[2] - fr), (x1, hi[1] + fr, lo[2]), M["unit"], g)
    box("grille_frame_l", (x0, lo[1] - fr, lo[2]), (x1, lo[1], hi[2]), M["unit"], g)
    box("grille_frame_r", (x0, hi[1], lo[2]), (x1, hi[1] + fr, hi[2]), M["unit"], g)
    for k in range(LOUVRES):
        z = lo[2] + (k + 0.5) * (hi[2] - lo[2]) / LOUVRES
        box("louvre", (x0 + 0.004, lo[1], z - 0.003), (x1, hi[1], z + 0.003), M["unit"], g)


def build_box_unit(e, g):
    box(e["id"] + "_body", e["lo"], e["hi"], M["unit"] if e["layer"] == "air" else M["elec"], g)


def build_nft_wall(e, g):
    p = e["params"]; lo, hi = e["lo"], e["hi"]
    nt, ns = p["towers"], p["sites"]
    pitch = (hi[0] - lo[0]) / nt
    wall = p["wall_y"]
    yb = wall - 0.1016                    # 4 in stand-off (Fig 2) = back of the channel band
    yf = yb - p["channel_d"]
    zt0, zt1 = lo[2] - 0.08, hi[2] + 0.06
    plants_g = empty("nft_plants", g)
    for i in range(nt):
        xc = lo[0] + (i + 0.5) * pitch
        box(f"nft_channel_{i:02d}", (xc - p["channel_w"] / 2, yf, zt0), (xc + p["channel_w"] / 2, yb, zt1), M["pvc"], g)
        for j in range(ns):
            zc = lo[2] + (j + 0.5) * (hi[2] - lo[2]) / ns
            cyl(f"net_cup_{i:02d}_{j:02d}", (xc, yf + 0.005, zc), (xc, yf - 0.03, zc), p["cup_d"] / 2, M["hdpe"], g,
                segs=max(6, SEG // 2))
            plant(f"nft_plant_{i:02d}_{j:02d}", "nft", p["plant_r"], (xc, yf - 0.035, zc), plants_g,
                  up=(0, -0.75, 0.66))
    if LOD < 2:     # supply manifold (illustrative plumbing)
        cyl("nft_supply_manifold", (lo[0], yb - p["channel_d"] / 2, zt1 + 0.05), (hi[0], yb - p["channel_d"] / 2, zt1 + 0.05),
            VISUAL["pipe"], M["pvc"], g, extra={"illustrative": True})
    tl, th = p["trough_lo"], p["trough_hi"]
    open_box("nft_trough", tl, th, 0.006, M["pvc"], g)


def build_glass_enclosure(e, g):
    lo, hi = e["lo"], e["hi"]; fr = VISUAL["frame"]
    for (a, b) in [((lo[0], lo[1], lo[2]), (hi[0], lo[1] + fr, lo[2] + fr)), ((lo[0], hi[1] - fr, lo[2]), (hi[0], hi[1], lo[2] + fr)),
                   ((lo[0], lo[1], hi[2] - fr), (hi[0], lo[1] + fr, hi[2])), ((lo[0], hi[1] - fr, hi[2] - fr), (hi[0], hi[1], hi[2]))]:
        box("enclosure_rail", a, b, M["alu"], g)
    for xx in (lo[0], hi[0] - fr):
        for yy in (lo[1], hi[1] - fr):
            box("enclosure_post", (xx, yy, lo[2]), (xx + fr, yy + fr, hi[2]), M["alu"], g)
    t = 0.006
    box("glass_front", (lo[0] + fr, lo[1], lo[2] + fr), (hi[0] - fr, lo[1] + t, hi[2] - fr), M["glass"], g)
    box("glass_top", (lo[0] + fr, lo[1] + fr, hi[2] - t), (hi[0] - fr, hi[1] - fr, hi[2]), M["glass"], g)
    for xx in (lo[0], hi[0] - t):
        box("glass_end", (xx, lo[1] + fr, lo[2] + fr), (xx + t, hi[1] - fr, hi[2] - fr), M["glass"], g)
    ns = e["params"]["shelves"]
    tubes = empty("mycoponic_tubes", g, {"illustrative": True})
    for k in range(ns):
        z = lo[2] + (k + 1) * (hi[2] - lo[2]) / (ns + 1)
        box(f"enclosure_shelf_{k}", (lo[0] + fr, lo[1] + fr, z - VISUAL["shelf"]), (hi[0] - fr, hi[1] - fr, z), M["alu"], g)
        if LOD < 2:
            n = int((hi[0] - lo[0] - 2 * fr) / 0.09)
            for i in range(n):
                xc = lo[0] + fr + (i + 0.5) * (hi[0] - lo[0] - 2 * fr) / n
                for yy in (lo[1] + (hi[1] - lo[1]) * 0.33, lo[1] + (hi[1] - lo[1]) * 0.66):
                    cyl("myco_tube", (xc, yy, z), (xc, yy, z + 0.10), 0.025, M["myco"], tubes, segs=max(6, SEG // 2))


def build_shelf_rack(e, g):
    lo, hi = e["lo"], e["hi"]; p = e["params"]; pst = VISUAL["frame"]
    for xx in (lo[0], hi[0] - pst):
        for yy in (lo[1], hi[1] - pst):
            box("rack_post", (xx, yy, lo[2]), (xx + pst, yy + pst, hi[2]), M["cabinet"], g)
    n = p["levels"]
    seedlings = empty("seedlings", g)
    for k in range(n):
        z = lo[2] + 0.12 + k * (hi[2] - lo[2] - 0.15) / n
        box(f"rack_tray_{k}", (lo[0] + 0.005, lo[1] + 0.005, z), (hi[0] - 0.005, hi[1] - 0.005, z + 0.04), M["hdpe"], g)
        if LOD < 2:
            nx, ny = max(1, int((hi[0] - lo[0]) / 0.07)), max(1, int((hi[1] - lo[1]) / 0.07))
            for i in range(nx):
                for j in range(ny):
                    plant(f"seedling_{k}_{i}_{j}", "seedling", p["plant_r"],
                          (lo[0] + (i + 0.5) * (hi[0] - lo[0]) / nx, lo[1] + (j + 0.5) * (hi[1] - lo[1]) / ny, z + 0.04), seedlings)


def build_kratky(e, g):
    lo, hi = e["lo"], e["hi"]; p = e["params"]
    open_box("kratky_tub", lo, hi, 0.006, M["hdpe_blue"], g)
    box("kratky_lid", (lo[0], lo[1], hi[2] - 0.01), (hi[0], hi[1], hi[2]), M["hdpe"], g)
    n_lid = max(2, int((hi[0] - lo[0]) / 0.3))
    lid_g, shelf_g = empty("kratky_lid_plants", g), empty("kratky_shelf_plants", g)
    for i in range(n_lid):
        plant(f"kratky_lid_plant_{i}", "kratky", p["plant_r"], (lo[0] + (i + 0.5) * (hi[0] - lo[0]) / n_lid, (lo[1] + hi[1]) / 2, hi[2]), lid_g)
    b = p["bucket"]
    for s, zs in enumerate(p["shelf_z"]):
        box(f"kratky_shelf_{s}", (lo[0], 0.0, zs - VISUAL["shelf"]), (hi[0], b + 0.04, zs), M["wood"], g)
        for i in range(p["per_shelf"]):
            xc = lo[0] + (i + 0.5) * (hi[0] - lo[0]) / p["per_shelf"]
            box(f"kratky_bucket_{s}_{i}", (xc - b / 2, 0.02, zs), (xc + b / 2, 0.02 + b, zs + b), M["hdpe_blue"], g)
            plant(f"kratky_plant_{s}_{i}", "kratky", p["plant_r"] * 0.7, (xc, 0.02 + b / 2, zs + b), shelf_g)


def build_dutch(e, g):
    lo, hi = e["lo"], e["hi"]; p = e["params"]
    open_box(e["id"] + "_bucket", lo, hi, 0.008, M["hdpe"], g)
    cx, cy = (lo[0] + hi[0]) / 2, (lo[1] + hi[1]) / 2
    top = min(p["ceiling"] - 0.2, hi[2] + 1.4)
    cyl("dutch_stake", (cx, cy, hi[2] - 0.2), (cx, cy, top), 0.008, M["wood"], g, segs=6, extra={"illustrative": True})
    n = {0: 9, 1: 5, 2: 3}[LOD]
    leaves_g = empty(e["id"] + "_leaves", g)
    for k in range(n):
        z = hi[2] + 0.1 + k * (top - hi[2] - 0.2) / n
        th = k * 2.4
        plant(f"dutch_leaf_cluster_{k}", "dutch", p["plant_r"] * 0.55, (cx + 0.05 * math.cos(th), cy + 0.05 * math.sin(th), z), leaves_g,
              up=(math.cos(th) * 0.5, math.sin(th) * 0.5, 0.7))


def build_battery_cabinet(e, g):
    lo, hi = e["lo"], e["hi"]; p = e["params"]; t = 0.012
    box("cabinet_back", (lo[0], lo[1], lo[2]), (hi[0], lo[1] + t, hi[2]), M["cabinet"], g)
    box("cabinet_top", (lo[0], lo[1], hi[2] - t), (hi[0], hi[1], hi[2]), M["cabinet"], g)
    for xx in (lo[0], hi[0] - t):
        box("cabinet_side", (xx, lo[1], lo[2]), (xx + t, hi[1], hi[2]), M["cabinet"], g)
    L, W, Hb = p["block"]
    tiers, per = 4, max(1, p["n"] // 4)
    for k in range(tiers):
        z = lo[2] + 0.02 + k * (hi[2] - lo[2] - 0.05) / tiers
        box(f"cabinet_shelf_{k}", (lo[0] + t, lo[1] + t, z - 0.01), (hi[0] - t, hi[1], z), M["cabinet"], g)
        for i in range(per):
            x = lo[0] + t + 0.01 + i * (hi[0] - lo[0] - 2 * t) / per
            blk = box(f"battery_BT{k * per + i + 1:02d}", (x, lo[1] + 0.08, z), (x + min(L, (hi[0] - lo[0]) / per - 0.02),
                      lo[1] + 0.08 + W, z + Hb), M["battery"], g, extra={"illustrative": True})
            if LOD == 0:
                for d in (0.03, 0.12):
                    cyl("terminal", (x + d, lo[1] + 0.08 + W / 2, z + Hb), (x + d, lo[1] + 0.08 + W / 2, z + Hb + 0.02),
                        0.009, M["copper"], g, segs=8)
    box("inverter_charge_controller", (lo[0] + 0.1, lo[1] + 0.05, hi[2]), (lo[0] + 0.6, lo[1] + 0.3, hi[2] + 0.35),
        M["elec"], g, extra={"illustrative": True})


def build_workbench(e, g):
    lo, hi = e["lo"], e["hi"]; t = e["params"]["top_t"]; leg = 0.05
    box("bench_top", (lo[0], lo[1], hi[2] - t), (hi[0], hi[1], hi[2]), M["wood"], g)
    for xx in (lo[0] + 0.05, hi[0] - 0.05 - leg, (lo[0] + hi[0]) / 2):
        for yy in (lo[1] + 0.05, hi[1] - 0.05 - leg):
            box("bench_leg", (xx, yy, lo[2]), (xx + leg, yy + leg, hi[2] - t), M["alu"], g)
    box("bench_shelf", (lo[0] + 0.05, lo[1] + 0.05, 0.15), (hi[0] - 0.05, hi[1] - 0.05, 0.17), M["wood"], g)


def build_receptacle(e, g):
    lo, hi = e["lo"], e["hi"]
    box(e["id"] + "_plate", lo, hi, M["elec"], g)
    if LOD == 0:
        inward = 1 if e["params"]["wall"] == "ymin" else -1
        yface = hi[1] if inward > 0 else lo[1]
        for dz in (-0.025, 0.025):
            zc = (lo[2] + hi[2]) / 2 + dz
            box("outlet_face", (lo[0] + 0.015, yface, zc - 0.012), (hi[0] - 0.015, yface + inward * 0.004, zc + 0.012), M["unit"], g)


def build_conduit(e, g):
    lo, hi = e["lo"], e["hi"]; r = VISUAL["conduit"]
    cyl("conduit_run", lo, hi, r, M["alu"], g, segs=max(6, SEG // 3))
    for x, z in e["params"]["drops"]:
        cyl("conduit_drop", (x, lo[1], lo[2]), (x, lo[1], z + 0.07), r, M["alu"], g, segs=max(6, SEG // 3))


def build_solar(e, g):
    lo, hi = e["lo"], e["hi"]; p = e["params"]; pl, pw, pt = p["panel"]
    n = p["n"]; cols = 2; rows = math.ceil(n / cols)
    span_x = rows * pl; x0 = (lo[0] + hi[0]) / 2 - span_x / 2
    y0 = (lo[1] + hi[1]) / 2 - cols * pw / 2
    z = lo[2] + 0.10
    for yy in (y0 + 0.2, y0 + cols * pw - 0.25):
        box("solar_rail", (x0, yy, lo[2]), (x0 + span_x, yy + 0.04, z), M["alu"], g, extra={"illustrative": True})
    k = 0
    for i in range(rows):
        for j in range(cols):
            if k >= n:
                break
            k += 1
            a = (x0 + i * pl + 0.01, y0 + j * pw + 0.01, z)
            b = (x0 + (i + 1) * pl - 0.01, y0 + (j + 1) * pw - 0.01, z + pt)
            pg = empty(f"SP{k}", g, {"part": f"SP{k}", "layer": "power"})
            box(f"SP{k}_frame", a, b, M["alu"], pg)
            box(f"SP{k}_cells", (a[0] + 0.02, a[1] + 0.02, b[2]), (b[0] - 0.02, b[1] - 0.02, b[2] + 0.002), M["solar"], pg)


def build_mannequin(e, g):
    lo, hi = e["lo"], e["hi"]; h = hi[2] - lo[2]
    cx, cy = (lo[0] + hi[0]) / 2, (lo[1] + hi[1]) / 2
    w = (hi[0] - lo[0]) / 2
    cyl("leg_l", (cx - w * 0.3, cy, 0), (cx - w * 0.3, cy, h * 0.47), w * 0.22, M["suit"], g)
    cyl("leg_r", (cx + w * 0.3, cy, 0), (cx + w * 0.3, cy, h * 0.47), w * 0.22, M["suit"], g)
    cyl("torso", (cx, cy, h * 0.47), (cx, cy, h * 0.82), w * 0.62, M["suit"], g)
    cyl("arm_l", (cx - w * 0.78, cy, h * 0.80), (cx - w * 0.85, cy, h * 0.45), w * 0.14, M["suit"], g)
    cyl("arm_r", (cx + w * 0.78, cy, h * 0.80), (cx + w * 0.85, cy, h * 0.45), w * 0.14, M["suit"], g)
    cyl("head", (cx, cy, h * 0.84), (cx, cy, h * 0.98), w * 0.32, M["skin"], g, segs=max(8, SEG // 2))


BUILD = {"shell": build_shell, "floor": build_floor, "partition": build_partition, "grille": build_grille,
         "box_unit": build_box_unit, "nft_wall": build_nft_wall, "glass_enclosure": build_glass_enclosure,
         "shelf_rack": build_shelf_rack, "kratky": build_kratky, "dutch_bucket": build_dutch,
         "battery_cabinet": build_battery_cabinet, "workbench": build_workbench, "receptacle": build_receptacle,
         "conduit": build_conduit, "solar_array": build_solar, "mannequin": build_mannequin}

root = empty("astro_usa_fpm", None, {"ledger_digest": spec["ledger_digest"], "lod": LOD,
                                    "note": "Generated from the sourced ledger; illustrative=true marks stand-in equipment"})
for e in spec["elements"]:
    g = empty(e["id"], root, {"part": e["parent"], "element": e["id"], "layer": e["layer"],
                              "illustrative": bool(e["illustrative"]), "refs": ",".join(e["refs"]),
                              **({"label": e["params"]["label"]} if "label" in e["params"] else {})})
    BUILD[e["type"]](e, g)

# propagate element metadata to every mesh (so a picked mesh knows its part/layer)
for o in scene.objects:
    if o.type in ("MESH", "EMPTY") and "element" not in o.keys():
        p = o.parent
        while p is not None and "element" not in p.keys():
            p = p.parent
        if p is not None:
            for k in ("part", "element", "layer"):
                o[k] = p[k]
            o["illustrative"] = bool(o.get("illustrative", False) or p["illustrative"])

stats = {"lod": LOD, "objects": sum(o.type == "MESH" for o in scene.objects),
         "triangles": sum(sum(len(pl.vertices) - 2 for pl in o.data.polygons) for o in scene.objects if o.type == "MESH"),
         "unique_meshes": len({o.data.name for o in scene.objects if o.type == "MESH"}),
         "names_with_dot_suffix": [o.name for o in scene.objects if "." in o.name][:10]}

base = OUT / f"fpm_vr_lod{LOD}"
bpy.ops.export_scene.gltf(filepath=str(base) + ".glb", export_format="GLB", export_extras=True, export_yup=True,
                          export_apply=True, export_gpu_instances=True,
                          export_meshopt_compression_enable=False)   # files are < 2 MB; keeps the QA reader and viewer decoder-free
if LOD == 0:
    bpy.ops.wm.usd_export(filepath=str(base) + ".usdc", export_materials=True)
    bpy.ops.export_scene.fbx(filepath=str(base) + ".fbx", use_custom_props=True, apply_unit_scale=True)
bpy.ops.wm.save_as_mainfile(filepath=str(base) + ".blend")


# --- review renders (EEVEE) -------------------------------------------------------------------------
def render(name, loc, target, lens=18, res=(1600, 900)):
    cam_d = bpy.data.cameras.new(name); cam_d.lens = lens
    cam = bpy.data.objects.new(name, cam_d); scene.collection.objects.link(cam)
    cam.location = loc
    cam.rotation_euler = (Vector(target) - Vector(loc)).to_track_quat("-Z", "Y").to_euler()
    scene.camera = cam
    scene.render.resolution_x, scene.render.resolution_y = res
    scene.render.filepath = str(OUT / f"render_lod{LOD}_{name}.png")
    bpy.ops.render.render(write_still=True)


if RENDER:
    scene.render.engine = "BLENDER_EEVEE"
    scene.view_settings.view_transform = "AgX"
    scene.view_settings.look = "AgX - Medium High Contrast"
    scene.view_settings.exposure = -0.4
    world = bpy.data.worlds.new("sky"); scene.world = world; world.use_nodes = True
    world.node_tree.nodes["Background"].inputs[0].default_value = (0.75, 0.82, 0.92, 1)
    world.node_tree.nodes["Background"].inputs[1].default_value = 0.6
    Lx, Ly, Hh = spec["interior_m"]
    for k in range(6):                                   # ceiling light strips (render only, not exported)
        ld = bpy.data.lights.new(f"ceiling_light_{k}", "AREA"); ld.energy = 90; ld.size = 1.2
        lo_ = bpy.data.objects.new(f"ceiling_light_{k}", ld); scene.collection.objects.link(lo_)
        lo_.location = ((k + 0.5) * Lx / 6, Ly / 2, Hh - 0.05)
    sun = bpy.data.lights.new("sun", "SUN"); sun.energy = 3
    so = bpy.data.objects.new("sun", sun); scene.collection.objects.link(so); so.rotation_euler = (0.7, 0.2, 0.8)
    render("exterior", (-4.0, -6.5, 5.5), (Lx / 2, Ly / 2, 1.0), lens=24)
    for o in scene.objects:                              # cut-away: hide roof, solar array and everything on the near wall
        el_ = o.get("element", "")
        if (o.name.startswith(("roof_panel", "side_wall_ymin", "rail_top_a")) or el_ in ("solar_array", "conduit_bottom")
                or el_ in ("recp5", "recp6", "recp7", "recp8", "disconnect")):
            o.hide_render = True
    render("cutaway", (Lx * 0.45, -3.2, 4.2), (Lx * 0.45, Ly * 0.6, 0.8), lens=16)
    for o in scene.objects:
        o.hide_render = False
    render("aisle_from_door", (0.45, Ly * 0.45, 1.62), (Lx, Ly * 0.5, 1.2), lens=16)

(OUT / f"blender_stats_lod{LOD}.json").write_text(json.dumps(stats, indent=1))
print("BLENDER_STATS", json.dumps(stats))
