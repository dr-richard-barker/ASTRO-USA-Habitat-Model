# GCI — M0 baseline, time-averaged transient (Celik et al. 2008)

Ladder shifted coarser by decision (57 / 80 / 113 mm); the 'fine' level is the 57 mm mesh.

| Role | Mesh | h (mm) | cells |
|---|---|---|---|
| fine | medium | 48.7 | 547,747 |
| medium | coarse | 62.8 | 255,123 |
| coarse | xcoarse | 84.6 | 103,502 |

| Quantity | 57 mm | 80 mm | 113 mm | p | GCI_fine % | convergence |
|---|---|---|---|---|---|---|
| domain:T_excess_K | 3.119 | 3.091 | 3.043 | 1.29 | 2.94 | monotonic |
| domain:AoA_s | 451.9 | 454.7 | 447.6 | 3.30 | 0.58 | oscillatory |
| domain:dCO2_ppm | 90.32 | 89.98 | 87.87 | 5.93 | 0.13 | monotonic |
| occupied:U_mean_m_s | 0.1082 | 0.1134 | 0.1125 | 8.07 | 0.87 | oscillatory |
| crew_1:dCO2_ppm | 141.9 | 131.4 | 125.6 | 3.33 | 6.98 | monotonic |
| crew_1:T_excess_K | 3.458 | 3.314 | 3.215 | 2.32 | 6.46 | monotonic |
| crew_2:dCO2_ppm | 144 | 131.3 | 136.5 | 4.01 | 6.19 | oscillatory |
| crew_2:T_excess_K | 3.753 | 3.632 | 3.676 | 4.60 | 1.81 | oscillatory |
| nft_canopy:T_excess_K | 3.274 | 3.249 | 3.211 | 0.89 | 3.79 | monotonic |
| nft_canopy:dH2O_mmol_mol | 0.414 | 0.4138 | 0.4052 | 12.25 | 0.00 | monotonic |
| aisle_x2:T_excess_K | 2.917 | 2.883 | 2.876 | 7.30 | 0.27 | monotonic |
| aisle_x2:dCO2_ppm | 97.22 | 96.91 | 97.76 | 3.49 | 0.28 | oscillatory |
| aisle_x2:U_m_s | 0.08323 | 0.07824 | 0.08311 | 0.10 | 288.01 | oscillatory |
| aisle_x5:T_excess_K | 2.964 | 2.922 | 2.842 | 1.78 | 3.07 | monotonic |
| aisle_x5:dCO2_ppm | 91.4 | 89.77 | 85.42 | 2.93 | 2.01 | monotonic |
| aisle_x5:U_m_s | 0.03799 | 0.0297 | 0.01898 | 0.35 | 291.92 | monotonic |
| aisle_x8:T_excess_K | 3.475 | 3.301 | 3.29 | 13.05 | 0.23 | monotonic |
| aisle_x8:dCO2_ppm | 114.5 | 101.3 | 99.32 | 9.20 | 1.53 | monotonic |
| aisle_x8:U_m_s | 0.0596 | 0.06809 | 0.06213 | 1.55 | 36.72 | oscillatory |

All mesh gates pass: True
