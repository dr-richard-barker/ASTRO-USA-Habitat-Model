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

## VR scene v0 (started at user request while CFD run2 solves, 2026-10-12)
- `make vr`: spec (registry + `ledger/vr_detail.yaml`) -> Blender 5.2 procedural builder -> LOD0 172k / LOD1 48k / LOD2 18k tris,
  GLB + USDZ (usdchecker Success) + FBX + .blend; all gates PASS (`out/vr/VR_QA.json`)
- Fig 8 receptacle/disconnect/panel positions measured from the raster (2.886 px/in, +/-2 in)
- fixes: door hardware was outside the ISO envelope; GPU-instancing holder nodes lacked extras; QA must apply instance
  translations (Blender writes no min/max on them); meshopt dropped (files < 2 MB, keeps QA/viewer decoder-free)
- viewer: `vr/web` loads LOD2 (or `?lod=1`), layers from extras, click shows element + illustrative flag, CFD overlay
- WebXR added (VRButton, dolly rig starting at the door end facing the attic, floor-only teleport, snap turn):
  loads without errors on desktop (button reports 'VR NOT SUPPORTED'); NOT yet tested in a headset (none available)
- next: Durable Object relay (multi-user), payload envelopes in the bioreactor bay, KTX2 when headsets exist

## Payload envelopes in the bioreactor bay (2026-10-12, user request; made generic 2026-10-16)
- `ledger/payloads.yaml`: four generic placeholder payloads: a ten-vessel bioreactor rack, a photobioreactor, an
  incubator and a sensor module; envelopes, ports (`ledger/payload_ports.json`) and loads are all declared assumptions
