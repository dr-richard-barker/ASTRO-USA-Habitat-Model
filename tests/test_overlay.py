"""The Figure 2 overlay gate passes on the build and fails on a mirrored plan (L010)."""
import shutil
from pathlib import Path

import numpy as np
import pytest
import trimesh

from habitat import OUT
from habitat.checks import fig2_overlay

CAD = OUT / "cad"
needs_build = pytest.mark.skipif(not (CAD / "stl").exists(), reason="run habitat.cad.build first")


@needs_build
def test_overlay_passes_on_build():
    assert fig2_overlay.run(out_dir=OUT / "checks")["pass"]


@needs_build
def test_overlay_fails_on_mirrored_plan(tmp_path):
    shutil.copytree(CAD / "stl", tmp_path / "stl")
    width_mm = 92.0 * 25.4
    for f in (tmp_path / "stl").glob("*.stl"):
        m = trimesh.load(f)
        m.vertices[:, 1] = width_mm - m.vertices[:, 1]   # mirror across the container's long axis
        m.export(f)
    assert not fig2_overlay.run(cad_dir=tmp_path, out_dir=tmp_path / "chk")["pass"]
