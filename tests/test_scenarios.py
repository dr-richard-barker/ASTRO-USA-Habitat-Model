"""Scenario ledgers override M0 key by key; everything they do not list is inherited, and refs say which was used."""
import pytest

from habitat.registry import build


def _crew(parts):
    return [p for p in parts if p.id.startswith("crew_")]


def test_s2_overrides_crew_only():
    _, m0 = build(scenario="m0")
    _, s2 = build(scenario="s2")
    assert len(_crew(m0)) == 2 and len(_crew(s2)) == 6
    assert "scenario_s2.crew_x" in _crew(s2)[0].refs
    sup = {p.id: p for p in s2}["hvac_supply"]
    assert "scenario_m0.hvac.supply_flow" in sup.refs                 # inherited, and says so


def test_s5_scales_flow_and_keeps_crew():
    q = {sc: {p.id: p for p in build(scenario=sc)[1]}["hvac_supply"].opening["flow_m3_s"] for sc in ("m0", "s5a", "s5b")}
    assert q["s5a"] == pytest.approx(q["m0"] / 2) and q["s5b"] == pytest.approx(2 * q["m0"])
    assert len(_crew(build(scenario="s5a")[1])) == 2


def test_s2_crew_clear_of_equipment():
    _, parts = build(scenario="s2")
    solid = [p for p in parts if p.cfd_role in ("blockage", "payload")]
    for c in _crew(parts):
        assert not any(all(c.lo[i] < b.hi[i] and c.hi[i] > b.lo[i] for i in range(3)) for b in solid), c.id


def test_unknown_scenario_refused():
    with pytest.raises(KeyError):
        build(scenario="s99")
