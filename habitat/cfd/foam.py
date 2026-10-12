"""OpenFOAM v2606 (pinned Docker image) driver: write dictionaries, run utilities, read logs.

Ported from Hardware_OSDR_review src/hwreview/foam.py @ 97f09f5 (see PORTED_FROM.md). Kept:
  * the environment is activated by sourcing etc/bashrc (never /usr/bin/openfoam2606, which
    execs an interactive shell and silently skips the rest of the script);
  * every utility's exit status is checked AND its log must contain 'End';
  * dictionaries are written whole from Python, never edited in place.
Added here:
  * a host-wide lock so two of our runs never share the VM, and a wait while any OTHER
    container from the same image is running (another session's campaign); overlapping
    campaigns once got a run killed (exit 137) in Hardware_OSDR_review.
"""
from __future__ import annotations

import fcntl
import os
import re
import subprocess
import time
from contextlib import contextmanager
from pathlib import Path

IMAGE = ("opencfd/openfoam-run@sha256:"
         "7ad9ee415db514ecfab39718200049fac21dad4c4385c185595c08237f44929b")  # v2606 arm64, pinned
IMAGE_ID_PREFIX = "7ad9ee415db5"
BASHRC = "/usr/lib/openfoam/openfoam2606/etc/bashrc"
LOCK = Path.home() / ".cache" / "habitat_model_openfoam.lock"


class FoamError(RuntimeError):
    pass


class Raw:
    """Verbatim OpenFOAM text."""

    def __init__(self, text: str, block: bool = False):
        self.text, self.block = text, block


def header(cls: str, obj: str, location: str | None = None) -> str:
    loc = f'    location    "{location}";\n' if location else ""
    return ("FoamFile\n{\n    version     2.0;\n    format      ascii;\n"
            f"    class       {cls};\n{loc}    object      {obj};\n}}\n\n")


def fmt(v, ind: int = 0) -> str:
    pad = "    " * ind
    if isinstance(v, dict):
        out = []
        for k, x in v.items():
            if isinstance(x, dict):
                out.append(f"{pad}{k}\n{pad}{{\n{fmt(x, ind + 1)}{pad}}}\n")
            elif isinstance(x, Raw) and x.block:
                out.append(f"{pad}{k}\n{x.text}\n")
            else:
                out.append(f"{pad}{k} {fmt(x)};\n")
        return "".join(out)
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (list, tuple)):
        return "(" + " ".join(fmt(x) for x in v) + ")"
    if isinstance(v, float):
        return repr(v)
    if isinstance(v, Raw):
        return v.text
    return str(v)


def write(path: Path, cls: str, obj: str, body: dict | str, location: str | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = body if isinstance(body, str) else fmt(body)
    path.write_text(header(cls, obj, location) + text + "\n// ************************************************************************* //\n")


def write_field(case: Path, name: str, dims: str, internal: str, bfs: dict, cls: str = "volScalarField") -> None:
    body = f"dimensions      {dims};\n\ninternalField   {internal};\n\nboundaryField\n{{\n"
    for patch, d in bfs.items():
        body += f"    {patch}\n    {{\n" + fmt(d, 2) + "    }\n"
    body += "}\n"
    write(case / "0" / name, cls, name, body, location="0")


def foreign_containers() -> list[str]:
    """Running containers from the pinned OpenFOAM image that are not ours."""
    r = subprocess.run(["docker", "ps", "--format", "{{.ID}} {{.Image}} {{.Names}}"], capture_output=True, text=True)
    out = []
    for ln in r.stdout.splitlines():
        cid, img, name = (ln.split() + ["", "", ""])[:3]
        if (IMAGE_ID_PREFIX in img or "openfoam" in img) and not name.startswith("habitat_"):
            out.append(ln)
    return out


@contextmanager
def host_lock(wait_foreign_s: float = 6 * 3600, quiet_s: float = 20.0, poll_s: float = 10.0):
    """Exclusive lock among our runs; then wait until no foreign OpenFOAM container has run for quiet_s."""
    LOCK.parent.mkdir(parents=True, exist_ok=True)
    with open(LOCK, "w") as fh:
        fcntl.flock(fh, fcntl.LOCK_EX)
        t0, last_seen = time.time(), None
        while True:
            busy = foreign_containers()
            now = time.time()
            if busy:
                last_seen = now
                print(f"[foam] waiting: another session's OpenFOAM container is running: {busy[0]}", flush=True)
            elif last_seen is None or now - last_seen >= quiet_s:
                break
            if now - t0 > wait_foreign_s:
                raise FoamError("gave up waiting for other OpenFOAM containers to finish")
            time.sleep(poll_s)
        yield


def run(case: Path, steps: list[str], nprocs: int = 1, timeout: float | None = None) -> None:
    """Run utilities in the pinned container (one log per step). 'par:' prefix -> mpirun -np nprocs."""
    case = case.resolve()
    root = case.parent
    with host_lock():
        for step in steps:
            par = step.startswith("par:")
            cmd = step[4:] if par else step
            app = cmd.split()[0]
            tag = re.sub(r"[^A-Za-z0-9_.-]+", "_", cmd)[:60]
            log = f"log.{tag}"
            inner = f"mpirun --oversubscribe -np {nprocs} {cmd} -parallel" if par and nprocs > 1 else cmd
            script = f". {BASHRC} >/dev/null 2>&1; cd /work/{case.name} && {inner} > {log} 2>&1"
            docker = ["docker", "run", "--rm", "--name", f"habitat_{case.name}_{tag}"[:120],
                      "--user", f"{os.getuid()}:{os.getgid()}", "-e", "HOME=/tmp",
                      "-e", "OMPI_MCA_btl_vader_single_copy_mechanism=none",
                      "-v", f"{root}:/work", "--entrypoint", "bash", IMAGE, "-c", script]
            r = subprocess.run(docker, timeout=timeout)
            text = (case / log).read_text(errors="replace") if (case / log).exists() else ""
            needs_end = app not in ("foamToVTK", "decomposePar", "reconstructPar")
            if r.returncode != 0 or "FOAM FATAL" in text or (needs_end and not re.search(r"^End\b", text, re.M)):
                tail = "\n".join(text.splitlines()[-30:])
                raise FoamError(f"{case.name}: '{cmd}' failed (exit {r.returncode})\n{tail}")
