"""The project page quotes only generated numbers and converts the manuscript tables cleanly."""
import re

import pytest

from habitat import ROOT
from habitat.site import _cell, page_values, table_html

TEMPLATE = ROOT / "site" / "index.template.html"
GENERATED = {"TABLE_ANNEX20", "TABLE_RUNS", "TABLE_GCI", "TABLE_SCENARIOS", "TABLE_SENSORS", "TABLE_LEDGER",
             "TABLE_ASSUMPTIONS", "REPO", "GitHead"}


def test_template_placeholders_resolve():
    used = set(re.findall(r"\{\{(\w+)\}\}", TEMPLATE.read_text()))
    assert used <= set(page_values()) | GENERATED, sorted(used - set(page_values()) - GENERATED)


def test_no_hand_typed_result_numbers():
    # decimals in the page text must come from placeholders; the only literals allowed are listed here
    text = re.sub(r"<script.*?</script>|<style.*?</style>", " ", TEMPLATE.read_text(), flags=re.S)
    text = re.sub(r"<[^>]+>|\{\{\w+\}\}", " ", text)
    allowed = {"4.0"}                                         # CC-BY-4.0
    assert not set(re.findall(r"\b\d+\.\d+\b", text)) - allowed


def test_page_has_the_four_sections():
    page = TEMPLATE.read_text()
    for sid in ("habitat", "model", "results", "concepts"):
        assert f'<section id="{sid}">' in page, sid


@pytest.mark.parametrize("tex", sorted((ROOT / "manuscript" / "tables").glob("tab_*.tex")), ids=lambda p: p.name)
def test_tables_convert_without_latex(tex):
    out = table_html(tex)
    assert "<thead>" in out and "\\" not in out and "$" not in out


def test_cell_converter_refuses_unknown_latex():
    assert _cell("$k$--$\\varepsilon$") == "k–ε"
    with pytest.raises(ValueError):
        _cell("\\unknown{x}")
