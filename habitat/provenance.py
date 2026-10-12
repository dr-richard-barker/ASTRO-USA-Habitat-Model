"""The ledger: every number the model uses, each with its provenance.

Record schema (leaf mappings in ledger/*.yaml), extended from Hardware_OSDR_review
hardware/SCHEMA.md (ported from commit 97f09f5, see PORTED_FROM.md):

    value: 464.0            # number, string, or list
    unit:  in               # stated unit; '-' for dimensionless / categorical
    kind:  specified | derived | measured | user_supplied | assumed
    source: "citation"      # required unless kind == assumed
    url:    optional
    quote:  "verbatim text (<= 40 words)"  # required for kind == specified
    how:    "how it was derived"           # required for kind == derived
    date:   YYYY-MM-DD                     # required for user_supplied / measured
    why:    "reason"                       # required for kind == assumed
    ask_team: true|false                   # required for kind == assumed

Code reads values only through Ledger.num()/val(), which logs every use, so each
output can list the exact records (and assumptions) it depends on.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import yaml

from . import LEDGER, ROOT

KINDS = {"specified", "derived", "measured", "user_supplied", "assumed"}
REQUIRED = {
    "specified": ("source", "quote"),
    "derived": ("source", "how"),
    "measured": ("source", "date"),
    "user_supplied": ("source", "date"),
    "assumed": ("why", "ask_team"),
}


class LedgerError(ValueError):
    pass


def _is_record(d) -> bool:
    return isinstance(d, dict) and "value" in d and "kind" in d


def _walk(d, prefix=""):
    if _is_record(d):
        yield prefix, d
    elif isinstance(d, dict):
        for k, v in d.items():
            yield from _walk(v, f"{prefix}.{k}" if prefix else k)
    elif isinstance(d, list):
        for i, v in enumerate(d):
            yield from _walk(v, f"{prefix}[{i}]")


def check_record(path: str, r: dict) -> None:
    kind = r.get("kind")
    if kind not in KINDS:
        raise LedgerError(f"{path}: kind {kind!r} not in {sorted(KINDS)}")
    if "unit" not in r:
        raise LedgerError(f"{path}: missing unit")
    for f in REQUIRED[kind]:
        if r.get(f) in (None, ""):
            raise LedgerError(f"{path}: kind={kind} requires '{f}'")
    if kind == "specified" and len(str(r["quote"]).split()) > 40:
        raise LedgerError(f"{path}: quote longer than 40 words")
    if r["value"] is None:
        raise LedgerError(f"{path}: value is null")


class Ledger:
    """Loads ledger/*.yaml (plus file-backed derived sections) into one checked namespace."""

    def __init__(self, files: list[Path] | None = None):
        files = files or sorted(LEDGER.glob("*.yaml"))
        self.tree: dict = {}
        self.files = [Path(f) for f in files]
        for f in self.files:
            doc = yaml.safe_load(Path(f).read_text()) or {}
            for k, v in doc.items():
                if k in self.tree:
                    raise LedgerError(f"top-level key {k!r} defined twice ({f})")
                self.tree[k] = self._expand(v)
        self.records = dict(_walk(self.tree))
        for p, r in self.records.items():
            check_record(p, r)
        self.used: dict[str, dict] = {}

    # file-backed derived blocks: {from_json: path, source:, how:, select: zones}
    def _expand(self, v):
        if isinstance(v, dict) and "from_json" in v and v.get("mode") == "ports":
            data = json.loads((ROOT / v["from_json"]).read_text())
            out = {}
            for pay, blk in data[v["select"]].items():
                out[pay] = {"envelope_check": {"value": blk["envelope_mm"], "unit": data["units"], "kind": "derived",
                                               "source": blk["source"], "how": "envelope as evaluated alongside the ports"}}
                for q in blk["ports"]:
                    out[pay][q["name"]] = {"value": q, "unit": data["units"], "kind": "derived",
                                          "source": blk["source"], "how": blk["how"]}
            return out
        if isinstance(v, dict) and "from_json" in v:
            data = json.loads((ROOT / v["from_json"]).read_text())
            out = {}
            for i, z in enumerate(data[v["select"]]):
                key = z["label"].lower().replace("™", "").replace("-", "_").replace(" ", "_")
                rec = {"value": z["bbox_in"], "unit": data["units"], "kind": "derived", "source": v["source"],
                       "how": v["how"] + f" (zone colour {z['colour_rgb']})", "label": z["label"]}
                if key in out:          # repeated labels (two Dutch buckets, three dead-space blocks)
                    if not isinstance(out[key], list):
                        out[key] = [out[key]]
                    out[key].append(rec)
                else:
                    out[key] = rec
            return out
        if isinstance(v, dict):
            return {k: self._expand(x) for k, x in v.items()}
        return v

    def rec(self, path: str) -> dict:
        if path not in self.records:
            raise LedgerError(f"no ledger record {path!r}")
        r = self.records[path]
        self.used[path] = r
        return r

    def val(self, path: str):
        return self.rec(path)["value"]

    def num(self, path: str, unit: str | None = None) -> float:
        r = self.rec(path)
        if unit is not None and r["unit"] != unit:
            raise LedgerError(f"{path}: unit is {r['unit']!r}, caller expected {unit!r}")
        if not isinstance(r["value"], (int, float)) or isinstance(r["value"], bool):
            raise LedgerError(f"{path}: value {r['value']!r} is not a number")
        return float(r["value"])

    def assumptions(self) -> dict[str, dict]:
        return {p: r for p, r in self.records.items() if r["kind"] == "assumed"}

    def digest(self) -> str:
        """Content hash of every record: stamped into all outputs so stale results are detectable."""
        blob = json.dumps(self.records, sort_keys=True, default=str).encode()
        return hashlib.sha256(blob).hexdigest()[:16]

    def usage_report(self) -> list[dict]:
        return [{"path": p, "value": r["value"], "unit": r["unit"], "kind": r["kind"],
                 "source": r.get("source") or r.get("why")} for p, r in sorted(self.used.items())]
