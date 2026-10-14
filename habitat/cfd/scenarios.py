"""Scenario results against the k-epsilon baseline: what changes with six crew (S2) or half / double airflow (S5)?

    uv run python -m habitat.cfd.scenarios

Every scenario that passed its gates is compared with fpm_m0_coarse_ke_tr on the GCI study's quantities (time means;
temperatures and concentrations are rises above the supply air). Same mesh, turbulence model and averaging, so the
differences come from the scenario alone; the GCI study's local-value uncertainty still applies to single points.
Outputs: results/cfd/scenarios.json / .md.
"""
from __future__ import annotations

import json

from .. import ROOT, RUNS
from .gci_study import quantities

OUT = ROOT / "results" / "cfd"
BASE = "fpm_m0_coarse_ke_tr"
SCEN = {"s2": "fpm_s2_coarse_ke_tr", "s5a": "fpm_s5a_coarse_ke_tr", "s5b": "fpm_s5b_coarse_ke_tr"}


def passed(name: str) -> bool:
    g = OUT / f"{name}_gates.json"
    return g.exists() and json.loads(g.read_text()).get("pass", False)


def run() -> dict:
    if not passed(BASE):
        raise ValueError(f"{BASE} has not passed its gates")
    base = quantities(RUNS / BASE)["quantities"]
    res = {"baseline": BASE, "scenarios": {}}
    for key, name in SCEN.items():
        if not passed(name):
            continue
        meta = json.loads((RUNS / name / "case_meta.json").read_text())
        q = quantities(RUNS / name)["quantities"]
        res["scenarios"][key] = {
            "case": name, "Q_m3_s": meta["physics"]["Q_m3_s"], "heat_W": meta["sources_total"]["heat_W"],
            "rows": {k: {"base": base[k], "scenario": q[k], "ratio": q[k] / base[k] if base[k] else None} for k in q}}
    meta0 = json.loads((RUNS / BASE / "case_meta.json").read_text())
    res["baseline_Q_m3_s"], res["baseline_heat_W"] = meta0["physics"]["Q_m3_s"], meta0["sources_total"]["heat_W"]
    return res


def write(res: dict) -> None:
    (OUT / "scenarios.json").write_text(json.dumps(res, indent=1) + "\n")
    lines = ["# Scenarios vs the k-epsilon baseline\n\n",
             f"Baseline {res['baseline']}: {res['baseline_heat_W']:.0f} W, {res['baseline_Q_m3_s']:.4f} m³/s. Values are "
             "time means above the supply air; ratio = scenario / baseline.\n\n"]
    for key, s in res["scenarios"].items():
        lines += [f"## {key} ({s['case']}: {s['heat_W']:.0f} W, {s['Q_m3_s']:.4f} m³/s)\n\n",
                  "| quantity | baseline | scenario | ratio |\n|---|---|---|---|\n"]
        lines += [f"| {k} | {r['base']:.4g} | {r['scenario']:.4g} | {r['ratio']:.2f} |\n" for k, r in s["rows"].items()]
        lines.append("\n")
    (OUT / "scenarios.md").write_text("".join(lines))


if __name__ == "__main__":
    r = run()
    write(r)
    print((OUT / "scenarios.md").read_text())
