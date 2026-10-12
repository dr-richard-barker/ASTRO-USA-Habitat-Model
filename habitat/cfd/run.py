"""Run a built case end to end with an explicit outcome file (waiters must not infer success from silence).

    uv run python -m habitat.cfd.run runs/fpm_m0_coarse --np 4 [--mesh]

Writes <case>/STATUS: 'RUNNING <pid>' at start, then 'DONE' or 'FAILED: <exception>' (traceback in STATUS.log).
"""
from __future__ import annotations

import argparse
import os
import traceback
from pathlib import Path

from .case import mesh_case, solve


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("case")
    ap.add_argument("--np", type=int, default=4)
    ap.add_argument("--mesh", action="store_true")
    a = ap.parse_args(argv)
    case = Path(a.case)
    st = case / "STATUS"
    st.write_text(f"RUNNING {os.getpid()}\n")
    try:
        if a.mesh:
            mesh_case(case)
        solve(case, a.np)
        st.write_text("DONE\n")
    except BaseException as e:   # noqa: BLE001 - record every way out, including KeyboardInterrupt
        (case / "STATUS.log").write_text(traceback.format_exc())
        st.write_text(f"FAILED: {type(e).__name__}: {str(e).splitlines()[0] if str(e) else ''}\n")
        raise


if __name__ == "__main__":
    main()
