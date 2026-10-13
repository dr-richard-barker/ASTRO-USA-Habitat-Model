"""Primary-habitat concept generator: analytic volumes, guideline check, clash detection."""
import math

import pytest

from habitat.primary import build
from habitat.provenance import Ledger


def _L(**over):
    L = Ledger()
    for k, v in over.items():
        L.records[k]["value"] = v
    return L


def test_volumes_are_analytic():
    s = build()
    m = s["metrics"]
    ri = 4.2 / 2 - 0.10
    assert m["by_element_m3"]["module_crew"] == pytest.approx(math.pi * ri ** 2 * 9.0)
    assert m["by_element_m3"]["node"] == pytest.approx(4 / 3 * math.pi * (2.5 - 0.10) ** 3)
    assert m["internal_pressurised_m3_excl_airlock"] == pytest.approx(sum(m["by_element_m3"].values()))


def test_guideline_comparison_flips_when_modules_shrink():
    small = [{"name": n, "diameter": 3.0, "length": 4.0, "functions": ["x"]} for n in ("crew", "lab", "food", "eclss")]
    m = build(_L(**{"primary.modules": small}))["metrics"]
    assert not m["nhv_by_habitable_fraction"]["0.40"]["meets_guideline"]


def test_clash_is_detected():
    # modules wider than the node (6 m on a 5 m node) with no tunnel: perpendicular modules overlap at the corners
    fat = [{"name": n, "diameter": 6.0, "length": 6.0, "functions": ["x"]} for n in ("crew", "lab", "food", "eclss")]
    with pytest.raises(ValueError, match="clash"):
        build(_L(**{"primary.modules": fat, "primary.hatch_tunnel": {"diameter": 1.3, "length": 0.0}}))
