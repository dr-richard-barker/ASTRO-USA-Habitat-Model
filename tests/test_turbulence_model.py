"""The case writer follows ledger cfd.turbulence_model: k-epsilon cases get epsilon (not omega) everywhere."""
import json
import shutil

from habitat.cfd.case import build
from habitat.provenance import Ledger


def test_case_uses_ledger_model():
    model = Ledger().val("cfd.turbulence_model")
    c = build("coarse", 1, tag="_pytest_turb", scenario="m0", end_iter=1)
    try:
        assert f"RASModel {model};" in (c / "constant" / "turbulenceProperties").read_text()
        w = "epsilon" if model == "kEpsilon" else "omega"
        other = "omega" if w == "epsilon" else "epsilon"
        assert (c / "0" / w).exists() and not (c / "0" / other).exists()
        assert f"div(phi,{w})" in (c / "system" / "fvSchemes").read_text()
        assert json.loads((c / "case_meta.json").read_text())["turbulence_model"] == model
    finally:
        shutil.rmtree(c)
