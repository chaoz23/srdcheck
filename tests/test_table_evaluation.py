import json

from srdcheck import load_adapter, project_table_evaluation
from srdcheck.cli import main
from srdcheck.verdict import illegal


ADAPTER = load_adapter("srd-5.2.1")


def save_params(d20_result):
    return {"modifier": 2, "dc": 10, "d20_result": d20_result,
            "save_ability": "dex", "saver_conditions": []}


def test_legal_and_illegal_project_complete_scoped_results():
    legal_params = save_params(12)
    legal = project_table_evaluation(
        ADAPTER.query("save.check", legal_params), "save.check", legal_params)
    assert legal["status"] == "checked_clean"
    assert legal["exit_code"] == 0
    assert legal["coverage"]["complete"] is True
    assert legal["authority_status"] == "self_attested"

    illegal_params = {"kind": "attack"}
    result = project_table_evaluation(
        ADAPTER.query("mage-hand.use", illegal_params),
        "mage-hand.use", illegal_params)
    assert result["status"] == "findings"
    assert result["exit_code"] == 1
    assert "mage-hand.cant-attack" in result["findings"][0]["evidence_refs"]
    assert result["findings"][0]["effective_policy"]["adapter"].startswith(
        "srd-5.2.1@")


def test_refusal_reasons_map_without_false_clean():
    cases = [
        ("save.check", {"modifier": 2}, "incomplete", "srdcheck.missing_fact"),
        ("spell.facts", {"name": "Hexblade"}, "unsupported",
         "srdcheck.unsupported_content"),
        ("save.check", {"modifier": 2, "dc": 10, "bogus": 1}, "invalid",
         "srdcheck.invalid_input"),
    ]
    for query_type, params, status, code in cases:
        result = project_table_evaluation(
            ADAPTER.query(query_type, params), query_type, params)
        assert result["status"] == status
        assert result["exit_code"] == 2
        assert result["coverage"]["complete"] is False
        assert result["findings"] == []
        assert result["errors"][0]["code"] == code


def test_projection_is_deterministic_and_input_bound():
    params = save_params(12)
    verdict = ADAPTER.query("save.check", params)
    first = project_table_evaluation(verdict, "save.check", params)
    second = project_table_evaluation(verdict, "save.check", params)
    assert first == second
    assert first["evaluation_id"].startswith("srdcheck-")
    assert first["cursor"]["input_digest"].startswith("sha256:")
    changed = project_table_evaluation(
        ADAPTER.query("save.check", save_params(13)),
        "save.check", save_params(13))
    assert changed["evaluation_id"] != first["evaluation_id"]


def test_illegal_without_evidence_is_typed_internal_error():
    verdict = illegal("future illegal result", adapter="future@1.0")
    result = project_table_evaluation(verdict, "future.query", {})
    assert result["status"] == "internal_error"
    assert result["findings"] == []
    assert result["errors"][0]["code"] == \
        "table_evaluation.finding_evidence_missing"


def test_cli_and_pipe_emit_shared_envelope(capsys, monkeypatch):
    params = json.dumps({"kind": "attack"})
    assert main(["query", "mage-hand.use", params,
                 "--table-evaluation"]) == 1
    result = json.loads(capsys.readouterr().out)
    assert result["schema_version"] == "table.evaluation/1.0"
    assert result["status"] == "findings"

    monkeypatch.setattr("sys.stdin", __import__("io").StringIO("not-json"))
    assert main(["--pipe", "--table-evaluation"]) == 2
    invalid = json.loads(capsys.readouterr().out)
    assert invalid["status"] == "invalid"
    assert invalid["errors"][0]["code"] == "srdcheck.invalid_input"

    monkeypatch.setattr("sys.stdin", __import__("io").StringIO("[]"))
    assert main(["--pipe", "--table-evaluation"]) == 2
    wrong_shape = json.loads(capsys.readouterr().out)
    assert wrong_shape["status"] == "invalid"
    assert wrong_shape["coverage"]["evaluators"][0]["id"] == "invalid-query"
