# Light budget of the NFT wall (ledger 9a0d9688950c7bc2)

If the FPM's stated budget (450 W maximum steady draw, ~8 kWh/day) includes the grow lights, how much light can reach 297 lettuce sites? Every watt is given to light at the best LED fixture efficacy achieved by 2020 (3 µmol/J), over BVAD's nominal 16 h photoperiod. BVAD's lettuce crop model is valid for 200–500 µmol/m²·s. (Physical ceiling for photosynthetic photons: 5.852 µmol/J at 700 nm.)

| lit area | m² | max PPF, all 450 W to light | mean PPF, all daily energy to light | power for 200 µmol/m²·s | energy/day for 200 µmol/m²·s |
|---|---|---|---|---|---|
| NFT wall face (model geometry) | 9.33 | 144.7 | 160.8 | 622 W | 9.95 kWh |
| 297 plants at BVAD density | 15.47 | 87.3 | 97.0 | 1031 W | 16.5 kWh |

Spreading 8 kWh over 16 h implies 500 W, more than the 450 W maximum draw, so the 450 W column is the binding bound.

Every bound falls below the crop model's range: either the lights run well under 200 µmol/m²·s, or the stated budget does not include them. The fixtures, their power and the canopy PPF are needed (TEAM_INPUTS) before plant gas exchange can be coupled into the CFD.
