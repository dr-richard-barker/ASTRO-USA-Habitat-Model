# STATE — resumable progress log (L026)

Plan: `~/.claude/plans/we-ve-been-developing-a-quiet-hare.md` (approved 2026-10-12, with review amendments).

## M0 — thin vertical slice
- [x] Scaffold, uv env (py3.11, build123d 0.11.1), `.gitignore` keeps team PDF/slides private
- [x] Fig 2 vector extraction → `sources/fig2_geometry.json` (22/22 printed dims match their own dimension lines, max 0.092 in)
- [x] Ledger (`ledger/*.yaml`): paper values w/ quotes, SeaCube 40' HC spec, BVAD Rev2 Table 3-26 crew loads, declared assumptions
- [x] Registry → block CAD → STEP/STL/GLB with reload checks (`out/cad/CAD_QA.json`)
- [x] Fig 2 overlay gate (max deviation 0.000 in) + mirrored-plan negative test
- [~] Coarse CFD smoke run (255 k cells, buoyantSimpleFoam + kOmegaSST, 4 ranks, ~1.25 s/iteration)
  - run1 (3000 it.): mass exact; CO2 -0.17 %, H2O -0.12 %, age identity +0.47 % (all PASS);
    heat +58 % and not steady (FAIL) - room-mean T a slow mode, still 1.8 K above balance
    (`results/cfd/fpm_m0_coarse_run1_*`)
  - run2: initial T = energy-balanced return T, h relaxation 0.5, 4000 it. (running)
- [x] Block GLB + CFD slice overlay in a three.js 0.180 viewer (preview `habitat-viewer`, port 8422)

## How to resume
    uv sync && uv run python -m habitat.cad.build && uv run python -m habitat.checks.fig2_overlay && uv run pytest -q

## Fixes found while running M0 (each now has a gate or test)
- heated blockages lost their heat (no cells inside a blockage) -> one-cell shell zones; case asserts totals = registry
- obstacle feature edges pushed outside the walls dragged wall points 25 mm out -> `insideBox` clip; mesh-bounds gate
- steady scalar solves to 1e-10 every iteration were ~15x too slow -> relTol 0.05
- room-mean temperature converges very slowly in steady SIMPLE -> balanced initial T (run2)
