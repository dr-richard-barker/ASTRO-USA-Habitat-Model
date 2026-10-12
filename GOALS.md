# Goals and traceability

Request (2026-10-12): "turn these plans into a detailed project with a detailed CAD model of the habitat for CFD modeling … and a hyper detailed model for a virtual reality collaboration."

| ID | Goal | Milestone | Gate (evidence) | Output | Status |
|---|---|---|---|---|---|
| G1 | Sourced dimension ledger | M0/M1 | `pytest tests/test_ledger.py` (unsourced values refused) | `ledger/*.yaml`, `ASSUMPTIONS.md` | M0 done |
| G2 | Floor plan from ICES-2026-251 Fig 2 | M0 | 22/22 printed dims vs own dimension lines (<0.1 in) | `sources/fig2_geometry.json` | done |
| G3 | Engineering CAD | M0 (block) → M1 | reload + bbox checks; Fig 2 overlay ≤0.5 in; mirrored-plan negative test | `out/cad/*.step/.stl/.glb` | M0 done |
| G4 | CFD model of the FPM | M0 (smoke) → M2/M3 | mass/energy/species balance ≤1 %, age identity ≤1 %, steady window; GCI (M3) | `runs/`, `results/cfd/` | M0 running |
| G5 | Hyper-detailed VR scene + engine packs | M4 | glTF validator, budgets, leak scan | `vr/` | not started |
| G6 | WebXR shared room | M5 | desktop walk-through, two-tab presence test | `vr/web`, `relay/` | M0 bare viewer |
| G7 | Mini-Hab site, payloads, primary concept | M6 | concept tags; envelope hashes | `ledger/`, `out/` | not started |
| G8 | Team inputs loop | continuous | change control (TEAM_INPUTS.md) | `TEAM_INPUTS.md` | v0 ready |
