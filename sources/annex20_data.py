"""Convert the Aalborg University LDA spreadsheet for the IEA Annex 20 2-D test case into sources/annex20_lda.json.

    uv run --with xlrd python -I sources/annex20_data.py <path to 592302_2d_-benchmark_test_measurements_new.xls>

Source: https://en.build.aau.dk/web/cfd-benchmarks/two-dimensional-benchmark-test ("592302 2D Benchmark Test
Measurements New"; file metadata: "Laser-doppler measurements of the two dimensional test case", author Arnkell Jonas
Petersen, last saved by Peter V. Nielsen 2006). Only the mean velocities are carried over; RMS values are kept too.
The sheet's y co-ordinate points down from the ceiling (report Figure 1); its column header 'y=x/H' on the vertical
lines is the sheet's own label for y/H.
"""
import hashlib
import json
import sys
from pathlib import Path

import xlrd

URL = "https://www.aaudxp-cms.aau.dk/media/udffy5eg/592302_2d_-benchmark_test_measurements_new.xls"


def block(sh, r0, c0, stop):
    xs, mean, rms = [], [], []
    r = r0
    while r < stop and isinstance(sh.cell_value(r, c0), float):
        xs.append(sh.cell_value(r, c0)); mean.append(sh.cell_value(r, c0 + 1)); rms.append(sh.cell_value(r, c0 + 2))
        r += 1
    return xs, mean, rms


def main(xls: Path) -> dict:
    sh = xlrd.open_workbook(str(xls)).sheet_by_index(0)
    assert "x=H" in str(sh.cell_value(8, 1)) and "x=2H" in str(sh.cell_value(8, 5)), "sheet layout changed"
    assert str(sh.cell_value(39, 1)) == "y=h/2" and str(sh.cell_value(39, 5)) == "y=H-h/2", "sheet layout changed"
    prof = {}
    for key, r0, c0, coord, stop in (("x=H", 11, 1, "y_over_H", 37), ("x=2H", 11, 5, "y_over_H", 37),
                                     ("ceiling h/2", 42, 1, "x_over_H", 80), ("floor h/2", 42, 5, "x_over_H", 80)):
        xs, m, rr = block(sh, r0, c0, min(stop, sh.nrows))
        prof[key] = {coord: xs, "mean": m, "rms": rr}
    return {"source": "Aalborg University CFD benchmark, IEA Annex 20 2-D test case, laser-Doppler measurements "
                      f"(Re = 5000), {URL}",
            "sha256_16": hashlib.sha256(xls.read_bytes()).hexdigest()[:16],
            "frame": "y measured down from the ceiling (report Figure 1); x from the inlet wall; velocities u/u0",
            "line_labels": {"ceiling h/2": "sheet 'y=h/2' (h/2 below the ceiling: the wall-jet line)",
                            "floor h/2": "sheet 'y=H-h/2' (h/2 above the floor)"},
            "profiles": prof}


if __name__ == "__main__":
    d = main(Path(sys.argv[1]))
    out = Path(__file__).resolve().parent / "annex20_lda.json"
    out.write_text(json.dumps(d, indent=1) + "\n")
    print({k: len(v["mean"]) for k, v in d["profiles"].items()}, d["sha256_16"])
