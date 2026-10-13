# Validation: IEA Annex 20 2-D test case (ledger 7b81bee4fd92284e)

Re = 4996, u0 = 0.455 m/s; kOmegaSST (as in the habitat runs) and standard k-epsilon, wall functions, the habitat cases' schemes. Data: Aalborg University CFD benchmark, IEA Annex 20 2-D test case, laser-Doppler measurements (Re = 5000), https://www.aaudxp-cms.aau.dk/media/udffy5eg/592302_2d_-benchmark_test_measurements_new.xls. Error = simulated minus measured mean u/u0 at the measured points. Isothermal case only: the report's buoyant case (2D2) has no measurements for this geometry ("experiments for h/H = 0.056 and Re = 5000 are missing", Nielsen 1990 p. 4).

| mesh | cells | iterations | largest final residual | x=H rms (max) | x=2H rms (max) | ceiling h/2 rms (max) | floor h/2 rms (max) |
|---|---|---|---|---|---|---|---|
| kOmegaSST 80 mm | 4,144 | 1402 | 1.4e-06 | 0.105 (0.170) | 0.095 (0.255) | 0.168 (0.465) | 0.181 (0.340) |
| kOmegaSST 40 mm | 16,875 | 6000 | 1.4e-06 | 0.145 (0.214) | 0.067 (0.116) | 0.179 (0.498) | 0.162 (0.334) |
| kOmegaSST 20 mm | 67,500 | 6000 | 3.2e-05 | 0.136 (0.199) | 0.083 (0.269) | 0.180 (0.506) | 0.161 (0.349) |
| kEpsilon 80 mm | 4,144 | 1276 | 1.0e-06 | 0.061 (0.107) | 0.038 (0.074) | 0.124 (0.302) | 0.074 (0.188) |
| kEpsilon 40 mm | 16,875 | 3801 | 1.0e-06 | 0.065 (0.131) | 0.037 (0.076) | 0.068 (0.157) | 0.072 (0.178) |
| kEpsilon 20 mm | 67,500 | 6000 | 2.7e-05 | 0.068 (0.141) | 0.036 (0.075) | 0.063 (0.186) | 0.062 (0.173) |
