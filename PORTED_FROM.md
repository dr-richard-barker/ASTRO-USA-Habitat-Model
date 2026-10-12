# Code ported from other local repositories (copied, never edited at source)

| Here | Source repo | Commit | Source path | Change |
|---|---|---|---|---|
| `habitat/provenance.py` (record schema) | Hardware_OSDR_review (local) | 97f09f5 | `hardware/SCHEMA.md`, `src/hwreview/geometry.py` (Resolver idea) | rewritten as a ledger; added `assumed` kind with `ask_team` |
| `habitat/cfd/foam.py` | Hardware_OSDR_review (local) | 97f09f5 | `src/hwreview/foam.py` | + host lock and wait for other sessions' OpenFOAM containers |
| `habitat/cfd/case.py` (STL writer, snappy/blockMesh set-up, scalar transport pattern) | Hardware_OSDR_review (local) | 97f09f5 | `src/hwreview/cases.py`, `geometry.py` | compressible steady solver, RAS, HVAC loop, scalars relative to supply, shell heat zones |
