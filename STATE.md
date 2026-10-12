# STATE — resumable progress log (L026)

Plan: `~/.claude/plans/we-ve-been-developing-a-quiet-hare.md` (approved 2026-10-12, with review amendments).

## M0 — thin vertical slice
- [x] Scaffold, uv env (py3.11, build123d 0.11.1), `.gitignore` keeps team PDF/slides private
- [x] Fig 2 vector extraction → `sources/fig2_geometry.json` (22/22 printed dims match their own dimension lines, max 0.092 in)
- [x] Ledger (`ledger/*.yaml`): paper values w/ quotes, SeaCube 40' HC spec, BVAD Rev2 Table 3-26 crew loads, declared assumptions
- [x] Registry → block CAD → STEP/STL/GLB with reload checks (`out/cad/CAD_QA.json`)
- [x] Fig 2 overlay gate (max deviation 0.000 in) + mirrored-plan negative test
- [ ] Coarse CFD smoke run (Docker, buoyantSimpleFoam + kOmegaSST), balance + age-of-air identity
- [ ] Block GLB in a bare three.js page (preview pane)

## How to resume
    uv sync && uv run python -m habitat.cad.build && uv run python -m habitat.checks.fig2_overlay && uv run pytest -q
