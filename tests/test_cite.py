"""Issue #14: cite returns verbatim source text — the Command-spell moment
(2026-07-24 live table) as one command."""
import json

import pytest

from srdcheck import cli
from srdcheck.engine import Engine, NON_EMPTY_NAME_INPUT_SCHEMA
from srdcheck.access import default_adapter_paths
from srdcheck.schema import issues as schema_issues


E = Engine(default_adapter_paths())


def _assert_invalid_name(verdict):
    assert verdict.exit_code == 2
    assert verdict.data["reason_code"] == "invalid-input"
    assert verdict.data["recoverability"] == "retry"
    assert verdict.data["suggested_next_action"] == "repair-request"
    assert verdict.data["missing_inputs"] == []


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
    verdict = E.cite("Hexblade")
    assert verdict.exit_code == 2
    assert verdict.data["reason_code"] == "unsupported-content"
    assert verdict.data["suggested_next_action"] == "select-adapter"


@pytest.mark.parametrize("name", ["", " ", "\t\n", None, 7, [], {}])
def test_cite_rejects_invalid_names_before_source_search(name, monkeypatch):
    def unexpected_search(_name):
        raise AssertionError("invalid citation name reached adapter search")

    for adapter in E.adapters:
        monkeypatch.setattr(adapter, "cite", unexpected_search)
    _assert_invalid_name(E.cite(name))


def test_non_empty_name_contract_rejects_whitespace():
    problems = schema_issues({"name": " \t"}, NON_EMPTY_NAME_INPUT_SCHEMA)
    assert [problem.code for problem in problems] == ["pattern"]


@pytest.mark.parametrize(("name", "expected_exit", "reason_code"), [
    ("", 2, "invalid-input"),
    ("  \t", 2, "invalid-input"),
    ("Command", 0, None),
    ("Hexblade", 2, "unsupported-content"),
])
def test_cite_cli_contract(name, expected_exit, reason_code, capsys):
    assert cli.main(["cite", name]) == expected_exit
    payload = json.loads(capsys.readouterr().out)
    assert payload["exit_code"] == expected_exit
    if reason_code is not None:
        assert payload["data"]["reason_code"] == reason_code
    if reason_code == "invalid-input":
        assert payload["data"]["recoverability"] == "retry"
        assert payload["data"]["suggested_next_action"] == "repair-request"
        assert payload["data"]["missing_inputs"] == []
