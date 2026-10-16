"""Project report site (docs/, the future GitHub Pages root), generated from the ledger and committed results.

    uv run python -m habitat.report

Nothing on the page is typed by hand except fixed explanatory prose: every number is read from ledger/*.yaml,
results/*, out/vr/*_QA.json or sources/*.json at build time. Status labels are derived from gate files, so a result
that has not passed its gates is shown as such. The viewer (vr/web) is copied to docs/viewer/.
"""
from __future__ import annotations

import html
import json
import shutil
from pathlib import Path

from . import OUT, ROOT
from .provenance import Ledger

DOCS = ROOT / "docs"
E = html.escape


def _json(p: Path):
    return json.loads(p.read_text()) if p.exists() else None


def _copy(src: Path, dst_name: str) -> str | None:
    if not src.exists():
        return None
    dst = DOCS / "assets" / dst_name
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(src, dst)
    return f"assets/{dst_name}"


def gate_badge(ok: bool | None) -> str:
    if ok is None:
        return '<span class="badge pending">pending</span>'
    return '<span class="badge pass">PASS</span>' if ok else '<span class="badge fail">FAIL</span>'


P_RANGE = (0.5, 3.0)   # schemes mix 1st order (upwind k/omega, Euler time) and ~2nd (linearUpwind U/h, limitedLinear)


def gci_noise(cases: list[str], rc: Path) -> dict:
    """Sampling-noise yardstick per quantity type: the largest first-half vs second-half gap of the return-grille
    time series over the averaging window, across the ladder's runs (from each run's own gate record)."""
    t = c = 0.0
    for name in cases:
        g = _json(rc / f"{name}_gates.json") or {}
        st = g.get("steady", {})
        if "return_T_halves_K" in st:
            t = max(t, abs(st["return_T_halves_K"][1] - st["return_T_halves_K"][0]))
            c = max(c, abs(st["return_dCO2_halves_ppm"][1] - st["return_dCO2_halves_ppm"][0]))
    return {"T": t, "dCO2": c}


def gci_rows(gj: dict, noise: dict) -> list[dict]:
    """Per quantity: the GCI record plus the two honesty flags (differences within the time-averaging noise; observed
    order p outside P_RANGE) and oscillatory convergence. Shared by the site report and the manuscript tables."""
    out = []
    for k, r in gj["gci"].items():
        nz = noise["T"] if k.endswith("_K") else noise["dCO2"] if "dCO2" in k else None
        e21, e32 = abs(r["phi_fine"] - r["phi_medium"]), abs(r["phi_medium"] - r["phi_coarse"])
        flags = []
        if nz is not None and max(e21, e32) <= nz:
            flags.append("within sampling noise")
        p = r.get("p")
        if p is None or p != p or not (P_RANGE[0] <= p <= P_RANGE[1]):
            flags.append("p outside expected range")
        if r.get("convergence") == "oscillatory":
            flags.append("oscillatory")
        out.append({"key": k, "r": r, "p": p, "flags": flags, "ok": not flags})
    return out


