"""Write manuscript/numbers.tex: every number the manuscript quotes, as a LaTeX macro, from the result files.

    uv run python -m habitat.manuscript_numbers

The manuscript never types a result. A result file that is missing (e.g. a run still in progress) gives a visible
\\todo placeholder instead of a number.
"""
from __future__ import annotations

import json
import subprocess

from . import ROOT
from .provenance import Ledger

OUT = ROOT / "manuscript" / "numbers.tex"


def _j(rel):
    p = ROOT / rel
    return json.loads(p.read_text()) if p.exists() else None


def main() -> None:
    L = Ledger()
    head = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "--short", "HEAD"], capture_output=True, text=True).stdout.strip()
    m = {"LedgerDigest": L.digest(), "GitHead": head, "NRecords": len(L.records), "NAssumed": len(L.assumptions())}
    kinds = {}
    for r in L.records.values():
        kinds[r["kind"]] = kinds.get(r["kind"], 0) + 1
    m.update({"NSpecified": kinds.get("specified", 0), "NDerived": kinds.get("derived", 0)})
    m.update({"NTowers": f"{L.num('fpm.hydroponics.towers', '-'):.0f}",
              "NSitesPerTower": f"{L.num('fpm.hydroponics.sites_per_tower', '-'):.0f}",
              "NSites": f"{L.num('fpm.hydroponics.towers', '-') * L.num('fpm.hydroponics.sites_per_tower', '-'):.0f}",
              "LoadAvg": f"{L.num('fpm.electrical.load_average', 'W'):.0f}"})
    fig2 = _j("sources/fig2_geometry.json")
    if fig2:
        m["FigTwoMaxErrIn"] = f"{fig2['max_dimension_error_in']:.3f}"
        m["FigTwoDims"] = len(fig2["dimension_check"])
    g = _j("results/cfd/fpm_m0_coarse_tr_gates.json")
    if g:
        m.update({"BaseCells": f"{g['cells']:,}".replace(",", "{,}"), "BaseVolume": f"{g['mesh_volume_m3']:.1f}",
                  "BaseHeatErr": f"{100 * g['rel_err']['heat_removed_W']:+.2f}",
                  "BaseCOTwoErr": f"{100 * g['rel_err']['co2_removed_mol_s']:+.2f}",
                  "BaseAgeErr": f"{100 * g['rel_err']['age_return_s']:+.2f}",
                  "BaseReturnCOTwo": f"{sum(g['steady']['return_dCO2_halves_ppm']) / 2:.0f}"})
    gci = _j("results/cfd/gci_m0.json")
    if gci:
        sp = {k: abs(r["phi_fine"] - r["phi_coarse"]) / abs(r["phi_fine"]) * 100 for k, r in gci["gci"].items()
              if r["phi_fine"] and "U_" not in k}
        hs = [d["h_m"] * 1000 for d in gci["meshes"].values()]
        m.update({"GciHFine": f"{hs[0]:.1f}", "GciHMed": f"{hs[1]:.1f}", "GciHCoarse": f"{hs[2]:.1f}",
                  "GciDomainMax": f"{max(v for k, v in sp.items() if k.startswith('domain:')):.1f}",
                  "GciLocalMax": f"{max(v for k, v in sp.items() if not k.startswith('domain:')):.0f}",
                  "GciRoomT": f"{gci['gci']['domain:T_excess_K']['gci_fine_pct']:.1f}",
                  "GciRoomP": f"{gci['gci']['domain:T_excess_K']['p']:.2f}"})
    a20 = _j("results/cfd/annex20.json")
    if a20:
        def rng(model):
            v = [e["rms"] for k, r in a20["runs"].items() if k.startswith(model) for e in r["errors"].values()]
            return f"{min(v):.2f}", f"{max(v):.2f}"
        (m["SstLo"], m["SstHi"]), (m["KeLo"], m["KeHi"]) = rng("kOmegaSST"), rng("kEpsilon")
    s6 = _j("results/cfd/fpm_s6_coarse_ke_tr_siting.json")       # k-epsilon run once it passes, else kOmegaSST
    if not (s6 and s6.get("pass")):
        s6 = _j("results/cfd/fpm_s6_coarse_tr_siting.json")
    if s6:
        m["OffgasMixed"] = f"{max(s6['return_ppm'].values()):.1f}"
        m["OffgasCanopyNFT"] = f"{s6['rows']['zone:nft_canopy']['nft_wall']:.1f}"
    lb = _j("results/light_budget.json")
    if lb:
        a = next(v for k, v in lb["areas"].items() if k.startswith("NFT wall"))
        m["LoadMax"] = f"{lb['inputs']['load_max_W']:.0f}"
        m.update({"LightMaxPPF": f"{a['ppf_max_all_450W_to_light']:.0f}", "LightPowerNeeded": f"{a['power_for_mec_minimum_W']:.0f}",
                  "LightEff": f"{lb['inputs']['fixture_umol_J']:g}", "MecLo": f"{lb['inputs']['mec_ppf_range'][0]:.0f}",
                  "MecHi": f"{lb['inputs']['mec_ppf_range'][1]:.0f}", "WallArea": f"{a['area_m2']:.2f}"})
    s3 = _j("results/s3_hvac_off.json")
    if s3:
        sealed = {c["crew"]: c["hours_to_limit"] for c in s3["cases"] if c["ach"] == 0}
        m.update({"SthreeSixCrew": f"{sealed[6]:.1f}", "SthreeTwoCrew": f"{sealed[2]:.1f}",
                  "OutdoorCOTwo": f"{s3['co2_outdoor_ppm']:.1f}", "SthreeVolume": f"{s3['air_volume_m3']:.1f}"})
    nav = _j("results/nav.json")
    if nav:
        m.update({"AisleMin": f"{nav['min_clear_aisle_m']:.2f}", "WalkArea": f"{nav['walkable_area_m2']:.1f}",
                  "FloorArea": f"{nav['floor_area_m2']:.1f}"})
    sc = _j("results/cfd/scenarios.json")
    if sc:
        for key, tag in (("s2", "Stwo"), ("s5a", "Sfivea")):
            if key in sc["scenarios"]:
                r = sc["scenarios"][key]["rows"]
                m[f"{tag}TRatio"] = f"{r['domain:T_excess_K']['ratio']:.2f}"
                m[f"{tag}COTwoRatio"] = f"{r['domain:dCO2_ppm']['ratio']:.2f}"
                m[f"{tag}AgeRatio"] = f"{r['domain:AoA_s']['ratio']:.2f}"
                m[f"{tag}COTwo"] = f"{r['domain:dCO2_ppm']['scenario']:.0f}"
        # air-change efficiency = nominal time constant / (2 x room-mean age of air); 0.5 for complete mixing
        for key, tag, case in (("base", "Base", "fpm_m0_coarse_ke_tr"), ("s5a", "Sfivea", "fpm_s5a_coarse_ke_tr")):
            meta = _j(f"runs/{case}/case_meta.json")
            if meta and (key == "base" or key in sc["scenarios"]):
                age = (sc["scenarios"]["s5a"]["rows"]["domain:AoA_s"]["scenario"] if key == "s5a"
                       else next(iter(sc["scenarios"].values()))["rows"]["domain:AoA_s"]["base"])
                m[f"{tag}ACE"] = f"{meta['transient']['t_flush_s'] / (2 * age):.2f}"
    sp = _j("results/cfd/sensor_placement.json")
    if sp and sp.get("ranked"):
        best = sp["ranked"][0]
        m.update({"SensorRuns": len(sp["cases"]), "SensorT": f"{best['worst_T']:.2f}",
                  "SensorCOTwo": f"{best['worst_dCO2']:.1f}", "SensorZ": f"{best['z_m']:.1f}",
                  "SensorWhere": ("the attic partition" if "attic" in best["wall"] else "a long wall"),
                  "SensorClear": f"{best['clearance_m']:.1f}"})
    mc = _j("results/cfd/model_compare.json")
    if mc:
        m["ModelDomainMax"] = f"{mc['summary']['domain_max_pct']:.1f}"
        m["ModelLocalMax"] = f"{mc['summary']['local_max_pct']:.0f}"
        m["ModelSpeedMax"] = f"{mc['summary']['speed_max_pct']:.0f}"
    lines = ["% generated by habitat/manuscript_numbers.py from the result files; do not edit by hand\n"]
    missing = "\\todo{missing}"
    for k, v in m.items():
        lines.append(f"\\newcommand{{\\{k}}}{{{v if v is not None else missing}}}\n")
    for k in ("ModelDomainMax", "ModelLocalMax", "ModelSpeedMax"):                      # pending results show as visible TODOs
        if k not in m:
            lines.append(f"\\newcommand{{\\{k}}}{{\\todo{{pending: k-epsilon baseline}}}}\n")
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text("".join(lines))
    print(f"wrote {OUT} ({len(m)} values)")


if __name__ == "__main__":
    main()
