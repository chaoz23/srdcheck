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
    assert "srdcheck-query-scope:save.check" in \
        legal["subject"]["entity_refs"]

    illegal_params = {"kind": "attack"}
    result = project_table_evaluation(
        ADAPTER.query("mage-hand.use", illegal_params),
        "mage-hand.use", illegal_params)
    assert result["status"] == "findings"
    assert result["exit_code"] == 1
    assert "mage-hand.cant-attack" in result["findings"][0]["evidence_refs"]
    assert result["findings"][0]["effective_policy"]["adapter"].startswith(
        "srd-5.2.1@")
    evidence = result["findings"][0]["effective_policy"]["evidence"]
    assert set(evidence) == set(result["findings"][0]["evidence_refs"])
    assert any(item["kind"] == "citation" and item["citation"]["quote"]
               for item in evidence.values())


def test_refusal_reasons_map_without_false_clean():
    cases = [
        ("save.check", {"modifier": 2}, "incomplete", "srdcheck.missing_fact",
         (1, 1, 0, 1)),
        ("spell.facts", {"name": "Hexblade"}, "unsupported",
         "srdcheck.unsupported_content", (0, 0, 0, 0)),
        ("save.check", {"modifier": 2, "dc": 10, "bogus": 1}, "invalid",
         "srdcheck.invalid_input", (0, 0, 0, 0)),
    ]
    for query_type, params, status, code, counts in cases:
        result = project_table_evaluation(
            ADAPTER.query(query_type, params), query_type, params)
        assert result["status"] == status
        assert result["exit_code"] == 2
        assert result["coverage"]["complete"] is False
        assert result["findings"] == []
        assert result["errors"][0]["code"] == code
        coverage = result["coverage"]
        assert (coverage["compatible"], coverage["eligible"],
                coverage["evaluated"], coverage["skipped"]) == counts


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


def test_caller_context_is_joinable_but_never_grants_authority():
    params = save_params(12)
    verdict = ADAPTER.query("save.check", params)
    context = {
        "session_id": "session-7",
        "entity_refs": ["character:aria", "encounter:bridge"],
        "correlation_id": "discord-message-42",
    }
    result = project_table_evaluation(
        verdict, "save.check", params, context=context)
    assert result["subject"]["session_id"] == "session-7"
    assert result["subject"]["entity_refs"] == [
        "srdcheck-query-scope:save.check", "character:aria",
        "encounter:bridge", "correlation:discord-message-42",
    ]
    assert result["authority_status"] == "self_attested"
    assert result != project_table_evaluation(
        verdict, "save.check", params, context={"session_id": "session-8"})


def test_invalid_caller_context_is_rejected():
    params = save_params(12)
    verdict = ADAPTER.query("save.check", params)
    for context in ({"host_attested": True}, {"entity_refs": [""]}, []):
        try:
            project_table_evaluation(
                verdict, "save.check", params, context=context)
        except ValueError:
            pass
        else:
            raise AssertionError("invalid caller context was accepted")


def test_cli_and_pipe_emit_shared_envelope(capsys, monkeypatch):
    params = json.dumps({"kind": "attack"})
    assert main(["query", "mage-hand.use", params,
                 "--table-evaluation"]) == 1
    result = json.loads(capsys.readouterr().out)
    assert result["schema_version"] == "table.evaluation/1.0"
    assert result["status"] == "findings"

    context = json.dumps({"session_id": "session-cli",
                          "correlation_id": "turn-3"})
    assert main(["query", "mage-hand.use", params, "--table-evaluation",
                 "--table-context", context]) == 1
    contextual = json.loads(capsys.readouterr().out)
    assert contextual["subject"]["session_id"] == "session-cli"
    assert "correlation:turn-3" in contextual["subject"]["entity_refs"]

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