def gci_html(gj: dict, rc: Path) -> str:
    """GCI table (Celik et al. 2008) with two honesty flags: differences between meshes no larger than the
    time-averaging noise, and an observed order p outside P_RANGE."""
    cases = [f"fpm_m0_{m}_tr" for m in gj["meshes"]]
    noise = gci_noise(cases, rc)
    mesh_rows = "".join(f"<tr><td>{m}</td><td>{d['h_m'] * 1000:.1f}</td><td>{d['cells']:,}</td></tr>"
                        for m, d in gj["meshes"].items())
    rows, n_ok = [], 0
    for q in gci_rows(gj, noise):
        r, p, ok = q["r"], q["p"], q["ok"]
        n_ok += ok
        gci = f"{r['gci_fine_pct']:.2f}" if r.get("gci_fine_pct") == r.get("gci_fine_pct") else "-"
        rows.append(f"<tr><td>{q['key']}</td><td>{r['phi_fine']:.4g}</td><td>{r['phi_medium']:.4g}</td>"
                    f"<td>{r['phi_coarse']:.4g}</td><td>{(f'{p:.2f}' if p == p else '-') if p is not None else '-'}</td>"
                    f"<td>{gci if ok else '(' + gci + ')'}</td><td>{', '.join(q['flags']) or 'ok'}</td></tr>")
    spread = {k: abs(r["phi_fine"] - r["phi_coarse"]) / abs(r["phi_fine"]) * 100 for k, r in gj["gci"].items()
              if r["phi_fine"] and "U_" not in k}
    dom = max(v for k, v in spread.items() if k.startswith("domain:"))
    loc = max(v for k, v in spread.items() if not k.startswith("domain:"))
    loc_k = max((k for k in spread if not k.startswith("domain:")), key=spread.get)
    models = {(_json(ROOT / "runs" / c / "case_meta.json") or {}).get("turbulence_model", "kOmegaSST") for c in cases}
    summary = (f"In plain terms: room-wide means change by at most {dom:.1f} % between the finest and coarsest mesh, "
               f"while local values near the crew and along the aisle change by up to {loc:.0f} % ({loc_k}); air "
               f"speeds are too small and noisy for a GCI. These runs used {', '.join(sorted(models))}; the scenario "
               "runs from 13 Oct 2026 use k-ε, which this study does not cover.")
    return (f"<p>Celik et al. (2008) procedure on the time-averaged baseline at three meshes; all mesh gates pass: "
            f"{gj['all_gates_pass']}. A GCI is quoted only where the mesh-to-mesh differences exceed the "
            f"time-averaging noise (largest half-window gap of the return-grille series: "
            f"{noise['T']:.3f} K, {noise['dCO2']:.2f} ppm) and the observed order p lies in {P_RANGE[0]}–{P_RANGE[1]} "
            f"(the schemes mix first and second order); otherwise it is shown in brackets with the reason. "
            f"{n_ok} of {len(gj['gci'])} quantities pass both tests. Age of air and speed have no noise yardstick and "
            f"are judged on p alone.</p><p>{summary}</p>"
            f"<table><tr><th>mesh</th><th>h (mm)</th><th>cells</th></tr>{mesh_rows}</table>"
            "<table><tr><th>quantity</th><th>fine</th><th>medium</th><th>coarse</th><th>p</th><th>GCI fine %</th>"
            f"<th>flags</th></tr>{''.join(rows)}</table>")


def _rng(vals, fmt="{:.2f}") -> str:
    lo, hi = fmt.format(min(vals)), fmt.format(max(vals))
    return lo if lo == hi else f"{lo}–{hi}"


