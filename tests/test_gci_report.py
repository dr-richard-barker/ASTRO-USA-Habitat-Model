"""GCI report flags (fixture data in this test only): differences inside the averaging noise and implausible p are
not quoted as a GCI."""
import json

from habitat.report import gci_html


def _gates(tmp, name, dT, dC):
    (tmp / f"{name}_gates.json").write_text(json.dumps(
        {"steady": {"return_T_halves_K": [294.0, 294.0 + dT], "return_dCO2_halves_ppm": [88.0, 88.0 + dC]}}))


def test_flags(tmp_path):
    for m in ("medium", "coarse", "xcoarse"):
        _gates(tmp_path, f"fpm_m0_{m}_tr", 0.03, 0.7)
    gj = {"all_gates_pass": True,
          "meshes": {"medium": {"h_m": 0.057, "cells": 1}, "coarse": {"h_m": 0.08, "cells": 1},
                     "xcoarse": {"h_m": 0.113, "cells": 1}},
          "gci": {"crew_1:dCO2_ppm": {"phi_fine": 100.0, "phi_medium": 104.0, "phi_coarse": 112.0, "p": 1.6,
                                      "gci_fine_pct": 2.5, "convergence": "monotonic"},
                  "domain:T_excess_K": {"phi_fine": 3.00, "phi_medium": 3.01, "phi_coarse": 3.02, "p": 1.0,
                                        "gci_fine_pct": 0.4, "convergence": "monotonic"},
                  "domain:AoA_s": {"phi_fine": 400.0, "phi_medium": 420.0, "phi_coarse": 421.0, "p": 8.0,
                                   "gci_fine_pct": 0.1, "convergence": "monotonic"}}}
    h = gci_html(gj, tmp_path)
    assert "1 of 3 quantities pass" in h
    assert "within sampling noise" in h and "p outside expected range" in h
    assert "<td>2.50</td><td>ok</td>" in h and "(0.40)" in h
