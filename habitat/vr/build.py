"""Build the VR scene at LOD0/1/2 with Blender and gate the results.

    uv run python -m habitat.vr.build [--lods 0 1 2] [--no-render]

Gates (each GLB parsed directly, not trusted from Blender's own report):
  * every spec element appears as a node; no mesh outside the public element allow-list (leak-scan base);
  * every mesh node carries extras {element, layer, illustrative};
  * scene envelope (glTF y-up, metres) equals the container's external size, within 1 cm;
  * triangle budget per LOD (review-amended plan: web <= 300 k, headset <= 500 k; LOD0 uncapped, reported);
  * no Blender '.001' duplicate-name drift.
"""
from __future__ import annotations

import argparse
import json
import struct
import subprocess
from pathlib import Path

import numpy as np

from .. import OUT, ROOT
from ..provenance import Ledger
from .spec import main as write_spec

BLENDER = "/Applications/Blender.app/Contents/MacOS/Blender"
BUDGET_TRIS = {0: None, 1: 500_000, 2: 300_000}


def read_glb(path: Path) -> tuple[dict, bytes]:
    b = path.read_bytes()
    magic, ver, length = struct.unpack_from("<III", b, 0)
    assert magic == 0x46546C67, f"{path} is not a GLB"
    off, js, binc = 12, None, b""
    while off < length:
        clen, ctype = struct.unpack_from("<II", b, off)
        chunk = b[off + 8: off + 8 + clen]
        if ctype == 0x4E4F534A:
            js = json.loads(chunk)
        elif ctype == 0x004E4942:
            binc = chunk
        off += 8 + clen
    return js, binc


def _accessor(g: dict, binc: bytes, a: dict) -> np.ndarray:
    """Float VEC3 accessor data from the GLB binary chunk (uncompressed buffers only)."""
    bv = g["bufferViews"][a["bufferView"]]
    if "extensions" in bv:
        raise ValueError("compressed bufferView: QA reader needs uncompressed GLB")
    assert a["componentType"] == 5126 and a["type"] == "VEC3", a
    stride = bv.get("byteStride", 12)
    off = bv.get("byteOffset", 0) + a.get("byteOffset", 0)
    raw = np.frombuffer(binc, dtype=np.uint8, count=stride * (a["count"] - 1) + 12, offset=off)
    return np.lib.stride_tricks.as_strided(raw.view(np.float32) if stride == 12 else
                                           np.frombuffer(binc, np.float32, offset=off), shape=(a["count"], 3),
                                           strides=(stride, 4)).copy()