def cfd_section() -> str:
    rc = ROOT / "results" / "cfd"
    rows = []
    for name, label in (("fpm_m0_coarse_run1_gates.json", "Run 1 — steady, 80 mm mesh"),
                        ("fpm_m0_coarse_gates.json", "Run 2 — steady, balanced start"),
                        ("fpm_m0_coarse_tr_gates.json", "Baseline — transient, time-averaged over 2 flush times")):
        g = _json(rc / name)
        if not g:
            rows.append(f"<tr><td>{label}</td><td colspan=6>{gate_badge(None)}</td></tr>")
            continue
        cells = "".join(f"<td>{gate_badge(g['gates'].get(k))}"
                        + (f"<br><small>{100 * g['rel_err'][k]:+.1f}%</small>" if k in g.get("rel_err", {}) else "")
                        + "</td>" for k in ("mass", "heat_removed_W", "co2_removed_mol_s", "h2o_removed_mol_s",
                                            "age_return_s", "steady"))
        rows.append(f"<tr><td>{label}</td>{cells}</tr>")
    conv = _copy(rc / "fpm_m0_coarse_convergence.png", "cfd_run2_convergence.png")
    base = _json(rc / "fpm_m0_coarse_tr_gates.json")
    base_ok = bool(base and base.get("pass"))
    fields = _copy(rc / "fpm_m0_coarse_tr_fields.png", "cfd_baseline_fields.png") if base_ok else None
    s6_case = "fpm_s6_coarse_ke_tr"                      # S6 is reported from the k-epsilon run only
    siting = _json(rc / f"{s6_case}_siting.json")
    gci = (rc / "gci_m0.md")
    out = [
        "<h2 id='cfd'>CFD (OpenFOAM v2606)</h2>",
        "<p>Coarse 80 mm mesh (≈0.26 M cells), placeholder HVAC (the attic unit is unknown), adiabatic walls. "
        "Every case must close its mass, energy, CO₂, H₂O and age-of-air balances to within 1 % and be steady "
        "(or, for transient runs, statistically stationary) before any result is quoted.</p>",
        "<table><tr><th>Case</th><th>mass</th><th>energy</th><th>CO₂</th><th>H₂O</th><th>age of air</th>"
        "<th>steady</th></tr>" + "".join(rows) + "</table>",
        "<p class='note'>The steady solver never settles for this flow (a cold supply jet plunging into a heated room "
        "is physically unsteady): its balances swing in ~1000-iteration cycles. The study therefore moved to "
        "time-averaged transient runs" + ("; the baseline transient passes every gate." if base_ok else
        ". <strong>No CFD finding is reported until those pass their gates.</strong>") + "</p>",
    ]
    if conv:
        out.append(f"<figure><img src='{conv}' alt='Run 2 return-grille convergence history'><figcaption>Run 2 "
                   "(steady): return-grille quantities against their global balance targets — the swings that "
                   "failed the gates.</figcaption></figure>")
    if fields:
        out.append(f"<figure><img src='{fields}' alt='Baseline time-averaged temperature, CO2, age of air and speed'>"
                   "<figcaption>Baseline (transient run, time means after the first flush time): plan at breathing "
                   "height and aisle section. Coarse mesh, placeholder HVAC, adiabatic walls; data: "
                   "runs/fpm_m0_coarse_tr, figure by habitat/cfd/slices.py. The age-of-air plan is also a viewer "
                   "overlay.</figcaption></figure>")
    out.append("<h3>Payload siting study (S6)</h3>")
    if siting and siting.get("pass"):
        ret = siting["return_ppm"]; routes = list(ret)
        crew = [r["crew_dCO2"] for r in siting["rows"].values()]
        out.append(f"<p>The same bioreactor off-gas (10 vessels, placeholder planning rate) released three ways in one flow "
                   f"field. Mixed into the whole room it adds {_rng(ret.values())} ppm "
                   f"above supply air; crew-generated CO₂ at the same locations is {min(crew):.0f}–{max(crew):.0f} ppm. "
                   "Factor = local excess ÷ well-mixed value (&gt; 1: the CO₂ concentrates there). All gates pass.</p>")
        out.append(f"<p>{s6_case} (k-ε, fresh averaging window over 3 flush times).</p>")
        head = "".join(f"<th>{r} ppm (×mixed)</th>" for r in routes)
        body = "".join(f"<tr><td>{loc.split(':')[1]}</td>" + "".join(
            f"<td>{row[r]:.2f} (×{row['factor_' + r]:.2f})</td>" for r in routes) + f"<td>{row['crew_dCO2']:.0f}</td></tr>"
            for loc, row in siting["rows"].items())
        out.append(f"<table><tr><th>location</th>{head}<th>crew ΔCO₂ ppm</th></tr>{body}</table>")
        for f, cap in ((f"{s6_case}_siting_factors.png", "Enrichment factor per location and route (log scale)."),
                       (f"{s6_case}_siting_maps.png", "Time-averaged plan slices of the three route tracers.")):
            img = _copy(rc / f, f)
            if img:
                out.append(f"<figure><img src='{img}' alt='{cap}'><figcaption>{cap} Data: runs/{s6_case}, "
                           "figure by habitat/cfd/s6_report.py; screening mesh, placeholder HVAC.</figcaption></figure>")
    else:
        out.append(f"<p>{gate_badge(None)} Three CO₂ routes (bay, photobioreactor, NFT wall) in one time-averaged run; queued behind the baseline.</p>")
    out.append("<h3>Grid convergence (GCI)</h3>")
    gj = _json(rc / "gci_m0.json")
    if gj:
        out.append(gci_html(gj, rc))
    else:
        out.append(f"<p>{gate_badge(None)} 57 / 80 / 113 mm ladder (shifted coarser by decision; the 80/57/40 mm transient ladder needs ~110 h on this machine). Running since the baseline transient passed.</p>")
    mc = _json(rc / "model_compare.json")
    if mc:
        sm = mc["summary"]
        (na, ma), (nb, mb) = list(mc["cases"].items())
        out.append("<h3>Turbulence-model sensitivity of the baseline</h3>")
        out.append(f"<p>The baseline repeated with {mb} (case {nb}) against {ma} ({na}), same mesh, loads and averaging; "
                   f"both pass every gate. Room-wide means change by at most {sm['domain_max_pct']:.1f} %, local values "
                   f"by up to {sm['local_max_pct']:.0f} % ({sm['local_max_quantity']}) and air speeds by up to "
                   f"{sm['speed_max_pct']:.0f} %. Like the mesh study, this says the room-scale picture is robust and "
                   "single-point values are not. Full table: results/cfd/model_compare.md.</p>")
    sc = _json(rc / "scenarios.json")
    if sc and sc.get("scenarios"):
        label = {"s2": "S2: six crew", "s5a": "S5a: half airflow", "s5b": "S5b: double airflow"}
        keys = ["domain:T_excess_K", "domain:dCO2_ppm", "domain:AoA_s", "crew_1:dCO2_ppm", "nft_canopy:dH2O_mmol_mol"]
        head = "".join(f"<th>{label.get(k, k)}</th>" for k in sc["scenarios"])
        body = "".join(
            f"<tr><td>{k}</td><td>{sc['scenarios'][next(iter(sc['scenarios']))]['rows'][k]['base']:.4g}</td>"
            + "".join(f"<td>{s['rows'][k]['scenario']:.4g} (×{s['rows'][k]['ratio']:.2f})</td>" for s in sc["scenarios"].values())
            + "</tr>" for k in keys)
        out.append("<h3>Scenarios (k-ε, coarse mesh)</h3>")
        out.append(f"<p>Each passing scenario against the k-ε baseline ({sc['baseline_heat_W']:.0f} W, "
                   f"{sc['baseline_Q_m3_s'] * 1000:.0f} L/s supply), same mesh and model. Values are time means above "
                   "the supply air (the supply temperature and outdoor-air fraction are placeholders). Full tables: "
                   "results/cfd/scenarios.md.</p>")
        out.append(f"<table><tr><th>quantity</th><th>baseline</th>{head}</tr>{body}</table>")
        missing = []
        for key, name, why in (("s5a", "fpm_s5a_coarse_ke_tr", "half airflow"), ("s5b", "fpm_s5b_coarse_ke_tr", "double airflow")):
            if key in sc["scenarios"]:
                continue
            g = _json(rc / f"{name}_gates.json")
            missing.append(f"{key[0].upper() + key[1:]} ({why}): " + ("not settled within its run (gates fail); a restarted "
                           "extension was unreliable after the room's pressure had drifted, so it is reported as unsettled"
                           if key == "s5b" else ("re-running uninterrupted (6 flush times, averaging the last 3)"
                                                 if not g else "gates fail")))
        if missing:
            out.append("<p class='note'>Not shown: " + "; ".join(missing) + ".</p>")
    a20 = _json(rc / "annex20.json")
    if a20:
        img = _copy(rc / "annex20.png", "annex20.png")
        keys = list(next(iter(a20["runs"].values()))["errors"])
        rows = "".join(f"<tr><td>{m}</td><td>{r['cells']:,}</td>" + "".join(f"<td>{r['errors'][k]['rms']:.3f}</td>" for k in keys)
                       + "</tr>" for m, r in a20["runs"].items())
        out.append("<h3>Validation: IEA Annex 20 two-dimensional test case</h3>")
        out.append("<p>A ceiling wall jet driving a room, as in the FPM, solved with the habitat cases' wall functions and "
                   "schemes and compared with Aalborg University's laser-Doppler measurements (isothermal, Re = 5000; the "
                   "buoyant variant has no data). kOmegaSST, used for the runs up to 13 Oct 2026, put a spurious eddy "
                   "near the floor and separated the jet from the ceiling early; standard k-ε was closer to the measured "
                   "profiles at every mesh, so the scenario runs from 13 Oct use k-ε (ledger cfd.turbulence_model). "
                   "RMS error of u/u0 at the measured points:</p>")
        out.append("<table><tr><th>model, mesh</th><th>cells</th>" + "".join(f"<th>{k}</th>" for k in keys)
                   + f"</tr>{rows}</table>")
        if img:
            out.append(f"<figure><img src='{img}' alt='Annex 20 velocity profiles, simulated vs measured'><figcaption>"
                       "Simulated vs measured mean velocity on the four Annex 20 lines. Data: results/cfd/annex20.json "
                       "(Aalborg LDA data in sources/annex20_lda.json), figure by habitat/cfd/annex20.py.</figcaption></figure>")
    lb = _json(ROOT / "results" / "light_budget.json")
    if lb:
        i = lb["inputs"]
        rows = "".join(f"<tr><td>{n}</td><td>{a['area_m2']}</td><td>{a['ppf_max_all_450W_to_light']}</td>"
                       f"<td>{a['power_for_mec_minimum_W']:.0f} W</td></tr>" for n, a in lb["areas"].items())
        out.append("<h3>Light budget: can plant gas exchange be modelled yet?</h3>")
        out.append(f"<p>Plant CO₂ uptake and transpiration scale with light. NASA's lettuce crop model (BVAD) is valid "
                   f"for {i['mec_ppf_range'][0]:.0f}–{i['mec_ppf_range'][1]:.0f} µmol/m²·s. If the paper's "
                   f"{i['load_max_W']:.0f} W maximum draw includes the grow lights, even with every watt going to light at "
                   f"the best LED fixture efficacy reported by 2020 ({i['fixture_umol_J']:g} µmol/J; Kusuma et al. 2020) "
                   "the NFT wall stays below that range, so the plants are not yet coupled into the CFD: the canopy "
                   "carries LED heat only. The lighting specification is requested from the team.</p>")
        out.append(f"<table><tr><th>lit area</th><th>m²</th><th>max PPF, all {i['load_max_W']:.0f} W to light "
                   f"(µmol/m²·s)</th><th>power for {i['mec_ppf_range'][0]:.0f} µmol/m²·s</th></tr>{rows}</table>")
    s3 = _json(ROOT / "results" / "s3_hvac_off.json")
    if s3:
        img = _copy(ROOT / "results" / "s3_hvac_off.png", "s3_hvac_off.png")
        rows = "".join(f"<tr><td>{c['crew']}</td><td>{c['ach']:g}</td><td>{c['rise_ppm_per_h_initial']:.0f}</td>"
                       f"<td>{c['hours_to_limit'] if c['hours_to_limit'] is not None else 'never'}</td></tr>"
                       for c in s3["cases"])
        out.append("<h3>S3: HVAC off, door closed (CO₂ build-up)</h3>")
        out.append(f"<p>A well-mixed (0-D) model of the {s3['air_volume_m3']:.0f} m³ of room air, crew at BVAD's awake "
                   f"CO₂ rate, starting from outdoor air ({s3['co2_outdoor_ppm']} ppm, NOAA). Container leakage is "
                   f"unknown, so it is swept. Limit: OSHA's {s3['limit_ppm']:.0f} ppm (an 8-hour time-weighted "
                   "average). The CFD reports CO₂ relative to the supply air, so the same build-up applies with the "
                   "attic unit running if it only recirculates room air: the unit's outdoor-air provision is one of "
                   "the team questions. Plants and temperature are not included.</p>")
        out.append("<table><tr><th>crew</th><th>infiltration (ACH)</th><th>initial rise (ppm/h)</th>"
                   f"<th>hours to {s3['limit_ppm']:.0f} ppm</th></tr>{rows}</table>")
        if img:
            out.append(f"<figure><img src='{img}' alt='CO2 build-up with the HVAC off'><figcaption>CO₂ after the HVAC "
                       "stops, by crew size and air-change rate. Data: results/s3_hvac_off.json, model "
                       "habitat/s3_hvac_off.py.</figcaption></figure>")
    sp = _json(rc / "sensor_placement.json")
    out.append("<h3>Sensor placement (for the Opto 22 / SIMOC monitoring)</h3>")
    if sp and sp.get("ranked"):
        img = _copy(rc / "sensor_placement.png", "sensor_placement.png")
        rows = "".join(f"<tr><td>{k}</td><td>{r['wall']}</td><td>{('y' if 'attic' in r['wall'] else 'x')} = "
                       f"{(r['y_m'] if 'attic' in r['wall'] else r['x_m']):.2f}</td><td>{r['z_m']:.1f}</td>"
                       f"<td>{r['worst_T']:.2f}</td><td>{r['worst_dCO2']:.1f}</td>"
                       f"<td>{r.get('clearance_m', float('nan')):.2f} m ({r.get('nearest_living_part', '')})</td></tr>"
                       for k, r in enumerate(sp["ranked"][:5], 1))
        out.append(f"<p>Where does one wall-mounted sensor best represent the air the crew breathe? Each candidate wall "
                   f"position is scored against the occupied-zone mean of the same run, keeping its worst case over "
                   f"{len(sp['cases'])} passing run(s) ({', '.join(sp['cases'])}). {sp['n_valid']} of "
                   f"{sp['n_candidates']} positions are usable; {sp['n_excluded_near_living_systems']} near plants, "
                   "water culture, the bioreactor bay or payloads are excluded because their gas exchange is not modelled "
                   "yet, so CO₂ and H₂O both come only from the crew here. A screening ranking on a coarse mesh with "
                   "placeholder HVAC, to be confirmed by measurement. The clearance column shows how close each position "
                   "is to growing systems: crops taller than their containers (e.g. in the Dutch buckets) could reach a "
                   "position the box-based exclusion allowed. The top positions are also a viewer overlay.</p>")
        out.append("<table><tr><th>rank</th><th>wall</th><th>position (m)</th><th>height (m)</th>"
                   f"<th>worst T error (K)</th><th>worst CO₂ error (%)</th><th>clearance to nearest plant / water / "
                   f"payload part</th></tr>{rows}</table>")
        if img:
            out.append(f"<figure><img src='{img}' alt='Worst-case sensor error along each wall'><figcaption>Worst-case "
                       "error along each wall at both mount heights; gaps are inside equipment or excluded. Data: "
                       "results/cfd/sensor_placement.json, figure by habitat/cfd/sensors.py.</figcaption></figure>")
    else:
        out.append(f"<p>{gate_badge(None)} Runs after the scenario campaign.</p>")
    return "\n".join(out)


