# GCI — M0 baseline, time-averaged transient (Celik et al. 2008)

Ladder shifted coarser by decision (57 / 80 / 113 mm); the 'fine' level is the 57 mm mesh.

| Role | Mesh | h (mm) | cells |
|---|---|---|---|
| fine | medium | 48.7 | 547,747 |
| medium | coarse | 62.8 | 255,123 |
| coarse | xcoarse | 84.6 | 103,502 |

| Quantity | 57 mm | 80 mm | 113 mm | p | GCI_fine % | convergence |
|---|---|---|---|---|---|---|
| domain:T_excess_K | 3.119 | 3.091 | 3.052 | 0.51 | 8.23 | monotonic |
| domain:AoA_s | 451.9 | 454.7 | 448.1 | 3.04 | 0.66 | oscillatory |
| domain:dCO2_ppm | 90.32 | 89.98 | 87.99 | 5.73 | 0.14 | monotonic |
| occupied:U_mean_m_s | 0.1082 | 0.1134 | 0.1121 | 6.39 | 1.46 | oscillatory |
| crew_1:dCO2_ppm | 141.9 | 131.4 | 126 | 3.64 | 6.08 | monotonic |
| crew_1:T_excess_K | 3.458 | 3.314 | 3.228 | 2.99 | 4.57 | monotonic |
| crew_2:dCO2_ppm | 144 | 131.3 | 136.6 | 3.95 | 6.34 | oscillatory |
| crew_2:T_excess_K | 3.753 | 3.632 | 3.682 | 3.96 | 2.32 | oscillatory |
| nft_canopy:T_excess_K | 3.274 | 3.249 | 3.219 | 0.03 | 114.39 | monotonic |
| nft_canopy:dH2O_mmol_mol | 0.414 | 0.4138 | 0.4055 | 12.13 | 0.00 | monotonic |
| aisle_x2:T_excess_K | 2.917 | 2.883 | 2.883 | 33.28 | 0.00 | monotonic |
| aisle_x2:dCO2_ppm | 97.22 | 96.91 | 97.76 | 3.49 | 0.28 | oscillatory |
| aisle_x2:U_m_s | 0.08323 | 0.07824 | 0.084 | 0.51 | 53.54 | oscillatory |
| aisle_x5:T_excess_K | 2.964 | 2.922 | 2.856 | 1.08 | 5.56 | monotonic |
| aisle_x5:dCO2_ppm | 91.4 | 89.77 | 85.56 | 2.82 | 2.13 | monotonic |
| aisle_x5:U_m_s | 0.03799 | 0.0297 | 0.01624 | 1.17 | 78.81 | monotonic |
| aisle_x8:T_excess_K | 3.475 | 3.301 | 3.298 | 19.61 | 0.04 | monotonic |
| aisle_x8:dCO2_ppm | 114.5 | 101.3 | 99.31 | 9.17 | 1.54 | monotonic |
| aisle_x8:U_m_s | 0.0596 | 0.06809 | 0.06274 | 2.04 | 26.17 | oscillatory |

All mesh gates pass: True
