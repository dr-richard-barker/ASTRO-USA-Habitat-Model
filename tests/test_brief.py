"""Team brief: generated from results, readable (no internal coordinates), no promises the repo cannot back."""
import json

from habitat import ROOT
from habitat.brief import main


def test_brief_numbers_come_from_results():
    main()
    t = (ROOT / "TEAM_BRIEF.md").read_text()
    assert "y=0" not in t and "y=max" not in t and "we can supply" not in t
    lb = json.loads((ROOT / "results" / "light_budget.json").read_text())
    wall = next(v for k, v in lb["areas"].items() if k.startswith("NFT wall"))
    assert f"{wall['ppf_max_all_450W_to_light']:.0f} µmol/m²·s" in t
