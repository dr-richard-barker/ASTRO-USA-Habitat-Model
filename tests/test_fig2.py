"""Figure 2 extraction: committed geometry is consistent, and the extractor's checks can fail."""
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PDF = ROOT / "sources/private/ICES-2026-251.pdf"
needs_pdf = pytest.mark.skipif(not PDF.exists(), reason="team PDF is private and not in the public repo")


def _mod():
    spec = importlib.util.spec_from_file_location("extract_fig2", ROOT / "sources/extract_fig2.py")
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    return m


def test_committed_geometry_is_self_consistent():
    g = json.loads((ROOT / "sources/fig2_geometry.json").read_text())
    assert g["footprint_in"] == [464.0, 92.0]
    assert len(g["dimension_check"]) == 22 and all(d["ok"] for d in g["dimension_check"])
    assert g["max_dimension_error_in"] < 0.1
    bottom = sorted([z for z in g["zones"] if z["bbox_in"][3] == 92.0 and z["label"] != "Attic"],
                    key=lambda z: z["bbox_in"][0])
    # bottom row chain closes: each zone starts where the previous ends (within 0.1 in), up to the 393 in line
    for a, b in zip(bottom, bottom[1:]):
        assert abs(a["bbox_in"][2] - b["bbox_in"][0]) < 0.1, (a, b)


@needs_pdf
def test_extractor_reproduces_committed_json(tmp_path):
    out = tmp_path / "g.json"
    _mod().main(str(PDF), str(out))
    a, b = json.loads(out.read_text()), json.loads((ROOT / "sources/fig2_geometry.json").read_text())
    assert a["zones"] == b["zones"]


@needs_pdf
def test_wrong_footprint_fails(tmp_path):
    m = _mod(); m.FOOTPRINT_IN = (460.0, 92.0)
    with pytest.raises(AssertionError, match="scales disagree"):
        m.main(str(PDF), str(tmp_path / "g.json"))


@needs_pdf
def test_tight_tolerance_fails(tmp_path):
    m = _mod(); m.DIM_TOL_IN = 0.01           # real errors reach 0.09 in, so this must fail
    with pytest.raises(AssertionError, match="disagree"):
        m.main(str(PDF), str(tmp_path / "g.json"))
