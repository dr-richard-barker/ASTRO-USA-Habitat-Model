"""Provenance rules: the ledger refuses unsourced or under-documented numbers."""
import pytest
import yaml

from habitat.provenance import Ledger, LedgerError, check_record


def test_real_ledger_loads_and_every_record_is_checked():
    L = Ledger()
    assert len(L.records) > 50
    assert L.assumptions(), "assumptions must be explicit records"
    for r in L.assumptions().values():
        assert r["why"] and isinstance(r["ask_team"], bool)


@pytest.mark.parametrize("rec,msg", [
    ({"value": 1.0, "unit": "m", "kind": "specified", "source": "x"}, "quote"),
    ({"value": 1.0, "unit": "m", "kind": "derived", "source": "x"}, "how"),
    ({"value": 1.0, "unit": "m", "kind": "assumed", "why": "w"}, "ask_team"),
    ({"value": 1.0, "unit": "m", "kind": "guessed"}, "kind"),
    ({"value": 1.0, "kind": "assumed", "why": "w", "ask_team": True}, "unit"),
    ({"value": None, "unit": "m", "kind": "assumed", "why": "w", "ask_team": True}, "null"),
])
def test_incomplete_records_are_refused(rec, msg):
    with pytest.raises(LedgerError, match=msg):
        check_record("t.x", rec)


def test_unknown_path_and_wrong_unit_are_refused(tmp_path):
    f = tmp_path / "a.yaml"
    f.write_text(yaml.safe_dump({"a": {"x": {"value": 2.0, "unit": "in", "kind": "assumed", "why": "w",
                                             "ask_team": False}}}))
    L = Ledger([f])
    assert L.num("a.x", "in") == 2.0
    with pytest.raises(LedgerError):
        L.num("a.x", "mm")
    with pytest.raises(LedgerError):
        L.val("a.y")
    assert "a.x" in L.used


def test_digest_changes_with_any_value(tmp_path):
    f = tmp_path / "a.yaml"
    base = {"a": {"x": {"value": 2.0, "unit": "in", "kind": "assumed", "why": "w", "ask_team": False}}}
    f.write_text(yaml.safe_dump(base)); d1 = Ledger([f]).digest()
    base["a"]["x"]["value"] = 2.5
    f.write_text(yaml.safe_dump(base)); d2 = Ledger([f]).digest()
    assert d1 != d2
