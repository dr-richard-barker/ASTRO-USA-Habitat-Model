"""Payload envelopes: placed inside the bay, unpowered in M0, powered heat lands on the bay, misfit refused."""
import pytest

from habitat.provenance import Ledger
from habitat.registry import build


def _ledger_with(**overrides):
    L = Ledger()
    for path, value in overrides.items():
        L.records[path]["value"] = value
    return L


def test_payloads_inside_bay_and_unpowered_in_m0():
    _, P = build()
    bay = next(p for p in P if p.id == "myco_enclosure")
    pay = [p for p in P if p.cfd_role == "payload"]
    assert {p.id for p in pay} == {"payload_bioreactor_rack", "payload_photobioreactor", "payload_incubator", "payload_sensor_module"}
    for p in pay:
        assert all(bl <= pl and ph <= bh for bl, pl, ph, bh in zip(bay.lo, p.lo, p.hi, bay.hi)), p.id
    assert bay.heat_W == 0.0


def test_powered_payload_heat_goes_to_bay():
    _, P = build(_ledger_with(**{"scenario_m0.payloads_powered": True}))
    bay = next(p for p in P if p.id == "myco_enclosure")
    assert bay.heat_W == pytest.approx(16.4)        # photobioreactor LED placeholder; others have no budget yet


def test_oversized_payload_is_refused():
    with pytest.raises(ValueError, match="do not fit"):
        build(_ledger_with(**{"payloads.bioreactor_rack.envelope": [2600.0, 507.6, 810.0]}))


def test_ports_lie_on_their_envelopes():
    _, P = build()
    for p in (q for q in P if q.cfd_role == "payload"):
        assert p.ports, p.id
        for port in p.ports:
            assert all(lo - 1 <= v <= hi + 1 for lo, v, hi in zip(p.lo, port["pos"], p.hi)), (p.id, port["name"])


def test_photobioreactor_inlet_faces_the_bioreactor_rack():
    _, P = build()
    rack = next(p for p in P if p.id == "payload_bioreactor_rack")
    pbr = next(p for p in P if p.id == "payload_photobioreactor")
    inlet = next(q for q in pbr.ports if q["name"] == "gas_in")
    assert inlet["dir"][0] < 0 and rack.hi[0] < inlet["pos"][0]


def test_powered_offgas_into_bay_adds_bioreactor_co2(tmp_path, monkeypatch):
    L = _ledger_with(**{"scenario_m0.payloads_powered": True})
    _, P = build(L)
    bay = next(p for p in P if p.id == "myco_enclosure")
    assert bay.co2_kg_s == pytest.approx(10 * 1.82e-3 / 86400)
    import habitat.cfd.case as C                 # and it reaches the CFD sources (bay = heated/gassy blockage shell)
    monkeypatch.setattr(C, "RUNS", tmp_path)
    monkeypatch.setattr(C, "build_registry", lambda **k: (L, P))
    meta = __import__("json").loads((C.build("coarse", 4) / "case_meta.json").read_text())
    assert meta["sources_total"]["co2_mol_s"] == pytest.approx(sum(p.co2_kg_s for p in P) / C.M_CO2)
    assert any(z["id"] == "myco_enclosure" and z["applied_as"] == "shell" for z in meta["parts"])


def test_other_route_adds_no_bay_co2():
    _, P = build(_ledger_with(**{"scenario_m0.payloads_powered": True, "payloads.layout.offgas_route": "photobioreactor"}))
    assert next(p for p in P if p.id == "myco_enclosure").co2_kg_s == 0.0


def test_port_value_mismatch_is_refused():
    with pytest.raises(ValueError, match="co2"):
        build(_ledger_with(**{"payloads.bioreactor_rack.co2_per_tube": 2.0}))
