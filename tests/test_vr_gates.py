"""VR gates: the public scene passes, and a planted foreign mesh (stand-in for leaked private CAD) fails."""
import json
import struct
from pathlib import Path

import pytest

from habitat import OUT
from habitat.vr.build import gate, read_glb

GLB = OUT / "vr" / "fpm_vr_lod2.glb"
SPEC = OUT / "vr" / "scene_spec.json"
needs = pytest.mark.skipif(not GLB.exists(), reason="run habitat.vr.build first")


def _write_glb(path: Path, js: dict, binc: bytes):
    j = json.dumps(js).encode(); j += b" " * (-len(j) % 4)
    b = binc + b"\0" * (-len(binc) % 4)
    total = 12 + 8 + len(j) + 8 + len(b)
    path.write_bytes(struct.pack("<III", 0x46546C67, 2, total) + struct.pack("<II", len(j), 0x4E4F534A) + j
                     + struct.pack("<II", len(b), 0x004E4942) + b)


@needs
def test_public_scene_passes():
    assert gate(2, GLB, json.loads(SPEC.read_text()))["pass"]


@needs
def test_planted_canary_fails_allow_list(tmp_path):
    js, binc = read_glb(GLB)
    mesh_node = next(n for n in js["nodes"] if "mesh" in n and "extensions" not in n)
    canary = {**mesh_node, "name": "bioreactor_private_detail_CANARY",
              "extras": {"element": "bioreactor_private_detail", "layer": "payload", "illustrative": False}}
    js["nodes"].append(canary)
    js["scenes"][js.get("scene", 0)]["nodes"].append(len(js["nodes"]) - 1)
    bad = tmp_path / "leak.glb"
    _write_glb(bad, js, binc)
    r = gate(2, bad, json.loads(SPEC.read_text()))
    assert not r["gates"]["allow_list"] and "bioreactor_private_detail" in r["foreign_elements"]
