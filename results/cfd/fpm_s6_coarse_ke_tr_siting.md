# S6 payload siting — fpm_s6_coarse_ke_tr (ledger 53413134410685ff)
Same bioreactor CO₂ release in every route: 10 tubes × 1.82 g/day. The photobioreactor can take 5 units' off-gas (sparger max flow); the rest vent in the bay.
Well-mixed (return-grille) excess: bay 0.811 ppm, photobioreactor 0.808 ppm, nft_wall 0.806 ppm.

| Location | bay ppm (×mixed) | photobioreactor ppm (×mixed) | nft_wall ppm (×mixed) | crew-generated ΔCO₂ ppm |
|---|---|---|---|---|
| zone:nft_canopy | 0.390 (×0.48) | 0.467 (×0.58) | 1.141 (×1.42) | 86.1 |
| zone:crew_1 | 0.389 (×0.48) | 0.466 (×0.58) | 0.789 (×0.98) | 126.7 |
| zone:crew_2 | 0.768 (×0.95) | 1.168 (×1.44) | 0.759 (×0.94) | 119.1 |
| zone:workbench_zone | 0.696 (×0.86) | 0.728 (×0.90) | 0.758 (×0.94) | 85.0 |
| probe:crew_1_head | 0.390 (×0.48) | 0.467 (×0.58) | 0.945 (×1.17) | 150.1 |
| probe:crew_2_head | 0.301 (×0.37) | 0.359 (×0.44) | 0.462 (×0.57) | 53.7 |
| probe:incubator_intake_fan | 0.411 (×0.51) | 0.518 (×0.64) | 0.871 (×1.08) | 80.4 |
| probe:sensor_module_sample_in | 0.505 (×0.62) | 0.548 (×0.68) | 0.875 (×1.09) | 81.4 |
| probe:nft_canopy_0 | 0.395 (×0.49) | 0.472 (×0.58) | 1.157 (×1.44) | 82.8 |
| probe:nft_canopy_1 | 0.388 (×0.48) | 0.464 (×0.57) | 1.190 (×1.48) | 88.2 |
| probe:nft_canopy_2 | 0.387 (×0.48) | 0.463 (×0.57) | 1.110 (×1.38) | 93.5 |
| probe:bay_centre | 0.441 (×0.54) | 0.601 (×0.74) | 0.768 (×0.95) | 85.1 |

Gates: balance_bay PASS, balance_photobioreactor PASS, balance_nft_wall PASS, general_mass PASS, general_heat_removed_W PASS, general_co2_removed_mol_s PASS, general_h2o_removed_mol_s PASS, general_age_return_s PASS, general_steady PASS
