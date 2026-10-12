"""Transient (time-averaged) variant of a steady case, for flows with no steady solution.

    HABITAT_FOAM_COEXIST=1 uv run python -m habitat.cfd.transient runs/fpm_m0_coarse [--flush 3] [--avg-from 1]

Why: the steady runs of the FPM (run 2, S6) wander around their balance targets in ~1000-iteration swings and never
close the global balances to 1 %: a cold supply jet plunging into a heated room is physically unsteady. Following the
review-amended plan (item 7), the case is re-run with buoyantPimpleFoam from the steady run's final fields, for
`flush` room flush times (V/Q), and the gates are applied to quantities averaged from `avg_from` flush times on.

The new case (<name>_tr) re-uses the steady case's mesh, zones, boundary conditions and sources unchanged; only the
time discretisation, the solver, PIMPLE controls and averaging change.
"""
from __future__ import annotations

import argparse
import json
import math
import re
import shutil
from pathlib import Path

from . import foam
from .foam import write


def free_cpus(total: int = 14, keep: int = 1) -> int:
    """CPUs not used by other containers in the VM (docker stats), minus a margin."""
    import subprocess
    r = subprocess.run(["docker", "stats", "--no-stream", "--format", "{{.Name}} {{.CPUPerc}}"],
                       capture_output=True, text=True)
    used = 0.0
    for ln in r.stdout.splitlines():
        name, pct = ln.rsplit(" ", 1)
        if not name.startswith("habitat_"):
            used += float(pct.rstrip("%")) / 100
    return max(2, min(12, total - math.ceil(used) - keep))


