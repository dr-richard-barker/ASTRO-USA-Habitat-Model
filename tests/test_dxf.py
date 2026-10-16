"""DXF exchange drawings: millimetre units and overall dimensions equal to the room from the registry."""
import subprocess
import sys

import ezdxf
import pytest

from habitat import ROOT
from habitat.drawings_cad import OUT
from habitat.registry import build


def test_dxf_dimensions_match_registry():
    # the command-line build (fixed hash seed), so the test leaves byte-identical tracked drawings behind
    subprocess.run([sys.executable, "-m", "habitat.drawings_cad"], cwd=ROOT, check=True, capture_output=True)
    room = {p.id: p for p in build()[1]}["interior"]
    want = {"FPM_plan.dxf": (room.hi[0], room.hi[1]), "FPM_section_AA.dxf": (room.hi[1], room.hi[2])}
    for name, (a, b) in want.items():
        d = ezdxf.readfile(OUT / name)
        assert d.header["$INSUNITS"] == 4
        dims = sorted(e.get_measurement() for e in d.modelspace().query("DIMENSION"))
        assert dims == pytest.approx(sorted([a, b]), abs=0.1)