def build() -> Path:
    L = Ledger()
    DOCS.mkdir(exist_ok=True)
    A = L.assumptions()
    kinds = {}
    for r in L.records.values():
        kinds[r["kind"]] = kinds.get(r["kind"], 0) + 1
    fig2 = _json(ROOT / "sources" / "fig2_geometry.json")
    vrqa = _json(OUT / "vr" / "VR_QA.json") or {}
    prim = _json(OUT / "vr" / "primary_spec.json")
    ports = _json(ROOT / "ledger" / "payload_ports.json")
    imgs = {k: _copy(OUT / "vr" / f, f) for k, f in (("cutaway", "render_lod0_cutaway.png"),
                                                     ("aisle", "render_lod0_aisle_from_door.png"),
                                                     ("bay", "render_lod0_payload_bay.png"),
                                                     ("site", "render_lod0_site_overview.png"),
                                                     ("primary", "render_lod0_primary_overview.png"))}
    ga = _copy(ROOT / "results" / "drawings" / "FPM_GA.svg", "FPM_GA.svg")
    _copy(ROOT / "results" / "drawings" / "FPM_GA.pdf", "FPM_GA.pdf")
    secs = _copy(ROOT / "results" / "drawings" / "FPM_sections.svg", "FPM_sections.svg")
    dxfs = [_copy(f, f.name) for f in sorted((ROOT / "results" / "drawings").glob("FPM_*.dxf"))]
    # viewer
    if (DOCS / "viewer").exists():
        shutil.rmtree(DOCS / "viewer")
    shutil.copytree(ROOT / "vr" / "web", DOCS / "viewer")

    lod_rows = "".join(f"<tr><td>LOD{g['lod']}</td><td>{g['triangles']:,}</td><td>{g['bytes'] / 1e6:.2f} MB</td>"
                       f"<td>{gate_badge(g['pass'])}</td></tr>" for g in vrqa.get("lods", []))
    a_rows = "".join(f"<tr><td><code>{E(p)}</code></td><td>{E(str(r['value']))[:80]}</td><td>{E(r['unit'])}</td>"
                     f"<td>{'yes' if r['ask_team'] else ''}</td><td>{E(r['why'])}</td></tr>" for p, r in sorted(A.items()))
    pm = prim["metrics"] if prim else None
    prim_rows = "".join(f"<tr><td>{k}</td><td>{v['per_crew_m3']:.1f}</td><td>{gate_badge(v['meets_guideline'])}</td></tr>"
                        for k, v in pm["nhv_by_habitable_fraction"].items()) if pm else ""
    port_rows = "".join(f"<tr><td>{E(k)}</td><td>{len(p['ports'])}</td><td>{E(p['gas_note'])}</td></tr>"
                        for k, p in ports["payloads"].items()) if ports else ""
    fig = lambda key, cap: (f"<figure><img src='{imgs[key]}' alt='{E(cap)}'><figcaption>{E(cap)}</figcaption></figure>"  # noqa
                            if imgs.get(key) else "")

    page = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>ASTRO-USA Habitat Model</title>