def make(steady: Path, flush: float = 3.0, avg_from: float = 1.0, nprocs: int = 4) -> Path:
    meta = json.loads((steady / "case_meta.json").read_text())
    times = sorted((p for p in steady.iterdir() if p.is_dir() and re.fullmatch(r"\d+(\.\d+)?", p.name)),
                   key=lambda p: float(p.name))
    last = times[-1]
    if last.name == "0":
        raise ValueError(f"{steady}: no solved time directory (run the steady case first)")
    case = steady.parent / f"{steady.name}_tr"
    if case.exists():
        shutil.rmtree(case)
    case.mkdir()
    shutil.copytree(steady / "constant", case / "constant")
    shutil.copytree(steady / "system", case / "system")
    shutil.copytree(last, case / "0")                       # steady final fields become the initial condition
    shutil.rmtree(case / "0" / "uniform", ignore_errors=True)
    for f in ("phi", "phi_0", "rhoPhi"):          # rebuild fluxes from U and rho: the SIMPLE-written phi made the
        (case / "0" / f).unlink(missing_ok=True)  # first PIMPLE step blow up (Co ~2000, negative T) in the first try
    for f in ("case_meta.json", "log.checkMesh"):
        shutil.copy(steady / f, case / f)
    V = float(re.search(r"Total volume = ([0-9.eE+-]+)", (steady / "log.checkMesh").read_text()).group(1).rstrip("."))
    Q = meta["physics"]["Q_m3_s"]
    t_flush = V / Q
    end, t_avg = flush * t_flush, avg_from * t_flush

    cd = (case / "system" / "controlDict").read_text()
    cd = cd.replace("application buoyantSimpleFoam;", "application buoyantPimpleFoam;")
    cd = re.sub(r"endTime \d+(\.\d+)?;", f"endTime {end:.1f};", cd)
    cd = re.sub(r"deltaT [^;]+;", "deltaT 0.001;", cd)
    cd = re.sub(r"writeControl timeStep;\n", "writeControl adjustableRunTime;\n", cd, count=1)
    cd = re.sub(r"writeInterval 500;", f"writeInterval {t_flush / 2:.1f};", cd)
    cd = cd.replace("runTimeModifiable true;", "runTimeModifiable true;\nadjustTimeStep yes;\nmaxCo 3;\nmaxDeltaT 0.5;")
    fields = "(U T dCO2 dH2O AoA" + "".join(f" tr_{r}" for r in meta.get("tracers", {})) + ")"
    favg = (f"    fieldAverage\n    {{\n        type fieldAverage; libs (\"libfieldFunctionObjects.so\");\n"
            f"        writeControl writeTime; timeStart {t_avg:.1f};\n        fields\n        (\n" +
            "".join(f"            {f} {{ mean on; prime2Mean off; base time; }}\n" for f in fields.strip("()").split()) +
            "        );\n    }\n")
    cd = cd.replace("functions\n{\n", "functions\n{\n" + favg, 1)
    (case / "system" / "controlDict").write_text(cd)

    # Every boundary has a fixed mass flow, so buoyantPimpleFoam fixes the pressure level from the gas
    # compressibility (closed-volume correction). incompressiblePerfectGas has psi = 0, which makes that
    # correction blow up (first try: p_rgh 101 kPa -> 31 MPa in one step). The full ideal-gas law is used for the
    # transient run; at room pressure its density differs from incompressiblePerfectGas by << 0.1 %.
    th = (case / "constant" / "thermophysicalProperties").read_text()
    th = th.replace("equationOfState incompressiblePerfectGas;", "equationOfState perfectGas;")
    th = re.sub(r"equationOfState\n\s*\{\n\s*pRef [^;]+;\n\s*\}\n", "", th)
    (case / "constant" / "thermophysicalProperties").write_text(th)
    if "incompressiblePerfectGas" in th or "pRef" in th:
        raise ValueError("thermophysicalProperties rewrite for perfectGas failed")
    fs = (case / "system" / "fvSchemes").read_text().replace("default steadyState;", "default Euler;")
    (case / "system" / "fvSchemes").write_text(fs)
    sol = (case / "system" / "fvSolution").read_text()
    sol = sol.replace("SIMPLE\n{", "PIMPLE\n{\n    nOuterCorrectors 3;\n    nCorrectors 2;")
    sol = re.sub(r"momentumPredictor no;", "momentumPredictor yes;", sol)
    # every solver also needs a "Final" variant for the last outer corrector
    sol = re.sub(r'("\(U\|h\|k\|omega\)")', r'"(U|h|k|omega)(Final)?"', sol)
    sol = re.sub(r'("\(dCO2\|dH2O\|AoA\|tr_\.\*\)")', r'"(dCO2|dH2O|AoA|tr_.*)(Final)?"', sol)
    sol = sol.replace("    p_rgh\n    {", "    \"p_rgh(Final)?\"\n    {")
    # buoyantPimpleFoam solves the continuity equation for rho (and rhoFinal): a diagonal solve, no iteration
    # (the 'missing rhoFinal' defect recorded in microgreen-chamber-cfd doc/FIRST_RUN.md)
    sol = sol.replace("solvers\n{\n", "solvers\n{\n    \"rho.*\"\n    {\n        solver diagonal;\n    }\n", 1)
    (case / "system" / "fvSolution").write_text(sol)
    write(case / "system" / "decomposeParDict", "dictionary", "decomposeParDict",
          {"numberOfSubdomains": nprocs, "method": "scotch"})
    meta.update({"case": case.name, "transient": {"from": steady.name, "from_time": last.name, "t_flush_s": t_flush,
                                                    "end_s": end, "avg_from_s": t_avg, "solver": "buoyantPimpleFoam"}})
    (case / "case_meta.json").write_text(json.dumps(meta, indent=1, default=str))
    return case


def solve(case: Path, nprocs: int):
    foam.run(case, ["decomposePar -force", "par:buoyantPimpleFoam", "reconstructPar -latestTime"], nprocs=nprocs)


def main(argv=None):
    import os
    import traceback
    ap = argparse.ArgumentParser()
    ap.add_argument("steady")
    ap.add_argument("--flush", type=float, default=3.0)
    ap.add_argument("--avg-from", type=float, default=1.0)
    ap.add_argument("--np", type=int, default=0, help="0 = choose from free CPUs")
    a = ap.parse_args(argv)
    n = a.np or free_cpus()
    case = make(Path(a.steady), a.flush, a.avg_from, n)
    st = case / "STATUS"
    st.write_text(f"RUNNING {os.getpid()}\n")
    try:
        print(f"[transient] {case.name}: {n} ranks", flush=True)
        solve(case, n)
        st.write_text("DONE\n")
    except BaseException as e:  # noqa: BLE001
        (case / "STATUS.log").write_text(traceback.format_exc())
        st.write_text(f"FAILED: {type(e).__name__}: {str(e).splitlines()[0] if str(e) else ''}\n")
        raise


if __name__ == "__main__":
    main()
