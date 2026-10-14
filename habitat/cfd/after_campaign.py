"""Follow-up queue after the k-epsilon campaign (2026-10-14): repairs and the S6 averaging extension.

    nohup uv run python -m habitat.cfd.after_campaign > results/cfd/after_campaign.driver.log 2>&1 &

1. GCI xcoarse level: its last write was 1108 s, not its 1329.5 s end -> continue to the end, re-gate, recompute
   the GCI (habitat.cfd.gci_study re-uses the finished cases).
2. S6 k-epsilon: failed only its CO2/H2O (+1.11 %) and bay-tracer balances with stationary flow -> extend from
   3 to 5 flush times (averaging window 1 -> 5 flush times), then re-run its siting report.
3. Any campaign case whose last write fell short of its end (the same defect) -> continue to the end, re-gate.
4. Sensor ranking over every passing k-epsilon case.
Waits for the campaign to finish; never runs alongside it (foam.run holds the host lock as well).
Progress: results/cfd/after_campaign.STATUS / .json.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import traceback

from .. import ROOT, RUNS
from . import post
from .campaign import alive
from .extend import extend, times

OUT = ROOT / "results" / "cfd"
ST = OUT / "after_campaign.STATUS"


def short_of_end(case) -> float | None:
    meta = json.loads((case / "case_meta.json").read_text())
    end = meta["transient"]["end_s"]
    return end if times(case)[-1] < end - 0.5 else None


def main() -> int:
    log = {}
    ST.write_text(f"WAITING for campaign ({os.getpid()})\n")
    while alive(OUT / "campaign.STATUS"):
        time.sleep(120)

    def step(name, fn):
        ST.write_text(f"RUNNING {os.getpid()} {name}\n")
        t0 = time.time()
        try:
            log[name] = {"result": fn(), "wall_h": round((time.time() - t0) / 3600, 2)}
        except BaseException as e:  # noqa: BLE001
            log[name] = {"error": f"{type(e).__name__}: {e}", "traceback": traceback.format_exc()[-1500:]}
        (OUT / "after_campaign.json").write_text(json.dumps(log, indent=1, default=str) + "\n")

    def gci():
        c = RUNS / "fpm_m0_xcoarse_tr"
        end = short_of_end(c)
        if end:
            extend(c, end)
        g = post.run(c)
        r = subprocess.run([sys.executable, "-m", "habitat.cfd.gci_study"], capture_output=True, text=True)
        return {"xcoarse_pass": g["pass"], "gci_rc": r.returncode, "tail": r.stdout[-400:]}

    def s6():
        c = RUNS / "fpm_s6_coarse_ke_tr"
        meta = json.loads((c / "case_meta.json").read_text())
        extend(c, 5 * meta["transient"]["t_flush_s"])
        from .s6_report import maps, run as s6_run
        res = s6_run(c)
        maps(c)
        return {"pass": res["pass"], "gates": res["gates"]}

    def repair():
        fixed = {}
        for c in sorted(RUNS.glob("fpm_*_ke_tr")):
            if c.name == "fpm_s6_coarse_ke_tr":
                continue
            end = short_of_end(c)
            if end:
                extend(c, end)
                fixed[c.name] = post.run(c)["pass"]
        return fixed

    def sensors_all():
        from . import sensors
        cases = []
        for c in sorted(RUNS.glob("fpm_*_ke_tr")):
            g = OUT / f"{c.name}_gates.json"
            sit = OUT / f"{c.name}_siting.json"
            ok = json.loads(g.read_text()).get("pass") if g.exists() else False
            if sit.exists():
                ok = ok and json.loads(sit.read_text()).get("pass")
            if ok:
                cases.append(c)
        sensors.write(sensors.score(cases))
        return [c.name for c in cases]

    step("gci_xcoarse", gci)
    step("s6_ke_extend", s6)
    step("repair_short_runs", repair)
    step("sensors", sensors_all)
    ST.write_text("DONE\n" + "\n".join(f"{k}: {v.get('error') or v.get('result')}" for k, v in log.items()) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
