"""Turbulence-model sensitivity of the baseline: kOmegaSST vs standard k-epsilon on the same mesh and loads.

    uv run python -m habitat.cfd.model_compare runs/fpm_m0_coarse_tr runs/fpm_m0_coarse_ke_tr

Both runs must have passed their gates. The GCI study's 19 quantities are extracted from each (time means), and the
model difference is set against that quantity's mesh sensitivity (fine-vs-coarse spread from results/cfd/gci_m0.json):
a ratio above 1 means the turbulence model matters more than the mesh for that quantity.

Outputs: results/cfd/model_compare.json / .md.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from .. import ROOT
from .gci_study import quantities

OUT = ROOT / "results" / "cfd"


def run(a: Path, b: Path) -> dict:
    for c in (a, b):
        g = json.loads((OUT / f"{c.name}_gates.json").read_text())
        if not g.get("pass"):
            raise ValueError(f"{c.name} did not pass its gates")
    meta = {c.name: json.loads((c / "case_meta.json").read_text()) for c in (a, b)}
    model = {n: m.get("turbulence_model", "kOmegaSST") for n, m in meta.items()}
    if len(set(model.values())) != 2:
        raise ValueError(f"expected two different turbulence models, got {model}")
    qa, qb = quantities(a)["quantities"], quantities(b)["quantities"]
    gci = json.loads((OUT / "gci_m0.json").read_text())["gci"]
    rows = {}
    for k in qa:
        d = qb[k] - qa[k]
        mesh = abs(gci[k]["phi_fine"] - gci[k]["phi_coarse"]) if k in gci else float("nan")
        rows[k] = {model[a.name]: qa[k], model[b.name]: qb[k], "diff": d,
                   "diff_pct": 100 * d / qa[k] if qa[k] else float("nan"),
                   "mesh_spread": mesh, "model_over_mesh": abs(d) / mesh if mesh else float("nan")}
    pct = {k: abs(r["diff_pct"]) for k, r in rows.items()}
    scal = {k: v for k, v in pct.items() if "U_" not in k}
    summary = {"domain_max_pct": max(v for k, v in scal.items() if k.startswith(("domain:", "occupied:"))),
               "local_max_pct": max(v for k, v in scal.items() if not k.startswith(("domain:", "occupied:"))),
               "local_max_quantity": max((k for k in scal if not k.startswith(("domain:", "occupied:"))), key=scal.get),
               "speed_max_pct": max(v for k, v in pct.items() if "U_" in k)}
    return {"cases": {a.name: model[a.name], b.name: model[b.name]}, "rows": rows, "summary": summary,
            "n_model_dominates": sum(1 for r in rows.values() if r["model_over_mesh"] > 1),
            "note": "model/mesh ratios are unstable where the mesh spread is near zero; read the % columns"}


def write(res: dict) -> None:
    (OUT / "model_compare.json").write_text(json.dumps(res, indent=1, default=float) + "\n")
    (na, ma), (nb, mb) = list(res["cases"].items())
    lines = [f"# Baseline turbulence-model sensitivity: {ma} ({na}) vs {mb} ({nb})\n\n",
             "Same mesh, loads and averaging; time means. 'model / mesh' = |model difference| divided by the "
             "fine-vs-coarse spread of the GCI study (above 1: the model matters more than the mesh). "
             f"{res['n_model_dominates']} of {len(res['rows'])} quantities have model / mesh above 1, but that ratio "
             "is unstable where the mesh spread is near zero. In plain terms: room-wide means change by at most "
             f"{res['summary']['domain_max_pct']:.1f} %, local values by up to {res['summary']['local_max_pct']:.0f} % "
             f"({res['summary']['local_max_quantity']}), air speeds by up to {res['summary']['speed_max_pct']:.0f} %.\n\n",
             f"| quantity | {ma} | {mb} | difference | % | model / mesh |\n|---|---|---|---|---|---|\n"]
    for k, r in res["rows"].items():
        lines.append(f"| {k} | {r[ma]:.4g} | {r[mb]:.4g} | {r['diff']:+.3g} | {r['diff_pct']:+.1f} | "
                     f"{r['model_over_mesh']:.2f} |\n")
    (OUT / "model_compare.md").write_text("".join(lines))


if __name__ == "__main__":
    r = run(Path(sys.argv[1]), Path(sys.argv[2]))
    write(r)
    print((OUT / "model_compare.md").read_text())
