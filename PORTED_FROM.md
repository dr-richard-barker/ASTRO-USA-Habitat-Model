# Code ported from other local repositories (copied, never edited at source)

| Here | Source repo | Commit | Source path | Change |
|---|---|---|---|---|
| `habitat/provenance.py` (record schema) | Hardware_OSDR_review (local) | 97f09f5 | `hardware/SCHEMA.md`, `src/hwreview/geometry.py` (Resolver idea) | rewritten as a ledger; added `assumed` kind with `ask_team` |
| `habitat/cfd/foam.py` | Hardware_OSDR_review (local) | 97f09f5 | `src/hwreview/foam.py` | + host lock and wait for other sessions' OpenFOAM containers |
| `habitat/cfd/case.py` (STL writer, snappy/blockMesh set-up, scalar transport pattern) | Hardware_OSDR_review (local) | 97f09f5 | `src/hwreview/cases.py`, `geometry.py` | compressible steady solver, RAS, HVAC loop, scalars relative to supply, shell heat zones |
| `site/theme.css` | Plant_response_to_radiation (shared Pages theme) | 4516d24 | `theme.css` lines 8-76 | tokens + content styles only; navigation rail and brand rules left out |
| `site/site.css`, `site/site.js` (tables, tabs, theme toggle) | Hardware_OSDR_review | 291f806 | `site/site.css`, `site/site.js` | no-rail page pattern; own top bar, viewer loader and pipeline styles |
| `tests/test_site.py` (placeholder and typed-decimal checks) | Hardware_OSDR_review | 291f806 | `tests/test_site.py` | + brand scan of `docs/`, LaTeX-free table cells |
