"""Extract the Food Production Module floor plan from ICES-2026-251, page 8 (Figures 2 and 3).

(main() raises AssertionError on any failed check; tests/test_fig2.py exercises the failure paths.)

Figure 2 (dimensioned plan) and Figure 3 (labelled layout) are vector drawings in the PDF.
This script reads the zone rectangles directly from the PDF drawing operators, so no value
is traced by eye:

  1. scale  - the container outline (Fig 2) must measure 464.00 in x 92.00 in (the paper's
              stated footprint); the in/pt factor is calibrated on it and both axes must
              agree to within 0.1 %;
  2. labels - each Figure 3 label is followed along its leader line to the zone its arrow
              points into, giving colour -> label from the drawing itself (labels written
              inside a zone are matched by containment);
  3. checks - every dimension string printed on Figure 2 is matched to a measured extent
              of the extracted geometry (within 0.25 in); an unmatched dimension fails.

Coordinates: inches, origin at the top-left inside corner of Figure 2 as printed;
x along the 464 in length (left -> right), y across the 92 in width (top wall -> bottom wall).

Usage:  python -I sources/extract_fig2.py sources/private/ICES-2026-251.pdf sources/fig2_geometry.json
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pymupdf

PAGE = 7                    # 0-based index of PDF page 8
FIG2_Y = (85.0, 215.0)      # page-space band (pt) holding Figure 2
FIG3_Y = (250.0, 400.0)     # page-space band (pt) holding Figure 3
OUTLINE_COLOUR = (0.45, 0.0, 0.0)
FOOTPRINT_IN = (464.0, 92.0)     # ICES-2026-251 Section V: "measures 464 in x 92 in"
DIM_TOL_IN = 0.25


def _col(c):
    return tuple(round(v, 2) for v in c) if c else None


def _quads(drawings, yband):
    """Closed rectangles ('qu' path items) inside a vertical band, with their stroke colour."""
    out = []
    for d in drawings:
        r = d["rect"]
        if not (yband[0] <= r.y0 <= yband[1]):
            continue
        for it in d["items"]:
            if it[0] == "qu":
                q = it[1].rect
                out.append({"colour": _col(d.get("color")), "x0": q.x0, "y0": q.y0, "x1": q.x1, "y1": q.y1})
    return out


def main(pdf: str, out: str) -> dict:
    page = pymupdf.open(pdf)[PAGE]
    drawings = page.get_drawings()
    words = page.get_text("words")

    # ---- 1. scale from the container outline
    q2 = _quads(drawings, FIG2_Y)
    outline = [q for q in q2 if q["colour"] == OUTLINE_COLOUR]
    assert len(outline) == 1, f"expected one container outline in Fig 2, found {len(outline)}"
    o = outline[0]
    sx = FOOTPRINT_IN[0] / (o["x1"] - o["x0"])
    sy = FOOTPRINT_IN[1] / (o["y1"] - o["y0"])
    assert abs(sx - sy) / sx < 1e-3, f"x/y scales disagree: {sx} vs {sy}"
    s = (sx + sy) / 2

    def to_in(q):
        return [round((q["x0"] - o["x0"]) * s, 2), round((q["y0"] - o["y0"]) * s, 2),
                round((q["x1"] - o["x0"]) * s, 2), round((q["y1"] - o["y0"]) * s, 2)]

    # attic partition: the outline-coloured 2-segment path inside the outline
    attic = [d for d in drawings if FIG2_Y[0] <= d["rect"].y0 <= FIG2_Y[1] and _col(d.get("color")) == OUTLINE_COLOUR
             and all(it[0] == "l" for it in d["items"])]
    assert len(attic) == 1, "expected one attic partition path"
    ar = attic[0]["rect"]
    attic_in = [round((ar.x0 - o["x0"]) * s, 2), 0.0, round((ar.x1 - o["x0"]) * s, 2), FOOTPRINT_IN[1]]

    # ---- 2. colour -> label from Figure 3 leaders
    q3 = _quads(drawings, FIG3_Y)
    heads = [d for d in drawings if FIG3_Y[0] <= d["rect"].y0 <= FIG3_Y[1] and d.get("color") is None
             and len(d["items"]) == 3]                       # filled arrowheads
    leaders = [d for d in drawings if FIG3_Y[0] <= d["rect"].y0 <= FIG3_Y[1] and _col(d.get("color")) == (0, 0, 0)
               and len(d["items"]) == 2]
    fig3_words = [w for w in words if FIG3_Y[0] <= w[1] <= FIG3_Y[1] + 60]
    # group words into label phrases by line
    phrases = []
    for w in sorted(fig3_words, key=lambda w: (round(w[1]), w[0])):
        if phrases and abs(phrases[-1]["y"] - w[1]) < 2 and w[0] - phrases[-1]["x1"] < 6:
            phrases[-1]["text"] += " " + w[4]
            phrases[-1]["x1"] = w[2]
        else:
            phrases.append({"text": w[4], "x0": w[0], "x1": w[2], "y": w[1], "y1": w[3]})
    phrases = [p for p in phrases if p["text"] not in ("Figure", "3.") and len(p["text"]) > 3
               and p["y"] < FIG3_Y[1] + 60]

    def innermost(px, py):
        hits = [q for q in q3 if q["x0"] - 0.5 <= px <= q["x1"] + 0.5 and q["y0"] - 0.5 <= py <= q["y1"] + 0.5
                and q["colour"] != OUTLINE_COLOUR]
        return min(hits, key=lambda q: (q["x1"] - q["x0"]) * (q["y1"] - q["y0"])) if hits else None

    colour_label: dict = {}
    for h in heads:
        hr = h["rect"]
        tip = ((hr.x0 + hr.x1) / 2, (hr.y0 + hr.y1) / 2)
        # leader whose end touches this arrowhead
        best = None
        for L in leaders:
            lr = L["rect"]
            for end in ((lr.x0, lr.y0), (lr.x1, lr.y1)):
                dist = abs(end[0] - tip[0]) + abs(end[1] - tip[1])
                if dist < 6 and (best is None or dist < best[0]):
                    best = (dist, L)
        if best is None:
            continue
        lr = best[1]["rect"]
        far = (lr.x0, lr.y0) if abs(lr.x0 - tip[0]) + abs(lr.y0 - tip[1]) > abs(lr.x1 - tip[0]) + abs(lr.y1 - tip[1]) \
            else (lr.x1, lr.y1)
        lab = min(phrases, key=lambda p: min(abs(far[0] - p["x0"]), abs(far[0] - p["x1"]),
                                             abs(far[0] - (p["x0"] + p["x1"]) / 2)) + abs(far[1] - p["y"]) * 0.5)
        if tip[0] > max(q["x1"] for q in q3 if q["colour"] != OUTLINE_COLOUR) - 1:   # arrow into the attic
            colour_label.setdefault(OUTLINE_COLOUR, lab["text"])
            continue
        z = innermost(*tip)
        if z is not None:
            colour_label.setdefault(z["colour"], lab["text"])
    for p in phrases:                                            # labels written inside a zone
        z = innermost((p["x0"] + p["x1"]) / 2, (p["y"] + p["y1"]) / 2)
        if z is not None and z["colour"] not in colour_label:
            colour_label[z["colour"]] = p["text"]

    # ---- zones in inches
    zones = []
    for q in q2:
        if q["colour"] == OUTLINE_COLOUR:
            continue
        zones.append({"label": colour_label.get(q["colour"], "UNLABELLED"), "colour_rgb": q["colour"],
                      "bbox_in": to_in(q)})
    zones.append({"label": colour_label.get(OUTLINE_COLOUR, "Attic"), "colour_rgb": OUTLINE_COLOUR,
                  "bbox_in": attic_in})
    unl = [z for z in zones if z["label"] == "UNLABELLED"]
    assert not unl, f"zones without a Figure 3 label: {unl}"

    # ---- 3a. every printed dimension must equal ITS OWN dimension line.
    # A dimension path is black, 4-5 straight segments; its first two segments are the extension
    # lines, so the measured span is the distance between them. Each label is paired with the
    # dimension path whose dimension-line segments (items 2..) pass closest to the label centre.
    dimpaths = []
    for d in drawings:
        r = d["rect"]
        if not (FIG2_Y[0] <= r.y0 <= FIG2_Y[1]) or _col(d.get("color")) != (0, 0, 0):
            continue
        it = d["items"]
        if not (4 <= len(it) <= 5 and all(x[0] == "l" for x in it)):
            continue
        (a0, a1), (b0, b1) = (it[0][1], it[0][2]), (it[1][1], it[1][2])
        segs = [(x[1], x[2]) for x in it[2:]]
        if abs(a0.x - a1.x) < 1e-3 and abs(b0.x - b1.x) < 1e-3:          # vertical extension lines
            axis, lo, hi = 0, min(a0.x, b0.x), max(a0.x, b0.x)
            perp = segs[0][0].y                                         # y of the dimension line
        elif abs(a0.y - a1.y) < 1e-3 and abs(b0.y - b1.y) < 1e-3:        # horizontal extension lines
            axis, lo, hi = 1, min(a0.y, b0.y), max(a0.y, b0.y)
            perp = segs[0][0].x                                         # x of the dimension line
        else:
            continue
        dimpaths.append({"span_in": (hi - lo) * s, "segs": segs, "axis": axis, "lo": lo, "hi": hi, "perp": perp})

    def seg_dist(p, a, b):
        ax, ay, bx, by = a.x, a.y, b.x, b.y
        L2 = (bx - ax) ** 2 + (by - ay) ** 2
        t = 0.0 if L2 == 0 else max(0.0, min(1.0, ((p[0] - ax) * (bx - ax) + (p[1] - ay) * (by - ay)) / L2))
        return ((p[0] - ax - t * (bx - ax)) ** 2 + (p[1] - ay - t * (by - ay)) ** 2) ** 0.5

    dims = []
    used = set()
    for w in words:
        if FIG2_Y[0] <= w[1] <= FIG2_Y[1] and w[4].endswith('"'):
            v = float(w[4].rstrip('"'))
            c = ((w[0] + w[2]) / 2, (w[1] + w[3]) / 2)
            # a label printed between its arrows lies inside the span, next to the dimension line
            inside = [j for j, p in enumerate(dimpaths)
                      if p["lo"] <= c[p["axis"]] <= p["hi"] and abs(c[1 - p["axis"]] - p["perp"]) < 12]
            pool = inside or range(len(dimpaths))      # labels printed outside the arrows: nearest line
            k = min(pool, key=lambda j: min(seg_dist(c, a, b) for a, b in dimpaths[j]["segs"]))
            used.add(k)
            meas = round(dimpaths[k]["span_in"], 3)
            dims.append({"printed_in": v, "dimension_line_in": meas, "error_in": round(meas - v, 3),
                         "ok": abs(meas - v) <= DIM_TOL_IN, "page_xy_pt": [round(w[0], 1), round(w[1], 1)]})
    bad = [d for d in dims if not d["ok"]]
    assert not bad, f"printed dimensions disagree with their own dimension lines: {bad}"
    assert len(used) == len(dims), "two labels were paired with the same dimension line"

    # ---- 3b. ...and every dimensioned span must exist as an edge-to-edge extent of the zones
    xs = sorted({v for z in zones for v in (z["bbox_in"][0], z["bbox_in"][2])} | {0.0, FOOTPRINT_IN[0]})
    ys = sorted({v for z in zones for v in (z["bbox_in"][1], z["bbox_in"][3])} | {0.0, FOOTPRINT_IN[1]})
    extents = {round(b - a, 2) for L in (xs, ys) for i, a in enumerate(L) for b in L[i + 1:]}
    for d in dims:
        d["zone_extent_in"] = min(extents, key=lambda e: abs(e - d["dimension_line_in"]))
        assert abs(d["zone_extent_in"] - d["dimension_line_in"]) <= DIM_TOL_IN, f"no zone edges span {d}"

    result = {
        "source": "ICES-2026-251 (55th ICES, 2026), PDF page 8, Figure 2 (dimensioned plan) + Figure 3 (labels)",
        "method": "vector extraction with PyMuPDF get_drawings(); see sources/extract_fig2.py",
        "pymupdf_version": pymupdf.VersionBind,
        "units": "in",
        "frame": "origin = top-left inside corner of Figure 2 as printed; +x along length, +y toward the "
                 "bottom wall of the printed plan",
        "scale_in_per_pt": {"x": sx, "y": sy, "used": s},
        "footprint_in": list(FOOTPRINT_IN),
        "colour_labels": {str(k): v for k, v in colour_label.items()},
        "zones": sorted(zones, key=lambda z: (z["bbox_in"][1], z["bbox_in"][0])),
        "dimension_check": sorted(dims, key=lambda d: d["page_xy_pt"]),
        "max_dimension_error_in": max(abs(d["error_in"]) for d in dims),
    }
    Path(out).write_text(json.dumps(result, indent=1) + "\n")
    return result


if __name__ == "__main__":
    r = main(sys.argv[1], sys.argv[2])
    for z in r["zones"]:
        print(f"{z['label']:22s} {z['bbox_in']}")
    print(f"{len(r['dimension_check'])} printed dimensions matched; max error {r['max_dimension_error_in']} in")
