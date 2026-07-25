"""Issue #14: cite returns verbatim source text — the Command-spell moment
(2026-07-24 live table) as one command."""
from srdcheck.engine import Engine
from srdcheck.access import default_adapter_paths


def test_cite_command_verbatim():
    v = Engine(default_adapter_paths()).cite("Command")
    assert v.exit_code == 0
    assert v.data["page"] == 116
    assert "Flee." in v.data["text"]
    assert "The target spends its turn moving away" in v.data["text"]


def test_cite_prefixed_heading():
    v = Engine(default_adapter_paths()).cite("Life Domain")   # heading is 'Cleric Subclass: Life Domain'
    assert v.exit_code == 0


def test_cite_unknown_refuses():
    assert Engine(default_adapter_paths()).cite("Hexblade").exit_code == 2
