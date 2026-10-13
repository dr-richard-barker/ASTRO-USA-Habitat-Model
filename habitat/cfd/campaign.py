"""Scenario campaign: run a queue of coarse time-averaged transient cases one after another, unattended.

    nohup uv run python -m habitat.cfd.campaign > results/cfd/campaign.driver.log 2>&1 &

Each scenario: build the coarse case from the registry, a 1500-iteration steady start (only a starting field), the
3-flush transient run (habitat.cfd.transient), then its gates (habitat.cfd.post, or the S6 siting report). The queue
waits for the GCI study to finish first, never runs two OpenFOAM jobs at once (foam.run holds the host lock), and a
failed scenario is recorded and skipped, not retried.

Progress: results/cfd/campaign.STATUS (one line per scenario) and results/cfd/campaign.json.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import traceback
from pathlib import Path

from .. import ROOT, RUNS
from . import post
from .case import build as build_case

# (scenario, case tag). All with standard k-epsilon (ledger cfd.turbulence_model, chosen 2026-10-13 from the Annex 20
# validation): the baseline first, so last night's kOmegaSST findings can be compared, then the scenarios. S6 also
# picks up the re-synced payloads (the sensor module's side sample ports).
QUEUE = [("m0", "_ke"), ("s6", "_ke"), ("s2", "_ke"), ("s5a", "_ke"), ("s5b", "_ke")]
OUT = ROOT / "results" / "cfd"
GCI_STATUS = OUT / "gci_m0.STATUS"


def alive(status_file: Path) -> bool:
    s = status_file.read_text().strip() if status_file.exists() else ""
    if not s.startswith("RUNNING"):
        return False
    try:
        os.kill(int(s.split()[1]), 0)
        return True
    except (OSError, ValueError, IndexError):
        return False


def status(case: Path) -> str:
    return (case / "STATUS").read_text().strip() if (case / "STATUS").exists() else ""


def run_one(scenario: str, tag: str) -> dict:
    from .transient import free_cpus, make as make_tr, solve as solve_tr
    n = free_cpus()
    steady = build_case("coarse", n, tag=tag, scenario=scenario, end_iter=1500)
    r = subprocess.run([sys.executable, "-m", "habitat.cfd.run", str(steady), "--np", str(n), "--mesh"])
    if r.returncode != 0 or not status(steady).startswith("DONE"):
        raise RuntimeError(f"steady start failed: {status(steady)}")
    n = free_cpus()
    tr = make_tr(steady, nprocs=n)
    (tr / "STATUS").write_text(f"RUNNING {os.getpid()}\n")
    try:
        solve_tr(tr, n)
    except BaseException as e:  # noqa: BLE001
        (tr / "STATUS").write_text(f"FAILED: {type(e).__name__}: {str(e).splitlines()[0] if str(e) else ''}\n")
        raise
    (tr / "STATUS").write_text("DONE\n")
    if scenario == "s6":
        from .s6_report import maps, run as s6_run
        res = s6_run(tr)
        maps(tr)
    else:
        res = post.run(tr)
    return {"case": tr.name, "pass": bool(res["pass"]), "gates": res["gates"]}


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    st = OUT / "campaign.STATUS"
    log: dict = {"queue": [f"{s}{t}" for s, t in QUEUE], "results": {}}
    from ..provenance import Ledger
    if Ledger().val("cfd.turbulence_model") != "kEpsilon":
        raise SystemExit("campaign queue is tagged _ke but the ledger turbulence model is not kEpsilon")
    st.write_text(f"WAITING for GCI ({os.getpid()})\n")
    while alive(GCI_STATUS):
        time.sleep(120)
    for scenario, tag in QUEUE:
        key = f"{scenario}{tag}"
        lines = [f"{k}: {'PASS' if v.get('pass') else 'FAIL' if 'pass' in v else v.get('error', '?')}"
                 for k, v in log["results"].items()]
        st.write_text(f"RUNNING {os.getpid()} {key}\n" + "\n".join(lines) + "\n")
        t0 = time.time()
        try:
            res = run_one(scenario, tag)
        except BaseException as e:  # noqa: BLE001
            res = {"error": f"{type(e).__name__}: {str(e).splitlines()[0] if str(e) else ''}",
                   "traceback": traceback.format_exc()[-2000:]}
        res["wall_h"] = round((time.time() - t0) / 3600, 2)
        log["results"][key] = res
        (OUT / "campaign.json").write_text(json.dumps(log, indent=1, default=str) + "\n")
    lines = [f"{k}: {'PASS' if v.get('pass') else 'FAIL' if 'pass' in v else v.get('error', '?')} ({v['wall_h']} h)"
             for k, v in log["results"].items()]
    # sensor placement over every time-averaged run that passed its gates (baseline + campaign)
    try:
        from . import sensors
        passed = [RUNS / v["case"] for v in log["results"].values() if v.get("pass")]   # one turbulence model only
        sensors.write(sensors.score(passed))
        lines.append(f"sensor placement: {len(passed)} cases")
    except BaseException as e:  # noqa: BLE001
        lines.append(f"sensor placement failed: {type(e).__name__}: {e}")
    st.write_text("DONE\n" + "\n".join(lines) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
