"""Case-writer guarantees (no Docker needed): turbulent scalar diffusivity, complete sources, closed domain."""
import json
import re

import pytest

from habitat.cfd import case as C
from habitat.registry import build


@pytest.fixture(scope="module")
def built(tmp_path_factory, monkeypatch_module=None):
    import habitat.cfd.case as mod
    old = mod.RUNS
    mod.RUNS = tmp_path_factory.mktemp("runs")
    try:
        yield mod.build("coarse", 4)
    finally:
        mod.RUNS = old


def test_scalar_transport_uses_turbulent_diffusivity(built):
    cd = (built / "system" / "controlDict").read_text()
    blocks = re.findall(r"transport_\w+\s*\{(.*?)\n    \}", cd, re.S)
    assert len(blocks) == 3
    for b in blocks:
        assert "alphaDt" in b and not re.search(r"^\s+D\s", b, re.M), "constant D would disable turbulent mixing"


def test_every_registry_watt_reaches_the_case(built):
    meta = json.loads((built / "case_meta.json").read_text())
    _, parts = build()
    assert meta["sources_total"]["heat_W"] == pytest.approx(sum(p.heat_W for p in parts))
    fv = (built / "constant" / "fvOptions").read_text()
    watts = sum(float(x) for x in re.findall(r"explicit\s+([0-9.eE+-]+);", fv))
    assert watts == pytest.approx(sum(p.heat_W for p in parts))


def test_dropped_source_is_detected(monkeypatch, tmp_path):
    import habitat.cfd.case as mod
    real = mod.build_registry

    def lossy(**k):
        L, parts = real(**k)
        for p in parts:
            if p.id == "battery_cabinet":
                p.cfd_role = "ignore"          # heat silently disappears from the CFD unless caught
        return L, parts
    monkeypatch.setattr(mod, "build_registry", lossy)
    monkeypatch.setattr(mod, "RUNS", tmp_path)
    with pytest.raises(AssertionError, match="source heat_W"):
        mod.build("coarse", 4)
