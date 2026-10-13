"""Validation: the IEA Annex 20 two-dimensional isothermal test case (case 2D1), against its laser-Doppler data.

    uv run python -m habitat.cfd.annex20 [--mesh 80 40 20]

Why this case: like the FPM, a ceiling wall jet from a slot drives the whole room, and it is solved here with the
habitat cases' own turbulence model (kOmegaSST), wall functions and convection schemes. Running it at the habitat's
80 mm cell size and at 40 / 20 mm separates the turbulence model's error from mesh error.

Specification (read from the scanned report, Nielsen 1990, pp. 1-2; see ledger/validation.yaml):
  L/H = 3.0, h/H = 0.056, t/H = 0.16 (H = 3.0, L = 9.0, h = 0.168, t = 0.48 m); inlet slot at the top of the x = 0
  wall, outlet at the bottom of the x = L wall; Re = h u0 / nu = 5000, u0 = 0.455 m/s, nu = 15.3e-6 m2/s;
  k0 = 1.5 (0.04 u0)^2, eps0 = k0^1.5 / l0, l0 = h / 10  (omega0 = eps0 / (0.09 k0)).
Data: Aalborg University CFD benchmark spreadsheet "Laser-doppler measurements of the isothermal two dimensional
test case": mean u/u0 on vertical lines x = H and x = 2H and on horizontal lines h/2 below the ceiling and h/2 above
the floor. The report's co-ordinates have y pointing DOWN from the ceiling (Figure 1); the model uses z up from the
floor, so y = H - z.

Outputs: results/cfd/annex20.json / .md / .png. Cases in runs/annex20_<mm>mm (git-ignored).
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from .. import ROOT, RUNS  # noqa: E402
from ..provenance import Ledger  # noqa: E402
from . import foam  # noqa: E402
from .foam import write  # noqa: E402

OUT = ROOT / "results" / "cfd"
DATA = ROOT / "sources" / "annex20_lda.json"


def spec(L: Ledger) -> dict:
    H = L.num("validation.annex20.H", "m")
    s = {"H": H, "L": H * L.num("validation.annex20.L_over_H", "-"), "h": H * L.num("validation.annex20.h_over_H", "-"),
         "t": H * L.num("validation.annex20.t_over_H", "-"), "u0": L.num("validation.annex20.u0", "m/s"),
         "nu": L.num("validation.annex20.nu", "m2/s")}
    k0 = 1.5 * (0.04 * s["u0"]) ** 2
    l0 = s["h"] / 10
    eps0 = k0 ** 1.5 / l0
    s.update({"k0": k0, "omega0": eps0 / (0.09 * k0), "Re": s["h"] * s["u0"] / s["nu"]})
    return s


MODELS = {"kOmegaSST": "", "kEpsilon": "_kEpsilon"}


def build(dx_mm: int, s: dict, model: str = "kOmegaSST") -> Path:
    case = RUNS / f"annex20_{dx_mm}mm{MODELS[model]}"
    import shutil
    shutil.rmtree(case, ignore_errors=True)
    dx = dx_mm / 1000
    H, Lx, h, t = s["H"], s["L"], s["h"], s["t"]
    ys = [0.0, t, H - h, H]                                  # z bands: outlet | wall | inlet  (z up from the floor)
    ny = [max(1, round((b - a) / dx)) for a, b in zip(ys, ys[1:])]
    nx = max(1, round(Lx / dx))
    dz = dx
    v = []
    for z in (0.0, dz):
        for y in ys:
            v += [(0.0, y, z), (Lx, y, z)]
    # vertex index: layer*8 + band_edge*2 + (0 = x0, 1 = xL)
    def vi(layer, e, side):
        return layer * 8 + e * 2 + side
    blocks, faces = [], {"inlet": [], "outlet": [], "walls": [], "frontAndBack": []}
    for b in range(3):
        a0, a1, b1, b0 = vi(0, b, 0), vi(0, b, 1), vi(0, b + 1, 1), vi(0, b + 1, 0)
        c0, c1, d1, d0 = vi(1, b, 0), vi(1, b, 1), vi(1, b + 1, 1), vi(1, b + 1, 0)
        blocks.append(f"hex ({a0} {a1} {b1} {b0} {c0} {c1} {d1} {d0}) ({nx} {ny[b]} 1) simpleGrading (1 1 1)")
        left, right = f"({a0} {c0} {d0} {b0})", f"({a1} {b1} {d1} {c1})"
        faces["inlet" if b == 2 else "walls"].append(left)
        faces["outlet" if b == 0 else "walls"].append(right)
        faces["frontAndBack"] += [f"({a0} {b0} {b1} {a1})", f"({c0} {c1} {d1} {d0})"]
    faces["walls"] += [f"({vi(0, 0, 0)} {vi(0, 0, 1)} {vi(1, 0, 1)} {vi(1, 0, 0)})",          # floor
                       f"({vi(0, 3, 0)} {vi(1, 3, 0)} {vi(1, 3, 1)} {vi(0, 3, 1)})"]          # ceiling
    types = {"inlet": "patch", "outlet": "patch", "walls": "wall", "frontAndBack": "empty"}
    bnd = "".join(f"    {n} {{ type {types[n]}; faces ( {' '.join(f)} ); }}\n" for n, f in faces.items())
    write(case / "system" / "blockMeshDict", "dictionary", "blockMeshDict",
          "convertToMeters 1;\nvertices (\n" + "\n".join(f"    ({a:.9g} {b:.9g} {c:.9g})" for a, b, c in v)
          + "\n);\nblocks (\n    " + "\n    ".join(blocks) + "\n);\nboundary (\n" + bnd + ");\n")
    U0, k0, w0 = s["u0"], s["k0"], s["omega0"]
    fields = {
        "U": ("volVectorField", "[0 1 -1 0 0 0 0]", "uniform (0 0 0)",
              {"inlet": f"type fixedValue; value uniform ({U0} 0 0);", "outlet": "type zeroGradient;",
               "walls": "type noSlip;"}),
        "p": ("volScalarField", "[0 2 -2 0 0 0 0]", "uniform 0",
              {"inlet": "type zeroGradient;", "outlet": "type fixedValue; value uniform 0;", "walls": "type zeroGradient;"}),
        "k": ("volScalarField", "[0 2 -2 0 0 0 0]", f"uniform {k0:.6g}",
              {"inlet": f"type fixedValue; value uniform {k0:.6g};", "outlet": "type zeroGradient;",
               "walls": f"type kqRWallFunction; value uniform {k0:.6g};"}),
        "omega": ("volScalarField", "[0 0 -1 0 0 0 0]", f"uniform {w0:.6g}",
                  {"inlet": f"type fixedValue; value uniform {w0:.6g};", "outlet": "type zeroGradient;",
                   "walls": f"type omegaWallFunction; value uniform {w0:.6g};"}),
        "epsilon": ("volScalarField", "[0 2 -3 0 0 0 0]", f"uniform {0.09 * k0 * w0:.6g}",
                    {"inlet": f"type fixedValue; value uniform {0.09 * k0 * w0:.6g};", "outlet": "type zeroGradient;",
                     "walls": f"type epsilonWallFunction; value uniform {0.09 * k0 * w0:.6g};"}),
        "nut": ("volScalarField", "[0 2 -1 0 0 0 0]", "uniform 0",
                {"inlet": "type calculated; value uniform 0;", "outlet": "type calculated; value uniform 0;",
                 "walls": "type nutkWallFunction; value uniform 0;"}),
    }
    for name, (cls, dims, internal, bc) in fields.items():
        body = (f"dimensions {dims};\ninternalField {internal};\nboundaryField\n{{\n"
                + "".join(f"    {p} {{ {t} }}\n" for p, t in bc.items()) + "    frontAndBack { type empty; }\n}\n")
        write(case / "0" / name, cls, name, body)
    write(case / "constant" / "transportProperties", "dictionary", "transportProperties",
          f"transportModel Newtonian;\nnu {s['nu']:.6g};\n")
    write(case / "constant" / "turbulenceProperties", "dictionary", "turbulenceProperties",
          f"simulationType RAS;\nRAS {{ RASModel {model}; turbulence on; printCoeffs off; }}\n")
    write(case / "system" / "controlDict", "dictionary", "controlDict",
          "application simpleFoam;\nstartFrom startTime;\nstartTime 0;\nstopAt endTime;\nendTime 6000;\ndeltaT 1;\n"
          "writeControl timeStep;\nwriteInterval 6000;\npurgeWrite 1;\nwriteFormat ascii;\nwritePrecision 8;\n"
          "runTimeModifiable true;\n")
    # same convection schemes as the habitat cases: linearUpwind for U, upwind for k / omega
    write(case / "system" / "fvSchemes", "dictionary", "fvSchemes",
          "ddtSchemes { default steadyState; }\ngradSchemes { default Gauss linear; }\n"
          "divSchemes\n{\n    default none;\n    div(phi,U) bounded Gauss linearUpwind grad(U);\n"
          "    div(phi,k) bounded Gauss upwind;\n    div(phi,omega) bounded Gauss upwind;\n"
          "    div(phi,epsilon) bounded Gauss upwind;\n"
          "    div((nuEff*dev2(T(grad(U))))) Gauss linear;\n}\n"
          "laplacianSchemes { default Gauss linear corrected; }\ninterpolationSchemes { default linear; }\n"
          "snGradSchemes { default corrected; }\nwallDist { method meshWave; }\n")
    write(case / "system" / "fvSolution", "dictionary", "fvSolution",
          "solvers\n{\n    p { solver GAMG; smoother GaussSeidel; tolerance 1e-8; relTol 0.05; }\n"
          "    \"(U|k|omega|epsilon)\" { solver smoothSolver; smoother symGaussSeidel; tolerance 1e-8; relTol 0.1; }\n}\n"
          "SIMPLE\n{\n    nNonOrthogonalCorrectors 0;\n    consistent yes;\n"
          "    residualControl { p 1e-5; U 1e-6; \"(k|omega|epsilon)\" 1e-6; }\n}\n"
          "relaxationFactors { equations { U 0.9; \".*\" 0.7; } }\n")
    (case / "case.foam").touch()
    return case


def sample(case: Path, s: dict) -> dict:
    from .slices import load
    vol, it = load(case)
    pts = vol.cell_data_to_point_data()
    import pyvista as pv
    H, dz = s["H"], float(vol.bounds[5])
    out = {"iteration": it}

    def line(p0, p1, n=300):
        P = np.linspace(p0, p1, n)
        sm = pv.PolyData(P).sample(pts)
        ok = np.asarray(sm.point_data["vtkValidPointMask"]).astype(bool)
        return P[ok], np.asarray(sm.point_data["U"])[ok, 0] / s["u0"]
    for key, x in (("x=H", H), ("x=2H", 2 * H)):
        P, u = line([x, 1e-4, dz / 2], [x, H - 1e-4, dz / 2])
        out[key] = {"y_over_H": ((H - P[:, 1]) / H).tolist(), "u_over_u0": u.tolist()}       # y down from ceiling
    for key, zf in (("ceiling h/2", H - s["h"] / 2), ("floor h/2", s["h"] / 2)):
        P, u = line([1e-4, zf, dz / 2], [s["L"] - 1e-4, zf, dz / 2])
        out[key] = {"x_over_H": (P[:, 0] / H).tolist(), "u_over_u0": u.tolist()}
    return out


def compare(sim: dict, data: dict) -> dict:
    """RMS and max |u/u0 error| at the measured points (simulation interpolated along each line)."""
    res = {}
    for key, d in data["profiles"].items():
        coord = "y_over_H" if key.startswith("x=") else "x_over_H"
        xs, us = np.array(sim[key][coord]), np.array(sim[key]["u_over_u0"])
        order = np.argsort(xs)
        pred = np.interp(d[coord], xs[order], us[order])
        e = pred - np.array(d["mean"])
        res[key] = {"rms": float(np.sqrt(np.mean(e ** 2))), "max": float(np.max(np.abs(e))), "n": len(e)}
    return res


def final_residuals(log: str) -> dict:
    import re
    res = {}
    for f in ("Ux", "Uz", "p", "k", "omega", "epsilon"):
        m = re.findall(rf"Solving for {f}, Initial residual = ([0-9.eE+-]+)", log)
        if m:
            res[f] = float(m[-1])
    return res


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--mesh", type=int, nargs="+", default=[80, 40, 20])
    ap.add_argument("--report-only", action="store_true", help="re-sample finished cases, no solve")
    ap.add_argument("--models", nargs="+", default=["kOmegaSST"], choices=list(MODELS))
    a = ap.parse_args(argv)
    L = Ledger()
    s = spec(L)
    if abs(s["Re"] - 5000) > 50:
        raise ValueError(f"spec Re {s['Re']:.0f} != 5000")
    data = json.loads(DATA.read_text())
    runs = {}
    for dx, model in [(d, m) for m in a.models for d in a.mesh]:
        case = RUNS / f"annex20_{dx}mm{MODELS[model]}"
        if not a.report_only:
            case = build(dx, s, model)
            foam.run(case, ["blockMesh", "checkMesh", "simpleFoam"], nprocs=1, exclusive=False)
        log = (case / "log.simpleFoam").read_text()
        iters = len([ln for ln in log.splitlines() if ln.startswith("Time = ")])
        fr = final_residuals(log)
        # converged: the solver's own residual control was met, or every final initial residual is below 1e-5
        converged = "reached convergence criteria" in log or max(fr.values()) < 1e-5
        sim = sample(case, s)
        runs[f"{model} {dx} mm"] = {"cells": int(next(ln.split()[-1] for ln in (case / "log.checkMesh").read_text().splitlines()
                                              if ln.strip().startswith("cells:"))),
                            "iterations": iters, "converged": bool(converged), "final_residuals": fr,
                            "errors": compare(sim, data), "sim": sim}
        print(f"[annex20] {model} {dx} mm: {iters} iterations, converged {converged}, "
              + ", ".join(f"{k} rms {v['rms']:.3f}" for k, v in runs[f'{model} {dx} mm']['errors'].items()), flush=True)
    res = {"spec": s, "ledger_digest": L.digest(), "data_source": data["source"], "runs": runs}
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "annex20.json").write_text(json.dumps(res, indent=1) + "\n")
    report(res, data)
    return 0


def report(res: dict, data: dict) -> None:
    keys = list(data["profiles"])
    lines = [f"# Validation: IEA Annex 20 2-D test case (ledger {res['ledger_digest']})\n\n",
             f"Re = {res['spec']['Re']:.0f}, u0 = {res['spec']['u0']} m/s; kOmegaSST (as in the habitat runs) and standard k-epsilon, wall functions, the habitat "
             f"cases' schemes. Data: {res['data_source']}. Error = simulated minus measured mean u/u0 at the measured "
             "points. Isothermal case only: the report's buoyant case (2D2) has no measurements for this geometry "
             "(\"experiments for h/H = 0.056 and Re = 5000 are missing\", Nielsen 1990 p. 4).\n\n",
             "| mesh | cells | iterations | largest final residual | " + " | ".join(f"{k} rms (max)" for k in keys) + " |\n",
             "|---|---|---|---|" + "---|" * len(keys) + "\n"]
    for m, r in res["runs"].items():
        lines.append(f"| {m} | {r['cells']:,} | {r['iterations']} | {max(r['final_residuals'].values()):.1e} | "
                     + " | ".join(f"{r['errors'][k]['rms']:.3f} ({r['errors'][k]['max']:.3f})" for k in keys) + " |\n")
    (OUT / "annex20.md").write_text("".join(lines))
    fig, axs = plt.subplots(1, 4, figsize=(15, 4.2), layout="constrained")
    for ax, k in zip(axs, keys):
        d = data["profiles"][k]
        vertical = k.startswith("x=")
        coord = "y_over_H" if vertical else "x_over_H"
        for m, r in res["runs"].items():
            sim = r["sim"][k]
            if vertical:
                ax.plot(sim["u_over_u0"], sim[coord], lw=1, label=m)
            else:
                ax.plot(sim[coord], sim["u_over_u0"], lw=1, label=m)
        if vertical:
            ax.plot(d["mean"], d[coord], "ko", ms=3, label="LDA (Aalborg)")
            ax.invert_yaxis(); ax.set_xlabel("u / u0"); ax.set_ylabel("y / H (down from the ceiling)")
        else:
            ax.plot(d[coord], d["mean"], "ko", ms=3, label="LDA (Aalborg)")
            ax.set_xlabel("x / H"); ax.set_ylabel("u / u0")
        ax.set_title(k, fontsize=9); ax.axvline(0, color="0.7", lw=0.5) if vertical else ax.axhline(0, color="0.7", lw=0.5)
    axs[0].legend(fontsize=7)
    models = sorted({k.split()[0] for k in res["runs"]})
    fig.suptitle(f"IEA Annex 20 2-D isothermal test case (Re 5000): simulated ({' vs '.join(models)}, wall functions) "
                 "vs measured mean velocity (Aalborg LDA)", fontsize=9)
    fig.savefig(OUT / "annex20.png", dpi=110)
    plt.close(fig)


if __name__ == "__main__":
    raise SystemExit(main())
