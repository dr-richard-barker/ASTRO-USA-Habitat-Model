"""Light-budget check: what canopy light (PPF) can the FPM's stated power budget deliver to the NFT wall?

    uv run python -m habitat.light_budget

Why it matters: plant CO2 uptake and transpiration scale with light. The crop model the plan intended (BVAD's
Modified Energy Cascade) is valid for lettuce only from 200 to 500 umol/m2/s, so before coupling plants into the CFD
we check whether the module's stated power can reach that range at all.

Bounds, all taken generously (every watt to light, the best fixture efficacy achieved by 2020):
  * instantaneous: the 450 W maximum steady draw, all into lights;
  * daily: the ~8 kWh/day energy use, all into lights, spread over the nominal 16 h lettuce photoperiod.
Two lit areas bracket the canopy: the NFT wall face in the model (registry nft_canopy, length x height) and the area
297 lettuce plants occupy at BVAD's nominal planting density. The physical ceiling for photosynthetic photons
(1 J of 700 nm light) is shown for reference.

Outputs: results/light_budget.json and .md.
"""
from __future__ import annotations

import json

from . import ROOT
from .provenance import Ledger
from .registry import build

H, C, NA = 6.62607015e-34, 299792458.0, 6.02214076e23     # SI-defined constants (exact)
OUT = ROOT / "results"


def umol_per_J(wavelength_nm: float) -> float:
    """Photon flux per watt of monochromatic light: lambda / (h c N_A), in umol/J."""
    return wavelength_nm * 1e-9 / (H * C * NA) * 1e6


def run() -> dict:
    L, parts = build()
    can = next(p for p in parts if p.id == "nft_canopy")
    wall_area = (can.hi[0] - can.lo[0]) / 1000 * (can.hi[2] - can.lo[2]) / 1000
    sites = int(L.num("fpm.hydroponics.towers", "-") * L.num("fpm.hydroponics.sites_per_tower", "-"))
    density_area = sites / L.num("crops.lettuce_planting_density", "plants/m2")
    Hh = L.num("crops.lettuce_photoperiod", "h/d")
    ppf_lo, ppf_hi = L.val("crops.lettuce_mec_ppf_range")
    eff = L.num("crops.led_fixture_efficacy_best", "umol/J")
    p_max = L.num("fpm.electrical.load_max_steady", "W")
    e_day = L.num("fpm.electrical.daily_energy", "kWh")
    areas = {"NFT wall face (model geometry)": wall_area, f"{sites} plants at BVAD density": density_area}
    res = {"inputs": {"sites": sites, "photoperiod_h": Hh, "mec_ppf_range": [ppf_lo, ppf_hi], "fixture_umol_J": eff,
                      "load_max_W": p_max, "daily_energy_kWh": e_day,
                      "photon_ceiling_700nm_umol_J": round(umol_per_J(700), 3)},
           "ledger_digest": L.digest(), "areas": {}}
    for name, A in areas.items():
        res["areas"][name] = {
            "area_m2": round(A, 2),
            "ppf_max_all_450W_to_light": round(p_max * eff / A, 1),
            "ppf_mean_all_daily_energy_over_photoperiod": round(e_day * 1000 / Hh * eff / A, 1),
            "power_for_mec_minimum_W": round(ppf_lo * A / eff, 0),
            "daily_energy_for_mec_minimum_kWh": round(ppf_lo * A / eff * Hh / 1000, 2),
            "efficacy_needed_at_450W_umol_J": round(ppf_lo * A / p_max, 2),
        }
    res["below_mec_range_in_every_bound"] = all(
        max(a["ppf_max_all_450W_to_light"], a["ppf_mean_all_daily_energy_over_photoperiod"]) < ppf_lo
        for a in res["areas"].values())
    return res


def write(res: dict) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "light_budget.json").write_text(json.dumps(res, indent=1) + "\n")
    i = res["inputs"]
    lines = [f"# Light budget of the NFT wall (ledger {res['ledger_digest']})\n\n",
             f"If the FPM's stated budget ({i['load_max_W']:.0f} W maximum steady draw, ~{i['daily_energy_kWh']:.0f} kWh/day) "
             f"includes the grow lights, how much light can reach {i['sites']} lettuce sites? Every watt is given to light "
             f"at the best LED fixture efficacy achieved by 2020 ({i['fixture_umol_J']:g} µmol/J), over BVAD's nominal "
             f"{i['photoperiod_h']:g} h photoperiod. BVAD's lettuce crop model is valid for "
             f"{i['mec_ppf_range'][0]:g}–{i['mec_ppf_range'][1]:g} µmol/m²·s. (Physical ceiling for photosynthetic photons: "
             f"{i['photon_ceiling_700nm_umol_J']} µmol/J at 700 nm.)\n\n",
             "| lit area | m² | max PPF, all 450 W to light | mean PPF, all daily energy to light | power for 200 µmol/m²·s | energy/day for 200 µmol/m²·s |\n",
             "|---|---|---|---|---|---|\n"]
    for name, a in res["areas"].items():
        lines.append(f"| {name} | {a['area_m2']} | {a['ppf_max_all_450W_to_light']} | "
                     f"{a['ppf_mean_all_daily_energy_over_photoperiod']} | {a['power_for_mec_minimum_W']:.0f} W | "
                     f"{a['daily_energy_for_mec_minimum_kWh']} kWh |\n")
    implied = i["daily_energy_kWh"] * 1000 / i["photoperiod_h"]
    if implied > i["load_max_W"]:
        lines.append(f"\nSpreading {i['daily_energy_kWh']:g} kWh over {i['photoperiod_h']:g} h implies {implied:.0f} W, more than "
                     f"the {i['load_max_W']:.0f} W maximum draw, so the 450 W column is the binding bound.\n")
    lines.append("\n" + ("Every bound falls below the crop model's range: either the lights run well under "
                         "200 µmol/m²·s, or the stated budget does not include them. The fixtures, their power and the "
                         "canopy PPF are needed (TEAM_INPUTS) before plant gas exchange can be coupled into the CFD."
                         if res["below_mec_range_in_every_bound"] else
                         "At least one bound reaches the crop model's range.") + "\n")
    (OUT / "light_budget.md").write_text("".join(lines))


if __name__ == "__main__":
    r = run()
    write(r)
    print((OUT / "light_budget.md").read_text())
