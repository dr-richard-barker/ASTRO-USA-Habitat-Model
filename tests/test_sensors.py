"""Sensor candidates: laid on the walls, and dropped beside systems whose gas exchange the CFD does not model."""
import numpy as np

from habitat.cfd.sensors import candidates, excluded
from habitat.provenance import Ledger
from habitat.registry import build


def test_canopy_wall_positions_are_excluded():
    L = Ledger()
    _, parts = build(L)
    dom = next(p for p in parts if p.cfd_role == "domain")
    pts, walls = candidates(np.array(dom.lo) / 1000, np.array(dom.hi) / 1000, L)
    near, ids = excluded(pts, L)
    assert "nft_canopy" in ids and "myco_enclosure" in ids
    can = next(p for p in parts if p.id == "nft_canopy")
    behind = [i for i, w in enumerate(walls) if "y=max" in w and can.lo[0] / 1000 < pts[i, 0] < can.hi[0] / 1000]
    assert behind and near[behind].all()              # every hydroponic-wall position along the canopy is dropped
    assert (~near).sum() > 0.3 * len(pts)             # but most of the work-side wall stays available
