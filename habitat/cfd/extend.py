"""Continue a finished transient case from its last written time to a new end time (OpenFOAM restart).

    from habitat.cfd.extend import extend; extend(Path("runs/fpm_s6_coarse_ke_tr"), new_end_s)

Uses the case's own decomposition (processor*/ directories) and restarts from the latest time they hold; the
fieldAverage means continue from the saved means, so the averaging window still starts at the case's avg_from_s.
writeInterval is reset so that a write lands exactly on the new end time (the defect this tool also repairs:
cases whose endTime was not a multiple of writeInterval never wrote their final fields). The previous solver log is
kept as log.buoyantPimpleFoam.partN; the time series stitch across the restart (post._dat drops the re-run overlap).
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from . import foam


def times(d: Path) -> list[float]:
    return sorted(float(p.name) for p in d.iterdir() if p.is_dir() and re.fullmatch(r"\d+(\.\d+)?", p.name))


def extend(case: Path, new_end: float, reset_average: bool = False) -> Path:
    """reset_average: start a fresh averaging window at the restart (fieldAverage restartOnRestart) and move the
    gates' window (case_meta avg_from_s) to the restart time: for runs that were still drifting when averaging began."""
    case = case.resolve()
    procs = sorted(case.glob("processor*"))
    if not procs:
        raise ValueError(f"{case.name}: no processor directories to restart from")
    t_last = times(procs[0])[-1]
    if new_end <= t_last + 1e-6:
        raise ValueError(f"{case.name}: new end {new_end} is not after the last write {t_last}")
    meta = json.loads((case / "case_meta.json").read_text())
    tr = meta["transient"]
    wi0 = tr["t_flush_s"] / 2
    n = max(1, round((new_end - t_last) / wi0))
    wi = (new_end - t_last) / n                                  # writes at t_last + k wi, the last one at new_end
    cd = (case / "system" / "controlDict").read_text()
    cd = re.sub(r"\nendTime [^;]+;", f"\nendTime {new_end:.6f};", cd, count=1)
    cd = re.sub(r"\nwriteInterval [^;]+;", f"\nwriteInterval {wi:.6f};", cd, count=1)
    if "startFrom latestTime;" not in cd:
        raise ValueError(f"{case.name}: controlDict does not restart from latestTime")
    if reset_average:
        if "type fieldAverage;" not in cd:
            raise ValueError(f"{case.name}: no fieldAverage function to reset")
        if "restartOnRestart" not in cd:
            cd = cd.replace("type fieldAverage;", "type fieldAverage; restartOnRestart true;", 1)
    (case / "system" / "controlDict").write_text(cd)
    log = case / "log.buoyantPimpleFoam"
    if log.exists():
        k = 1
        while (case / f"log.buoyantPimpleFoam.part{k}").exists():
            k += 1
        log.rename(case / f"log.buoyantPimpleFoam.part{k}")
    (case / "STATUS").write_text("RUNNING extend\n")
    try:
        foam.run(case, ["par:buoyantPimpleFoam", "reconstructPar -latestTime"], nprocs=len(procs))
    except BaseException as e:  # noqa: BLE001
        (case / "STATUS").write_text(f"FAILED: extend: {type(e).__name__}\n")
        raise
    if reset_average:            # OpenFOAM ignores unknown keys silently: prove the averaging really restarted
        lg = (case / "log.buoyantPimpleFoam").read_text(errors="replace")
        if "Restarting averaging" not in lg and "Starting averaging" not in lg:
            raise RuntimeError(f"{case.name}: no 'Restarting averaging' in the solver log; the reset did not take")
    if abs(times(case)[-1] - new_end) > 1e-3:
        raise RuntimeError(f"{case.name}: last written time {times(case)[-1]} != new end {new_end}")
    tr.setdefault("extended", []).append({"from_s": t_last, "to_s": new_end, "reset_average": reset_average})
    if reset_average:
        tr["avg_from_s"] = t_last
    tr["end_s"] = new_end
    (case / "case_meta.json").write_text(json.dumps(meta, indent=1, default=str))
    (case / "STATUS").write_text("DONE\n")
    return case