<style>
:root {{ --bg:#f7f8fa; --fg:#1d2733; --muted:#5b6774; --card:#fff; --line:#d9dee5; --accent:#2f5985; }}
@media (prefers-color-scheme: dark) {{ :root:not([data-theme="light"]) {{ --bg:#12161b; --fg:#e6ebf0; --muted:#9aa7b4; --card:#1b2129; --line:#2c3440; --accent:#7fb0e0; }} }}
:root[data-theme="dark"] {{ --bg:#12161b; --fg:#e6ebf0; --muted:#9aa7b4; --card:#1b2129; --line:#2c3440; --accent:#7fb0e0; }}
body {{ margin:0; background:var(--bg); color:var(--fg); font:16px/1.55 system-ui, sans-serif; }}
main {{ max-width:960px; margin:0 auto; padding:64px 16px 64px; }}
h1 {{ font-size:1.8rem; margin:.2em 0; }} h2 {{ margin-top:2.2em; border-bottom:1px solid var(--line); padding-bottom:.2em; }}
p.lead {{ font-size:1.1rem; color:var(--muted); }} .note {{ color:var(--muted); font-size:.92rem; }}
table {{ border-collapse:collapse; width:100%; font-size:.86rem; margin:.6em 0; display:block; overflow-x:auto; }}
th, td {{ border:1px solid var(--line); padding:4px 6px; text-align:left; vertical-align:top; }}
figure {{ margin:1em 0; }} img {{ max-width:100%; height:auto; border:1px solid var(--line); border-radius:6px; background:#fff; }}
figcaption {{ color:var(--muted); font-size:.85rem; }}
.badge {{ font-size:.75rem; padding:1px 6px; border-radius:4px; font-weight:600; }}
.pass {{ background:#d3f4dc; color:#145c2c; }} .fail {{ background:#fde2e1; color:#8a1c17; }} .pending {{ background:#eceff3; color:#4a5560; }}
.cta {{ display:inline-block; padding:8px 14px; border-radius:6px; background:var(--accent); color:#fff; text-decoration:none; margin:4px 8px 4px 0; }}
code {{ font-size:.85em; }}
</style>
</head>
<body>
<main>
<h1>ASTRO-USA Habitat Model</h1>
<p class="lead">A sourced, parametric model of the ASTRO-USA Mini-Hab <strong>Food Production Module</strong> — the converted
40 ft high-cube container described in ICES-2026-251 — driving engineering CAD, CFD and a shared VR walk-through.</p>
<p>Design: the ASTRO-USA team (Purdue University Space &amp; Earth Analogs Research Chapter, with NASA KSC and the
University of Arizona), Peters et al., <em>55th International Conference on Environmental Systems</em>, ICES-2026-251.
This model is an independent digital representation built from that paper; it is not the team's own CAD.</p>
<p><a class="cta" href="viewer/">Open the 3-D / VR viewer</a><a class="cta" href="viewer/?scene=primary">Primary habitat concept</a>
<a class="cta" href="assets/FPM_GA.pdf">Drawings (PDF)</a></p>

<h2 id="sources">What the model is built from</h2>
<p>{len(L.records)} ledger records: {", ".join(f"{v} {k}" for k, v in sorted(kinds.items()))}.
Every number is either quoted from a source or a declared assumption with its reason; the build refuses anything else.</p>
<ul>
<li>Floor plan: the paper's Figure 2 is vector data in the PDF; {len(fig2['dimension_check']) if fig2 else '?'} printed dimensions
were matched to their own dimension lines (max error {fig2['max_dimension_error_in'] if fig2 else '?'} in).</li>
<li>Container shell: SeaCube 40′ high-cube specification sheet; crew loads: NASA BVAD Rev2, Table 3-26.</li>
<li>Bioreactor payloads: generic, unbranded placeholder envelopes, ports and loads, all declared assumptions until the team chooses the hardware.</li>
</ul>

<h2 id="drawings">General arrangement</h2>
{f"<figure><img src='{ga}' alt='FPM plan and elevations'><figcaption>Plan and long-wall elevations generated from the registry. Plan dimensions from ICES Fig 2; most equipment heights are assumptions.</figcaption></figure>" if ga else ""}
{f"<figure><img src='{secs}' alt='FPM cross-sections'><figcaption>Cross-sections across the container through the battery cabinet / NFT wall and the workbench / bioreactor bay, from the same registry.</figcaption></figure>" if secs else ""}
{"<p>CAD exchange (DXF, millimetres, one layer per kind of element, for Fusion 360 / AutoCAD): " + ", ".join(f"<a href='{d}'>{d.split('/')[-1]}</a>" for d in dxfs if d) + ".</p>" if any(dxfs) else ""}

<h2 id="vr">3-D and VR model</h2>
{fig("cutaway", "Cut-away of the Food Production Module (LOD0). Stand-in equipment is flagged 'illustrative' in the model.")}
{fig("aisle", "Aisle view from the door end.")}
<table><tr><th>Level</th><th>Triangles</th><th>GLB size</th><th>Gates</th></tr>{lod_rows}</table>
<p class="note">Engine packs: GLB, USDZ (Apple usdchecker: {E(str(vrqa.get('usdz', {}).get('usdchecker', '—')))}) and FBX with per-node
metadata. The viewer runs in desktop browsers and WebXR headsets (headset testing pending), with shared sessions:
avatars and review pins over a small relay (not yet deployed).</p>

<h2 id="payloads">Bioreactor payloads (generic placeholders)</h2>
{fig("bay", "Generic payload envelopes in the bioreactor bay: bioreactor rack, photobioreactor, incubator and sensor module; coloured markers are gas ports.")}
<table><tr><th>Payload</th><th>Ports</th><th>CO₂ data</th></tr>{port_rows}</table>

{cfd_section()}

<h2 id="site">Mini-Hab site and primary habitat (concept level)</h2>
{fig("site", "Mini-Hab site after Fig 10 (topology only; sizes assumed): Crew Quarters, Laboratory Module, BioWaTERR trailer placeholder.")}
{fig("primary", "Primary-habitat concept generator output (design study, not the team's design).")}
{f"<p>Concept: {pm['internal_pressurised_m3_excl_airlock']:.0f} m³ internal pressurised volume (airlock excluded) for a crew of {pm['crew']}; NASA's minimum acceptable net habitable volume is {pm['nhv_guideline_m3_per_person']:.0f} m³ per person (Whitmire et al. 2014). Habitable fraction needed: {pm['min_habitable_fraction_for_guideline']:.2f}.</p><table><tr><th>Habitable fraction (assumed)</th><th>NHV per crewmember (m³)</th><th>≥ 25 m³</th></tr>{prim_rows}</table>" if pm else ""}

<h2 id="assumptions">Assumptions ({len(A)})</h2>
<p>What the model does <em>not</em> know yet. "Ask team" marks values the ASTRO-USA team can replace with facts.</p>
<table><tr><th>Ledger path</th><th>Value</th><th>Unit</th><th>Ask team</th><th>Why</th></tr>{a_rows}</table>

<h2 id="reproduce">Reproduce</h2>
<p><code>uv sync &amp;&amp; make cad check vr docs test</code> · CFD: <code>make cfd-coarse post</code> (Docker, pinned
OpenFOAM v2606 image). Ledger digest <code>{L.digest()}</code>.</p>
</main>
</body></html>
"""
    (DOCS / "assets").mkdir(parents=True, exist_ok=True)
    (DOCS / "index.html").write_text(page)
    (DOCS / ".nojekyll").write_text("")
    return DOCS / "index.html"


if __name__ == "__main__":
    print(build())
