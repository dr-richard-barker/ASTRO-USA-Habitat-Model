"""No dimension may be typed into model-building code: numbers come from the ledger."""
import ast
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
CHECKED = ["habitat/registry.py"]
ALLOWED = {0, 1, 2, 0.0, 1.0, 2.0}


def numeric_literals(src: str):
    tree = ast.parse(src)
    in_subscript = {id(n) for sub in ast.walk(tree) if isinstance(sub, ast.Subscript) for n in ast.walk(sub.slice)}
    for node in ast.walk(tree):
        if id(node) in in_subscript:          # indices / slices (bbox[3], digest[:12]) are not dimensions
            continue
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
            if node.value not in ALLOWED:
                yield node.lineno, node.value


@pytest.mark.parametrize("path", CHECKED)
def test_no_typed_dimensions(path):
    bad = list(numeric_literals((ROOT / path).read_text()))
    assert not bad, f"{path}: numeric literals {bad} — put the value in the ledger"


def test_lint_catches_a_typed_dimension():
    assert list(numeric_literals("h = 2438.0\n")) == [(1, 2438.0)]
    assert list(numeric_literals("h = box[3] * 2438.0\n")) == [(1, 2438.0)]
    assert list(numeric_literals("h = box[3]\n")) == []
