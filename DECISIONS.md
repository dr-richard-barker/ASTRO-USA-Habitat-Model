# Decisions

| Date | Decision | Why | By |
|---|---|---|---|
| 2026-10-12 | Scope: FPM + biomanufacturing payloads + whole Mini-Hab site + primary-habitat concept; FPM first | User request | R. Barker |
| 2026-10-12 | Container = 40 ft high-cube | User | R. Barker |
| 2026-10-12 | VR = browser WebXR shared room + engine-ready asset packs (no engine project); no headsets yet | User | R. Barker |
| 2026-10-12 | Public repo + Pages; first push needs user OK **and** recorded team consent | User; plan review item 12 | R. Barker |
| 2026-10-12 | Payloads modelled as outer envelopes, gas ports and loads only | User; plan review item 5 | R. Barker |
| 2026-10-16 | Payloads made generic and unbranded (bioreactor rack, photobioreactor, incubator, sensor module); values kept as declared assumptions so the CFD results stay valid | User (repo shared with J. M. Peters) | R. Barker |
| 2026-10-12 | CFD on this Mac (pinned Docker image), queued behind other sessions' runs | User | R. Barker |
| 2026-10-12 | Steady compressible buoyantSimpleFoam + incompressiblePerfectGas + kOmegaSST; scalars relative to supply air; turbulent scalar diffusivity (alphaD/alphaDt) | Plan review items 1-4 | Claude (approved plan) |
| 2026-10-12 | Floor plan taken from the PDF's vector geometry, not traced; frame: model y = 92 in - printed y (right-handed, z up) | Exactness; mirrored-plan test guards the flip | Claude |
| 2026-10-12 | Heated blockages deposit heat in a one-cell fluid shell; case asserts source totals equal the registry | A dropped source still "balances" (found in M0: 122.5 W missing) | Claude |
| 2026-10-16 | Public release: repo made public and the project page published on GitHub Pages | ASTRO-USA team agreed (relayed by R. Barker after speaking to the team); repo recreated first so no pre-rewrite commits remain on GitHub | R. Barker |
