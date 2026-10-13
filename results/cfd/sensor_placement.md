# Sensor placement — 4 case(s): fpm_m0_coarse_ke_tr, fpm_s2_coarse_ke_tr, fpm_s5a_coarse_ke_tr, fpm_s6_coarse_ke_tr

Ledger bf8f08efaf8171a1. 101 of 184 wall positions are usable: outside equipment in every case and more than the exclusion margin from parts whose gas exchange the CFD does not model (78 dropped near: dutch_bucket_1, dutch_bucket_2, kratky_tub, myco_enclosure, nft_canopy, nft_trough, payload_bioreactor_rack, payload_incubator, payload_photobioreactor, payload_sensor_module, propagation_rack). In these runs CO₂ and H₂O both come only from the crew, so their errors coincide; plant and fungal gas exchange will change the picture near the growing systems. Error = sensor reading minus the occupied-zone volume mean of the same case (T in K; CO₂ and H₂O in % of the occupied-zone excess over supply air); each position's WORST case across the runs is shown. Coarse mesh, placeholder HVAC: a screening ranking, to be confirmed by measurement.

| rank | wall | along the wall (m) | height (m) | worst T err (K) | worst CO₂ err (%) | worst H₂O err (%) | clearance to nearest plant / water / payload part |
|---|---|---|---|---|---|---|---|
| 1 | attic partition | y = 0.75 | 1.2 | 0.27 | 4.9 | 4.9 | 1.56 m (myco_enclosure) |
| 2 | wall y=0 (battery / work side) | x = 10.25 | 1.2 | 0.31 | 6.9 | 6.9 | 1.77 m (myco_enclosure) |
| 3 | wall y=0 (battery / work side) | x = 2.00 | 1.2 | 0.28 | 10.1 | 10.1 | 0.90 m (kratky_tub) |
| 4 | wall y=0 (battery / work side) | x = 10.50 | 1.2 | 0.35 | 6.7 | 6.7 | 1.90 m (myco_enclosure) |
| 5 | attic partition | y = 0.50 | 1.2 | 0.36 | 5.8 | 5.8 | 1.71 m (myco_enclosure) |
| 6 | attic partition | y = 1.75 | 1.2 | 0.37 | 4.6 | 4.6 | 1.29 m (myco_enclosure) |
| 7 | attic partition | y = 0.25 | 1.2 | 0.37 | 5.9 | 5.9 | 1.88 m (myco_enclosure) |
| 8 | wall y=0 (battery / work side) | x = 5.50 | 1.2 | 0.36 | 11.7 | 11.7 | 0.60 m (dutch_bucket_2) |