- registry role `payload` (CAD + VR; inside the enclosure's CFD blockage); `scenario_m0.payloads_powered: false` keeps M0 at
  520 W; powered -> heat deposited in the bay's fluid shell (tests/test_payloads.py)
- VR: translucent tinted envelopes + edge frames + port markers, layer "payloads", extras envelope_only; close-up
  render `out/vr/render_lod0_payload_bay.png`
- layout: photobioreactor rotated 180 deg so its gas inlet faces the rack; off-gas route 'bay' (assumed; S6 compares
  bay / photobioreactor / nft_wall); powered + route bay -> 18.2 g CO2/day into the bay's fluid shell
- still to do: O2 balance, culture uptake rates, fan flows; real hardware once the team chooses it

## Multi-user relay (2026-10-12, user request)
- `relay/`: Cloudflare Worker + SQLite Durable Object rooms; pins stored, poses relayed in memory; origin allow-list
- `vr/web/collab.js`: start/join via #room= fragment, avatars (10 Hz pose), review pins (author-only delete), reconnect
- tests: `npm test` 20/20 against `wrangler dev` (127.0.0.1:8797, preview config `habitat-relay`); two-tab browser test:
  presence both ways, pin round trip with element + author, reload restores pins from storage
- NOT deployed: user chose to keep it local and deploy together with the Pages site (`npm run deploy` in relay/)
- known: background tabs pause rendering, so a hidden tab sends no poses (fine for one-person-per-window use)

## CFD: steady -> transient (2026-10-12)
- run 2 (steady, 4000 it.) failed gates: balances off 2-12 %, ~1000-iteration swings (cold jet into heated room is
  physically unsteady); iteration means still 1-4 % off. S6 steady: same. GCI correctly refused to start.
- `habitat/cfd/transient.py`: buoyantPimpleFoam restart from the steady fields, 3 flush times (V/Q ~ 446 s), averaged
  from 1 flush time; fixes: rho/rhoFinal diagonal solver, phi rebuilt (stale SIMPLE phi blew up), perfectGas
  (psi=0 made the closed-volume pressure correction explode). ~11x slower than real time on 12 ranks (~4 h per run).
- post/s6_report: time-weighted window means + stationarity gate (halves of the window agree)
- GCI (user decision): shifted ladder 57/80/113 mm on transient runs (80/57/40 needs ~110 h here); orchestrator
  `habitat.cfd.gci_study` waits for fpm_m0_coarse_tr to pass, then xcoarse + medium (steady init 1500 it. + transient)

## Mini-Hab site, concept level (2026-10-12)
- `ledger/site.yaml`: Fig 10 topology by pixel analysis (schematic, not to scale); 20 ft standard dry modules
  (SeaCube spec verified), trailer placeholder (ICES-2026-290 not available), illustrative Lab (Fig 1 equipment) and
  Crew Quarters (6 berths) layouts
- `make vr`-style build: `uv run python -m habitat.vr.build --site` -> fpm_site_lod{0,1,2}.glb (gates PASS);
  viewer toggle loads the overlay on demand

## Primary-habitat concept generator (2026-10-12)
- `ledger/primary.yaml` (study variables, all assumed except the paper's intent quotes and the NASA NHV guideline:
  25 m3/person, crew of 6, Whitmire et al. 2014, NTRS 20140016951 - read from the report itself)
- `habitat/primary.py` -> `results/primary_concept.md`: node 5 m + 4 x 4.2 m modules (9/8/9/8 m) + airlock;
  488 m3 internal pressurised (airlock excluded), deck 130 m2; meets 25 m3/person for habitable fraction >= 0.31
  (0.40/0.50/0.60 -> 32.5/40.7/48.8 m3/person); clash check + 3 tests
- VR: `habitat.vr.build --primary` -> primary_concept_lod{0,1,2}.glb (gates PASS); viewer `?scene=primary`

## Drawings + project report site (2026-10-12)
- `make drawings` -> results/drawings/FPM_GA.(svg|pdf|png): plan + both long-wall elevations, one scale, from the registry
- `make report` -> docs/index.html (+ docs/viewer, docs/assets): every number read from ledger/results at build time;
  CFD shown with gate badges (run1/run2 FAIL, transient/S6/GCI pending); self-contained page styling;
  checked desktop + mobile (375 px, no overflow) + dark; preview config `habitat-docs` (port 8423). NOT published.

## Viewer fix (2026-10-12)
- Clicks hit hidden layers/overlays (three.js raycasts invisible objects and the filter checked only the mesh, not its
  ancestors) -> pick now requires every ancestor visible.

## Overnight CFD (2026-10-12/13)
- Baseline `fpm_m0_coarse_tr` (buoyantPimpleFoam, 3 flush times, means over the last 2): **all gates PASS**:
  heat +0.14 %, CO2 -0.57 %, H2O -0.57 %, age identity -0.16 %, stationary (`results/cfd/fpm_m0_coarse_tr_gates.json`).
  Fields + viewer overlay now use the time means (`fpm_m0_coarse_tr_fields.png`, `vr/web/assets/fpm_m0_coarse_tr_age_z1.10.glb`);
  the failed steady run's overlay was removed from the viewer.
- S6 siting `fpm_s6_coarse_tr`: **all gates PASS** (3 route balances + general). The placeholder bioreactor off-gas adds ~0.8 ppm
  when mixed through the room vs 57-156 ppm crew-generated CO2 at the same points (kOmegaSST run; superseded by the k-epsilon S6 run, its outputs removed 2026-10-16);
  ducting to the NFT wall concentrates it at the canopy (x1.3-1.5 the mixed value) but only to ~1 ppm.
  Caveats: coarse mesh, placeholder HVAC (300 cfm), adiabatic walls, the bioreactor rate is a placeholder planning value.
- GCI (113/80/57 mm) running since ~03:30 (`results/cfd/gci_m0.STATUS`); finest level is ~17 h.
- Not pushed: the attestation at 4df856e is stale for these results; run /abai check before the next push.

## Payload envelopes updated (2026-10-13)
- Sensor module envelope 104 x 96 x 96 mm with its sample inlet/outlet on the -X side (was a 90 mm cube sampled at the
  top face); bioreactor rack 869 mm tall (was 810). In the S6 open bay the payloads moved 2.8-11.2 mm, well under the
  80 mm cells; the GCI ladder reads only the crew/canopy boxes, which did not move.

## Scenario campaign queued (2026-10-13)
- `registry.scenario_path`: a `scenario_<name>` ledger overrides M0 values key by key; refs name the record used
  (m0/s6 registry output byte-identical before/after; `tests/test_scenarios.py`).
- New declared-assumption scenarios: **S2** peak occupancy (6 crew along the aisle; 860 W vs 520 W),
  **S5a/S5b** HVAC flow 150 / 600 cfm (half/double the placeholder, same supply T).
- `habitat.cfd.campaign` (detached; started ~11:00, restarted 11:57 to add its final sensor-placement step) waits for the GCI study, then runs coarse transients in turn:
  S6 re-run on the current ledger (`fpm_s6_coarse_r2_tr`; probes the sensor module's side sample inlet), S2, S5a, S5b. Expected
  ~4-5 h each, so ~18 h after the GCI finishes. Progress: `results/cfd/campaign.STATUS`; results in `results/cfd/`.
- Supply temperature stays fixed at 18 C in every scenario (no set-point control), so room temperature is an output.

## Plant gas exchange: blocked on lighting data (2026-10-13)
- The sensor analysis showed the canopy carries LED heat only (no CO2 uptake, no transpiration), so positions near
  plants / water culture / the bioreactor bay / payloads are excluded from the ranking (`ledger/sensors.yaml`).
- Coupling plants needs a crop model. BVAD's Modified Energy Cascade is valid for lettuce only at 200-500 umol/m2/s.
  `habitat.light_budget` (`results/light_budget.md`): if the paper's 450 W max draw includes the grow lights, every watt
  to light at the best achieved fixture efficacy (3 umol/J, Kusuma et al. 2020) gives at most 145 umol/m2/s on the NFT
  wall face (87 at BVAD planting density). 8 kWh over the 16 h photoperiod implies 500 W > 450 W, so 450 W binds.
  -> not coupled; the question is now item 5 of TEAM_INPUTS (fixtures, power, canopy PPF, inside the budget or not).
- The BVAD MEC equations extract from the PDF as broken fragments; transcribing them needs the page images and a
  check against BVAD's own nominal outputs (Table 4-91 lettuce: 10.70 g CO2/m2/d, 2.10 kg H2O/m2/d) when it is done.

## S3 HVAC off, 0-D (2026-10-13)
- `habitat.s3_hvac_off` (`results/s3_hvac_off.md`): well-mixed 63.1 m3, BVAD crew CO2, start at NOAA outdoor 426.1 ppm,
  OSHA PEL 5000 ppm (eCFR Table Z-1, verified from the regulation XML). Sealed: 2 crew 6.3 h, 6 crew 2.1 h; 0.5 ACH keeps
  both below the limit. Infiltration is the unknown -> CO2 decay test added to TEAM_INPUTS (Envelope).
- NIOSH STEL/IDLH values were seen only through a summarising fetch (cdc.gov blocks curl with 403), so they are not used.
- Same build-up applies with the HVAC on if the split unit only recirculates (CFD CO2 is relative to supply air).

## Validation and turbulence-model switch (2026-10-13)
- `habitat.cfd.annex20`: IEA Annex 20 2-D isothermal case (spec read from the scanned Nielsen 1990 R9040 pages;
  Aalborg LDA spreadsheet -> `sources/annex20_lda.json` via `sources/annex20_data.py`) at 80/40/20 mm with the habitat
  wall functions and schemes. kOmegaSST: RMS u/u0 error 0.07-0.18, a spurious lower eddy and early jet separation, not
  improved by refinement. Standard k-epsilon: 0.04-0.07 (the 80 mm ceiling line 0.12). Buoyant case 2D2 has no data.
- User decision: the scenario queue uses k-epsilon (`ledger/cfd.yaml`). Queue re-tagged `_ke`: baseline m0 first (to
  compare with the SST baseline), then S6, S2, S5a, S5b; the closing sensor ranking uses only the k-epsilon runs.
  The GCI study stays kOmegaSST. One-core 20-iteration smoke test of the k-epsilon habitat case passed (Mesh OK, no NaN).
- `foam.run(..., exclusive=False)` lets single-rank verification cases run beside the campaign; production runs keep
  the host lock.

## GCI result (2026-10-13 16:01)
- All three meshes pass their gates (effective h 48.7 / 62.8 / 84.6 mm; 548k / 255k / 104k cells; r21 1.29, r32 1.35).
- With the report's two tests (differences above the time-averaging noise, p in 0.5-3): 5 of 19 quantities have a
  quotable GCI: room-mean T rise 2.9 %, crew_1 T 6.5 %, canopy T 3.8 %, aisle x=5 T 3.1 % and CO2 2.0 %.
- Room-wide means change <= 2.7 % fine-to-coarse; local values up to 13 % (aisle x=8 CO2, beside crew 2); air speeds
  are noise-dominated. kOmegaSST runs: the k-epsilon scenarios are not covered by this study.

## Engine-pack colliders + navmesh (2026-10-13)
- `habitat.vr.nav` (in `make vr`): 28 box colliders (`UCX_<element>`, plus floor/ceiling/walls/partition) and a walkable
  navmesh (living floor minus equipment footprints grown by 0.25 m; head clearance 1.9 m; both declared in
  ledger/vr_detail.yaml). Gates pass: one connected piece, door end to partition, no vertex inside equipment.
- Walkable 6.5 of 25.2 m2; narrowest clear aisle 0.89 m at 0.5 m from the door (battery cabinet vs NFT wall)
  (`results/nav.json`); in TEAM_BRIEF as a layout figure, not a code check.
- Viewer: VR teleport now lands only on the navmesh (three.js layer 1: not drawn, not click-picked); floor fallback.
  Checked in the browser: navmesh bounds 0.25-10.52 m x 0.25-2.09 m at 5 mm, no console messages.
- Viewer measure tool (2026-10-13): "Measure" toggle, two clicks -> straight / horizontal / vertical distance in metres
  (glTF y up). Browser check: line drawn, readout matches the two hit points; scene scale is the ISO 12.192 m length.
- Viewer guided tour (2026-10-13): "Tour the zones" steps through 8 Fig 3 zones (NFT wall, Kratky, Dutch buckets,
  propagation rack, bioreactor bay, workbench, battery cabinet, attic partition); stops computed from each element's
  geometry, camera at 1.6 m in the aisle. First version put 4 cameras inside equipment across the aisle and one
  outside the door wall; fixed and re-checked: all 8 cameras inside the room and >= 0.15 m clear of every element.
- DXF exchange drawings + cross-sections (2026-10-13): `habitat.drawings_cad` (in `make drawings`) writes plan, both
  elevations and two sections (A-A through the battery cabinet / NFT wall, B-B through the workbench / bioreactor bay)
  as DXF (mm, layers EQUIPMENT / SOURCE_ZONE / PAYLOAD / OPENING / OUTLINE / DIMS / TEXT) plus FPM_sections.(svg|pdf|png).
  Checked: dimensions read back as 11785.6 x 2336.8 x 2698 mm (tests/test_dxf.py). ezdxf now a declared dependency.
- Manuscript seed (2026-10-13, user request): `manuscript/main.tex` + `refs.bib` + generated `numbers.tex`
  (`make manuscript`). Authors as asked: Richard Barker, John M. Peters (ICES byline form; the user wrote "John Micheal
  Peters", so the full middle name is a TODO), D. Marshall Porterfield last (ICES spelling "Marshall"). Affiliations
  from the ICES-2026-251 footnotes. References verified this session (CrossRef for the DOIs; Celik et al. 2008 has
  no CrossRef author list, so authors are from Semantic Scholar, marked TODO). Introduction, discussion, author
  contributions and competing interests are TODO for the authors; k-epsilon results show as TODO macros.

## k-epsilon baseline (2026-10-13 20:47)
- `fpm_m0_coarse_ke_tr` passes every gate (heat +0.42 %, CO2 -0.92 %, age +0.80 %, stationary).
- vs the kOmegaSST baseline (`results/cfd/model_compare.md`): room-wide means within 1.9 %, local values up to 25 %
  (aisle x=8 CO2, beside crew 2), speeds up to 18 %. The model/mesh ratio count (10 of 19 above 1) is unstable where
  the mesh spread is near zero, so the docs quote the percentages. Room-scale findings stand under both models.
- Campaign continues: s6_ke running, then s2_ke, s5a_ke, s5b_ke, then the k-epsilon sensor ranking.

## Campaign results so far, and a write-time defect (2026-10-14)
- m0_ke PASS, s2_ke PASS, s6_ke FAIL (CO2/H2O balance +1.11 %, bay tracer +2.22 % [photobioreactor +0.52, nft_wall -0.82]; stationary flow -> averaging
  window too short), s5a running, s5b queued.
- S2 vs the k-eps baseline (`results/cfd/scenarios.md`): CO2 rise x2.97 (3x crew), T rise x1.61 (1.65x heat), i.e.
  ~272 ppm and 5.0 K above supply; crew zones x2.1-2.25 (own plume dominates).
- Defect: transient.make rounded endTime and writeInterval separately, so some runs never wrote their final fields:
  GCI xcoarse (last write 1108 s of 1329.5) and both S6 runs (1155.5 of 1386.5). Gates/tables use the time series
  (full window) and are unaffected; field-based outputs (GCI xcoarse quantities, S6 maps) used a shorter window.
  Fixed in transient.make (endTime = n x writeInterval). `habitat.cfd.extend` restarts a case to a new end;
  post._dat / s6_report.probe_values now stitch restarts and drop the re-run overlap (tests/test_restart_series.py).
- `habitat.cfd.after_campaign` (detached, waits for the campaign): extend GCI xcoarse to its end and recompute the
  GCI; extend s6_ke to 5 flush times and re-run its siting report; repair any other short k-eps run; final sensor
  ranking over all passing k-eps cases. The SST S6 run is not extended (a restart would replace its tail with a new
  realisation); its maps caption states the 1.5-flush window.
- S5a (half airflow) FAIL: heat -1.70 %, CO2/H2O -3.25 %, age -2.97 %, not stationary (window halves +0.12 K,
  +4.0 ppm): the room was still warming and accumulating CO2 when averaging began (flush time 892 s at half flow).
  -> follow-up queue extends it 3 flush times with a fresh averaging window (fieldAverage restartOnRestart; keyword
  confirmed in the v2606 library; extend() checks the solver log for "Restarting averaging"). S6 k-eps gets the same
  fresh-window extension instead of a longer window across its start. Follow-up queue restarted (PID 6932) to pick
  this up; it still waits for S5b.
- 2026-10-14 ~14:55 the Mac restarted (cause not in the logs; no software update that day). Lost: S5b's transient
  (57.6 s in, nothing written) and ~7 h of queue time; Colima was down until restarted at 22:03 (Superset container
  not restarted). The campaign process died; the follow-up queue was relaunched (PID 99853) in priority order:
  GCI xcoarse -> S6 fresh-window extension -> S5b rebuilt from its finished steady start (fixed write alignment)
  -> S5a fresh-window extension -> repair -> sensor ranking. Est. ~15 h.
- GCI recomputed after completing the xcoarse run to its end (22:12): xcoarse values moved < 0.5 %, but GCIs swing:
  room-mean T 2.94 -> 8.23 % (p 1.29 -> 0.51), canopy T no longer quotable (p 0.03), crew_1 T 6.46 -> 4.57 %, aisle x=5
  T 3.07 -> 5.56 %, CO2 2.01 -> 2.13 %; 4 of 19 pass both tests (was 5). Room-wide spread <= 2.6 % (was 2.7), local
  <= 13 %. Superseded values above (2026-10-13 GCI section) came from the truncated xcoarse window.
- 2026-10-15: S6 k-eps with a fresh 3-flush averaging window PASSES every gate (3 tracer balances + general);
  mixed off-gas 0.81 ppm on all routes, canopy +1.14 ppm on the NFT route (kOmegaSST run: 0.80-0.81, 1.14) -> report,
  brief and manuscript now use the k-eps run. S5b rebuilt run FAILED (heat +1.10 %, CO2 +1.44 %, still cooling:
  halves -0.053 K, -1.86 ppm) -> chained after the queue: 3-flush fresh-window extension
  (`python -m habitat.cfd.extend ... --reset`), then `python -m habitat.cfd.sensors --passing-ke`. S5a extension running.
- 2026-10-15 restart artefact: the fresh-window extension of S5a failed again (heat +1.50 %, not stationary). Its
  history shows the room-mean T jumping +0.32 K at the restart (volAvg, not just the return), then draining over
  ~2 flush times; S6's restart showed no jump (-0.009 K). S5a's room pressure had drifted to ~101,640 Pa (sealed-box
  warming with mass-flow BCs on both grilles) vs S6's ~101,316 Pa. Exact mechanism not pinned down (likely the
  restart's first pressure corrections + the dp/dt work term); conclusion: restart extensions are unreliable after a
  large pressure drift. Evidence kept: runs/fpm_s5a_coarse_ke_tr_attempt1, results/cfd/fpm_s5a_coarse_ke_tr_attempt1_*.
- User decision: re-run S5a only, uninterrupted (6 flush times, average the last 3; ~9 h, started ~08:40), then
  gates + scenarios + sensor ranking (chained). S5b reported as unsettled; its extension was stopped. Note: killing
  the Python driver does NOT stop its Docker container -- the S5b container ran 43 min alongside S5a's start until
  stopped with `docker stop`.
- 2026-10-15 15:54: S5a uninterrupted run PASSES (heat +0.16 %, CO2 -0.53 %, age -0.55 %; halves 0.013 K / 0.95 ppm).
  vs the k-eps baseline: T rise x2.35, CO2 x2.44, age x2.26 (mean age 1009 s vs V/Q 892 s: air-change efficiency
  ~0.44 < 0.5), occupied speed x0.67 -> mixing worsens at low flow. Sensor ranking now over 4 passing k-eps runs
  (m0, s2, s5a, s6): best = attic partition y 0.75 m, z 1.2 m (worst 0.27 K, 4.9 %; 1.56 m from growing systems).
  Report, brief, manuscript and viewer overlay regenerated. Campaign complete except S5b (reported unsettled).
- 2026-10-16 manuscript text (user request): abstract, introduction and discussion written; methods now state the
  actual averaging windows; air-change efficiency added (baseline 0.50, half airflow 0.44; Sandberg & Sjoberg 1983);
  7 new references, each CrossRef-checked (Zabel 2020, Fu 2016, Wheeler 2017, Chen 1995, Nielsen 2015, Sandberg 1981,
  Sandberg & Sjoberg 1983). New numbers are macros (tower/site counts and loads from the ledger, ACE from results).
  Drafts flagged TODO for the authors: CRediT contributions, an AI-use statement, competing interests, title, name forms/ORCIDs. 7 pages, no undefined references.

## Payloads made generic (2026-10-16, user request: repo shared with J. M. Peters for continued development)
- Branded payloads replaced by generic, unbranded placeholders (bioreactor rack, photobioreactor, incubator, sensor
  module); all their values are now declared assumptions with `ask_team`, numerically unchanged so every CFD result
  stays valid. The bay is called the bioreactor bay (the paper's Fig 2 label is kept only where quoted from the source).
- Port data moved to `ledger/payload_ports.json`; the old port extractor was removed.
- Local run directories were relabelled (identifiers only, no field values changed; the regenerated S6 siting JSON
  matches the previous one value for value) instead of re-solved. The superseded kOmegaSST S6 outputs were removed.
- The site report no longer loads an external theme.

## Manuscript figures and tables (2026-10-16)
- `habitat/manuscript_figures.py` (run by `make manuscript`) writes 7 figures (`manuscript/figures/`) and 6 tables
  (`manuscript/tables/`) from the result files and the local run fields; the field figures are skipped, and the committed
  files kept, where `runs/` is absent. Palette: reference categorical slots 1-3, validated all-pairs; every series also
  has a line style and a legend entry.
- Correction: the manuscript had quoted a GCI for the room-mean temperature rise, but its mesh differences are within the
  time-averaging noise; the text now gives the spread instead and the count of quotable quantities (macros `GciNOk`/`GciN`).
- Drawing labels in the bioreactor bay shortened (PBR, S; key in the sheet note) so they no longer overlap.
- DXF export was not byte-reproducible (ezdxf orders some objects by set iteration): `drawings_cad` now re-runs itself
  with PYTHONHASHSEED=0.
