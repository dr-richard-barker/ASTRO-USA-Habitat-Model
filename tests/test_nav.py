"""Navmesh and colliders: gates pass on the built scene (skipped until `make vr` has written the scene spec)."""
import pytest

from habitat import OUT


@pytest.mark.skipif(not (OUT / "vr" / "scene_spec.json").exists(), reason="needs `make vr`")
def test_nav_gates():
    from habitat.vr.nav import run
    r = run()
    assert r["pass"], r["gates"]
    assert 0 < r["walkable_area_m2"] < r["floor_area_m2"]
    assert 0.5 < r["min_clear_aisle_m"] < 2.34
