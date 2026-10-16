"""Project page: site/index.template.html -> docs/index.html (+ docs/assets, docs/viewer).

    uv run python -m habitat.site          (make site)

Every number on the page is a {{Macro}} from the same values the manuscript uses (habitat.manuscript_numbers.values)
plus a few page-only values read here from the ledger and result files; tables are the manuscript's generated
LaTeX tables converted to HTML, so the page and the paper cannot drift. Unknown placeholders, missing values or
LaTeX left in a converted table stop the build.
"""
from __future__ import annotations

import html
import json
import re
import shutil
import subprocess
from pathlib import Path

from . import ROOT
from .manuscript_numbers import values
from .provenance import Ledger

SITE = ROOT / "site"
DOCS = ROOT / "docs"
ASSETS = DOCS / "assets"
FIG = ASSETS / "fig"
REPO = "https://github.com/dr-richard-barker/ASTRO-USA-Habitat-Model"


def _j(p: Path):
    return json.loads(p.read_text()) if p.exists() else None


# ----------------------------------------------------------------------------------------------- values
def page_values() -> dict:
    """Manuscript macros (LaTeX thousands separators made plain) plus page-only values."""
    v = {k: str(x).replace("{,}", ",") for k, x in values().items()}
    L = Ledger()
    v.update({"SolarKW": f"{L.num('fpm.electrical.solar_nominal', 'kW'):g}",
              "NPanels": f"{L.num('fpm.electrical.solar_panels', '-'):.0f}",
              "NBatteries": f"{L.num('fpm.electrical.batteries', '-'):.0f}",
              "DailyEnergy": f"{L.num('fpm.electrical.daily_energy', 'kWh'):g}",
              "MissionCrew": f"{L.num('fpm.mission.crew', '-'):.0f}",
              "PropLevels": f"{L.num('fpm.propagation.levels', '-'):.0f}",
              "NAskTeam": str(sum(1 for r in L.assumptions().values() if r.get("ask_team"))),
              "NHVGuide": f"{L.num('primary.nhv_guideline', 'm3/person'):g}"})
    prim = _j(ROOT / "out" / "vr" / "primary_spec.json")
    if prim:
        m = prim["metrics"]
        v.update({"PrimaryVol": f"{m['internal_pressurised_m3_excl_airlock']:.0f}", "PrimaryCrew": str(m["crew"]),
                  "PrimaryMinFrac": f"{m['min_habitable_fraction_for_guideline']:.2f}"})
    return v


# ----------------------------------------------------------------------------------------------- tables
MATH = [(r"\tau_n", "τ<sub>n</sub>"), (r"\langle", "⟨"), (r"\rangle", "⟩"), (r"\times", "×"), (r"\varepsilon", "ε"),
        (r"\omega", "ω"), (r"\Delta", "Δ"), (r"\tau", "τ"), ("^{-1}", "⁻¹")]


def _cell(tex: str) -> str:
    s = html.escape(tex.strip(), quote=False)
    s = s.replace("{,}", ",").replace(r"\%", "%").replace(r"\,", "\u2009").replace(r"\ ", " ")
    s = re.sub(r"\\textsubscript\{(.*?)\}", r"<sub>\1</sub>", s)
    s = re.sub(r"\\texttt\{(.*?)\}", lambda m: "<code>" + m.group(1).replace(r"\_", "_") + "</code>", s)

    def math(m):
        t = m.group(1)
        for a, b in MATH:
            t = t.replace(a, b)
        return t.replace(" ", "")
    s = re.sub(r"\$(.*?)\$", math, s)
    s = s.replace("--", "–")
    if "\\" in s or "$" in s:
        raise ValueError(f"LaTeX left in table cell: {tex!r} -> {s!r}")
    return s


NUM = re.compile(r"^[−\-+]?[\d,.]+( \(×[\d.]+\))?$|^[\d.]+–[\d.]+$|^–$")


def table_html(tex_file: Path, caption: str = "", tall: bool = False) -> str:
    """A generated booktabs tabular (manuscript/tables/*.tex) as an HTML table."""
    lines = [ln.strip() for ln in tex_file.read_text().splitlines()
             if ln.strip() and not ln.startswith("%") and not ln.strip().startswith(("\\begin{tabular", "\\end{tabular"))]
    head, body, part, rule = [], [], "pre", False
    for ln in lines:
        if ln == r"\toprule":
            part = "head"; continue
        if ln == r"\midrule":
            if part == "head":
                part = "body"
            else:
                rule = True
            continue
        if ln == r"\bottomrule":
            break
        cells = [_cell(c) for c in ln.rstrip("\\").rstrip().removesuffix("\\\\").split(" & ")]
        if part == "head" and not head:
            head = cells
        else:
            body.append((cells, rule)); rule = False
    if not head:
        raise ValueError(f"{tex_file.name}: no header row")

    def td(c, i, tag="td"):
        cls = ' class="num"' if i and NUM.match(re.sub("<[^>]+>", "", c)) else ""
        return f"<{tag}{cls}>{c}</{tag}>"
    out = [f'<div class="tbl{" tall" if tall else ""}"><table>']
    if caption:
        out.append(f"<caption>{caption}</caption>")
    out.append("<thead><tr>" + "".join(td(c, i, "th") for i, c in enumerate(head)) + "</tr></thead><tbody>")
    for cells, r in body:
        cls = ' class="rule"' if r else ""
        out.append(f"<tr{cls}>" + "".join(td(c, i) for i, c in enumerate(cells)) + "</tr>")
    out.append("</tbody></table></div>")
    return "".join(out)


