"""Light budget: photon physics checked against a published value; the FPM bound sits below the crop-model range."""
import pytest

from habitat.light_budget import run, umol_per_J


def test_photon_flux_matches_kusuma_2020():
    # Kusuma, Pattison & Bugbee (2020): "red photons centered at 660nm can provide 5.52 µmol J-1"
    assert umol_per_J(660) == pytest.approx(5.52, abs=0.005)


def test_budget_bounds_are_consistent():
    r = run()
    for a in r["areas"].values():
        assert a["ppf_max_all_450W_to_light"] * a["area_m2"] == pytest.approx(
            r["inputs"]["load_max_W"] * r["inputs"]["fixture_umol_J"], rel=1e-3)
    assert r["below_mec_range_in_every_bound"]
