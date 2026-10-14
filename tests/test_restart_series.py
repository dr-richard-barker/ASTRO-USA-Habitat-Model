"""Restarted runs: time series are stitched without the re-run overlap."""
from habitat.cfd.post import _dat


def test_restart_overlap_dropped(tmp_path):
    a = tmp_path / "postProcessing" / "fo" / "0"; b = tmp_path / "postProcessing" / "fo" / "10"
    a.mkdir(parents=True); b.mkdir(parents=True)
    (a / "s.dat").write_text("# Time v\n" + "".join(f"{t} {t}\n" for t in range(0, 15)))
    (b / "s.dat").write_text("# Time v\n" + "".join(f"{t} {t}\n" for t in range(10, 20)))
    cols, arr = _dat(tmp_path, "fo")
    t = list(arr[:, 0])
    assert t == sorted(set(t)) and t[0] == 0 and t[-1] == 19 and len(t) == 20