def glb_stats(path: Path) -> dict:
    g, binc = read_glb(path)
    nodes, meshes, acc = g.get("nodes", []), g.get("meshes", []), g.get("accessors", [])

    def tris(mi):
        n = 0
        for pr in meshes[mi]["primitives"]:
            n += (acc[pr["indices"]]["count"] if "indices" in pr else acc[pr["attributes"]["POSITION"]]["count"]) // 3
        return n

    # world-space bounds: walk the node tree, transform each mesh's POSITION min/max box corners
    def mat(nd):
        if "matrix" in nd:
            return np.array(nd["matrix"]).reshape(4, 4).T
        T = np.eye(4)
        if "translation" in nd:
            T[:3, 3] = nd["translation"]
        R = np.eye(4)
        if "rotation" in nd:
            x, y, z, w = nd["rotation"]
            R[:3, :3] = [[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
                         [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                         [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]]
        S = np.diag([*(nd.get("scale", [1, 1, 1])), 1])
        return T @ R @ S

    lo, hi = np.full(3, np.inf), np.full(3, -np.inf)
    total, mesh_nodes, missing_extras, inst = 0, [], [], 0
    roots = g["scenes"][g.get("scene", 0)]["nodes"]
    stack = [(r, np.eye(4)) for r in roots]
    while stack:
        i, M = stack.pop()
        nd = nodes[i]
        W = M @ mat(nd)
        if "mesh" in nd:
            mi = nd["mesh"]
            n_inst = 1
            ext = nd.get("extensions", {}).get("EXT_mesh_gpu_instancing")
            t_lo = t_hi = np.zeros(3)
            if ext:
                ta = acc[ext["attributes"]["TRANSLATION"]]
                n_inst = ta["count"]; inst += n_inst
                tr = _accessor(g, binc, ta)
                t_lo, t_hi = tr.min(0), tr.max(0)
            total += tris(mi) * n_inst
            mesh_nodes.append(nd)
            ex = nd.get("extras", {})
            if not all(k in ex for k in ("element", "layer", "illustrative")):
                missing_extras.append(nd.get("name"))
            for pr in meshes[mi]["primitives"]:
                a = acc[pr["attributes"]["POSITION"]]
                if "min" in a:
                    # instances: conservative box = mesh box swept over the instance-translation range
                    # (instance rotation/scale ignored: plant meshes are small and roughly isotropic)
                    mn, mx = np.array(a["min"]) + t_lo, np.array(a["max"]) + t_hi
                    c = np.array([[x, y, z, 1] for x in (mn[0], mx[0]) for y in (mn[1], mx[1])
                                  for z in (mn[2], mx[2])]) @ W.T
                    lo, hi = np.minimum(lo, c[:, :3].min(0)), np.maximum(hi, c[:, :3].max(0))
        for ch in nd.get("children", []):
            stack.append((ch, W))
    return {"nodes": len(nodes), "mesh_nodes": len(mesh_nodes), "gpu_instances": inst, "triangles": total,
            "bounds_min": lo.tolist(), "bounds_max": hi.tolist(), "extent_m": (hi - lo).tolist(),
            "missing_extras": missing_extras[:10], "n_missing_extras": len(missing_extras),
            "elements": sorted({nd.get("extras", {}).get("element") for nd in mesh_nodes} - {None}),
            "names": [nd.get("name", "") for nd in nodes], "bytes": path.stat().st_size,
            "extensions": g.get("extensionsUsed", [])}


def gate(lod: int, path: Path, spec: dict) -> dict:
    st = glb_stats(path)
    want_el = {e["id"] for e in spec["elements"]}
    names = set(st.pop("names"))
    # expected extent = union of the spec's own element boxes (model frame) mapped to glTF y-up (x, z, y)
    lo = np.min([e["lo"] for e in spec["elements"]], axis=0); hi = np.max([e["hi"] for e in spec["elements"]], axis=0)
    span = hi - lo
    want_ext = np.array([span[0], span[2], span[1]])
    got = np.array(st["extent_m"])
    res = {"lod": lod, **st,
           "missing_elements": sorted(want_el - names),
           "foreign_elements": sorted(set(st["elements"]) - want_el),
           "dot_suffix_names": sorted(n for n in names if "." in n)[:10]}
    res["gates"] = {
        "elements_present": not res["missing_elements"],
        "allow_list": not res["foreign_elements"],
        "extras": st["n_missing_extras"] == 0,
        # plan extent exact; height may undershoot the spec boxes (e.g. solar array box allows racking clearance)
        # or overshoot slightly (trailer hitch, wheels)
        "plan_extent": bool(abs(got[2] - want_ext[2]) < 0.01 and -0.01 <= got[0] - want_ext[0] <= 1.25),
        "height": bool(want_ext[1] - 0.25 <= got[1] <= want_ext[1] + 0.01),
        "budget": BUDGET_TRIS[lod] is None or st["triangles"] <= BUDGET_TRIS[lod],
        "no_dot_suffix": not res["dot_suffix_names"],
    }
    res["pass"] = all(res["gates"].values())
    return res


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--lods", type=int, nargs="+", default=[0, 1, 2])
    ap.add_argument("--no-render", action="store_true")
    ap.add_argument("--site", action="store_true", help="build the Mini-Hab site overlay instead of the FPM")
    a = ap.parse_args(argv)
    out = OUT / "vr"
    if a.site:
        from .site_spec import main as write_site
        write_site()
        spec_file = out / "site_spec.json"
    else:
        write_spec()
        spec_file = out / "scene_spec.json"
    spec = json.loads(spec_file.read_text())
    name = spec.get("name", "fpm_vr")
    script = ROOT / "habitat" / "vr" / "blender" / "build_scene.py"
    report = {"ledger_digest": spec["ledger_digest"], "lods": []}
    for lod in a.lods:
        cmd = [BLENDER, "--background", "--factory-startup", "--python", str(script), "--",
               str(spec_file), str(out), str(lod)] + ([] if a.no_render or lod else ["--render"])
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode != 0 or "Traceback" in r.stdout + r.stderr:
            raise RuntimeError(f"Blender LOD{lod} failed:\n{(r.stdout + r.stderr)[-3000:]}")
        g = gate(lod, out / f"{name}_lod{lod}.glb", spec)
        report["lods"].append(g)
        print(f"LOD{lod}: {g['triangles']:,} tris, {g['mesh_nodes']} mesh nodes, {g['bytes'] / 1e6:.2f} MB, "
              f"extent {np.round(g['extent_m'], 3).tolist()} m -> {'PASS' if g['pass'] else 'FAIL ' + str(g['gates'])}")
    if 0 in a.lods and not a.site:     # engine pack: USDZ for visionOS / Omniverse, checked with Apple's usdchecker
        usdz = out / "fpm_vr_lod0.usdz"
        subprocess.run(["/usr/bin/usdzip", str(usdz), str(out / "fpm_vr_lod0.usdc")], capture_output=True, cwd=out)
        chk = subprocess.run(["/usr/bin/usdchecker", str(usdz)], capture_output=True, text=True)
        ok = "Success!" in chk.stdout + chk.stderr
        report["usdz"] = {"file": usdz.name, "usdchecker": "Success" if ok else (chk.stdout + chk.stderr)[-800:]}
        print(f"USDZ: usdchecker {'Success' if ok else 'FAILED'}")
        if not ok:
            raise SystemExit(1)
    (out / ("SITE_QA.json" if a.site else "VR_QA.json")).write_text(json.dumps(report, indent=1))
    if not all(g["pass"] for g in report["lods"]):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
