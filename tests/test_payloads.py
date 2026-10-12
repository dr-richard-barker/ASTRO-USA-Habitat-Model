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
    assert bay.heat_W == pytest.approx(16.4)        # photobioreactor LED at design max; others have no budget yet


def test_oversized_payload_is_refused():
    with pytest.raises(ValueError, match="do not fit"):
        build(_ledger_with(**{"payloads.bioreactor_rack.envelope": [2600.0, 507.6, 810.0]}))
