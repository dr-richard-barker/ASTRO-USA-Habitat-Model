# Baseline turbulence-model sensitivity: kOmegaSST (fpm_m0_coarse_tr) vs kEpsilon (fpm_m0_coarse_ke_tr)

Same mesh, loads and averaging; time means. 'model / mesh' = |model difference| divided by the fine-vs-coarse spread of the GCI study (above 1: the model matters more than the mesh). 10 of 19 quantities have model / mesh above 1, but that ratio is unstable where the mesh spread is near zero. In plain terms: room-wide means change by at most 1.9 %, local values by up to 25 % (aisle_x8:dCO2_ppm), air speeds by up to 18 %.

| quantity | kOmegaSST | kEpsilon | difference | % | model / mesh |
|---|---|---|---|---|---|
| domain:T_excess_K | 3.091 | 3.108 | +0.017 | +0.5 | 0.22 |
| domain:AoA_s | 454.7 | 446.1 | -8.58 | -1.9 | 1.97 |
| domain:dCO2_ppm | 89.98 | 91.65 | +1.67 | +1.9 | 0.68 |
| occupied:U_mean_m_s | 0.1134 | 0.1116 | -0.00182 | -1.6 | 0.43 |
| crew_1:dCO2_ppm | 131.4 | 135.1 | +3.7 | +2.8 | 0.23 |
| crew_1:T_excess_K | 3.314 | 3.36 | +0.0461 | +1.4 | 0.19 |
| crew_2:dCO2_ppm | 131.3 | 139.6 | +8.29 | +6.3 | 1.11 |
| crew_2:T_excess_K | 3.632 | 3.704 | +0.0724 | +2.0 | 0.94 |
| nft_canopy:T_excess_K | 3.249 | 3.275 | +0.026 | +0.8 | 0.41 |
| nft_canopy:dH2O_mmol_mol | 0.4138 | 0.4244 | +0.0105 | +2.5 | 1.20 |
| aisle_x2:T_excess_K | 2.883 | 2.919 | +0.0354 | +1.2 | 0.86 |
| aisle_x2:dCO2_ppm | 96.91 | 100.2 | +3.34 | +3.4 | 6.21 |
| aisle_x2:U_m_s | 0.07824 | 0.09224 | +0.014 | +17.9 | 121.00 |
| aisle_x5:T_excess_K | 2.922 | 3.06 | +0.138 | +4.7 | 1.13 |
| aisle_x5:dCO2_ppm | 89.77 | 96.65 | +6.88 | +7.7 | 1.15 |
| aisle_x5:U_m_s | 0.0297 | 0.03486 | +0.00516 | +17.4 | 0.27 |
| aisle_x8:T_excess_K | 3.301 | 3.654 | +0.353 | +10.7 | 1.91 |
| aisle_x8:dCO2_ppm | 101.3 | 126.8 | +25.5 | +25.2 | 1.68 |
| aisle_x8:U_m_s | 0.06809 | 0.064 | -0.00409 | -6.0 | 1.62 |