def assumptions_html() -> str:
    L = Ledger()
    rows = "".join(f"<tr><td><code>{html.escape(p)}</code></td><td>{html.escape(str(r['value']))[:70]}</td>"
                   f"<td>{html.escape(str(r['unit']))}</td><td>{'yes' if r.get('ask_team') else ''}</td>"
                   f"<td>{html.escape(r['why'])}</td></tr>" for p, r in sorted(L.assumptions().items()))
    return ('<div class="tbl tall"><table><thead><tr><th>Ledger record</th><th>Value</th><th>Unit</th><th>Ask team</th>'
            f"<th>Why this value</th></tr></thead><tbody>{rows}</tbody></table></div>")


# ----------------------------------------------------------------------------------------------- assets
def _copy(src: Path, dst: Path) -> bool:
    if not src.exists():
        return dst.exists()                      # keep a committed copy when the source is a local build product
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(src, dst)
    return True


def stage_assets() -> None:
    import pymupdf
    FIG.mkdir(parents=True, exist_ok=True)
    for f in ("theme.css", "site.css", "site.js"):
        _copy(SITE / f, ASSETS / f)
    for pdf in sorted((ROOT / "manuscript" / "figures").glob("fig_*.pdf")):
        pix = pymupdf.open(pdf)[0].get_pixmap(dpi=220 if pdf.name == "fig_drawing.pdf" else 170)
        pix.save(FIG / (pdf.stem + ".png"))
    _copy(ROOT / "manuscript" / "figures" / "fig_render.jpg", FIG / "fig_render.jpg")
    for name in ("render_lod0_aisle_from_door.png", "render_lod0_payload_bay.png", "render_lod0_site_overview.png",
                 "render_lod0_primary_overview.png"):
        _copy(ROOT / "out" / "vr" / name, ASSETS / name)
    dwg = ROOT / "results" / "drawings"
    for f in ["FPM_GA.svg", "FPM_GA.pdf", "FPM_sections.svg"] + [p.name for p in sorted(dwg.glob("FPM_*.dxf"))]:
        _copy(dwg / f, ASSETS / f)
    if (DOCS / "viewer").exists():
        shutil.rmtree(DOCS / "viewer")
    shutil.copytree(ROOT / "vr" / "web", DOCS / "viewer")
    (DOCS / ".nojekyll").write_text("")


# ----------------------------------------------------------------------------------------------- page
def build() -> Path:
    stage_assets()
    v = page_values()
    t = ROOT / "manuscript" / "tables"
    v.update({"TABLE_ANNEX20": table_html(t / "tab_annex20.tex"), "TABLE_RUNS": table_html(t / "tab_runs.tex"),
              "TABLE_GCI": table_html(t / "tab_gci.tex", tall=True), "TABLE_SCENARIOS": table_html(t / "tab_scenarios.tex"),
              "TABLE_SENSORS": table_html(t / "tab_sensors.tex"), "TABLE_LEDGER": table_html(t / "tab_ledger.tex", tall=True),
              "TABLE_ASSUMPTIONS": assumptions_html(), "REPO": REPO,
              "GitHead": subprocess.run(["git", "-C", str(ROOT), "rev-parse", "--short", "HEAD"],
                                        capture_output=True, text=True).stdout.strip()})
    src = (SITE / "index.template.html").read_text()
    used = set(re.findall(r"\{\{(\w+)\}\}", src))
    missing = sorted(k for k in used if k not in v or v[k] in ("", None) or "todo" in str(v[k]))
    if missing:
        raise KeyError(f"page placeholders without a value: {missing}")
    page = re.sub(r"\{\{(\w+)\}\}", lambda m: str(v[m.group(1)]), src)
    page = page.replace("<!-- TEMPLATE -->", "<!-- generated by habitat/site.py from site/index.template.html; do not edit -->")
    (DOCS / "index.html").write_text(page)
    print(f"wrote {DOCS / 'index.html'} ({len(used)} placeholders)")
    return DOCS / "index.html"


if __name__ == "__main__":
    build()
