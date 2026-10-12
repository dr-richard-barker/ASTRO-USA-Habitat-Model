# ASTRO-USA Habitat Model

A parametric model of the ASTRO-USA **Mini-Hab Food Production Module (FPM)** — the shipping container described in
Peters et al., *Analog Simulation Training and Research Outpost Utilizing Self-sustaining Architecture: A Testbed for
Moon and Mars Technology at Purdue University*, 55th International Conference on Environmental Systems, ICES-2026-251.

One sourced **ledger** of dimensions and loads drives three outputs:

1. **Engineering CAD** (build123d → STEP / STL / GLB),
2. **CFD** (OpenFOAM v2606 in a pinned Docker image; air, heat, CO₂, water vapour, age of air),
3. **VR** (a browser WebXR viewer now; hyper-detailed LOD scenes and engine-ready packs to come).

## Status (M0 vertical slice, 2026-10-12)

- Floor plan extracted from the paper's vector Figure 2: all 22 printed dimensions agree with their own dimension
  lines within 0.1 in (`sources/fig2_geometry.json`).
- Block-level CAD of the FPM built and checked against Figure 2 (overlay deviation 0.000 in).
- First coarse CFD case (256 k cells) — see `results/cfd/` once the run's balance gates pass.
- Minimal three.js viewer in `vr/web/`.

Everything not stated in a source is an explicit, listed assumption: see [ASSUMPTIONS.md](ASSUMPTIONS.md). The facts
we need from the ASTRO-USA team are in [TEAM_INPUTS.md](TEAM_INPUTS.md). Progress and how to resume: [STATE.md](STATE.md).

## Reproduce

```bash
uv sync
make cad check docs test        # CAD, Figure 2 overlay gate, generated docs, tests
make cfd-coarse post            # needs Docker (pulls the pinned OpenFOAM v2606 image)
```

`make fig2` re-extracts the floor plan and needs the paper PDF in `sources/private/` (not distributed here; the
paper and slides belong to the ICES-2026-251 authors).

## Sources

- ICES-2026-251 (team paper): footprint, zone layout, equipment counts, electrical loads.
- SeaCube Containers, 40′ High Cube Dry specification sheet: container shell dimensions.
- NASA/TP-2015-218570/REV2 (BVAD), Table 3-26: crew metabolic heat, CO₂ and water vapour.
- CoolProp: air properties.

## Licence

Code: MIT ([LICENSE](LICENSE)). Model data and documents: licence to be agreed with the ICES-2026-251 team before
publication.
