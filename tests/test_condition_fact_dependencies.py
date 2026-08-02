"""Issue #49: condition effects never invent omitted observations."""

import json
import pathlib

import pytest

from srdcheck import cli
from srdcheck.adapter import Adapter
from srdcheck.engine import Engine
from srdcheck.mcp import PROTOCOL_VERSION, Server


ROOT = pathlib.Path(__file__).resolve().parent.parent
ADAPTER = ROOT / "srdcheck" / "adapters" / "srd-5.2.1"
E = Engine([ADAPTER])


def _missing(verdict, *paths):
    assert verdict.exit_code == 2
    assert verdict.data["reason_code"] == "missing-fact"
    assert verdict.data["recoverability"] == "retry"
    assert verdict.data["suggested_next_action"] == "provide-facts"
    assert verdict.data["missing_inputs"] == list(paths)


def _attack(**params):
    return E.query("attack.modifiers", params)


def _check(**params):
    return E.query("check.make", params)


def test_attack_condition_fact_matrices():
    frightened = {"attacker": {"conditions": ["Frightened"]},
                  "target": {}, "distance_ft": 5}
    _missing(_attack(**frightened), "attacker.frightened_source_in_sight")
    assert _attack(**{
        **frightened,
        "attacker": {**frightened["attacker"],
                     "frightened_source_in_sight": False},
    }).data["roll"] == "straight"
    assert _attack(**{
        **frightened,
        "attacker": {**frightened["attacker"],
                     "frightened_source_in_sight": True},
    }).data["roll"] == "disadvantage"

    charmed = {"attacker": {"conditions": ["Charmed"]},
               "target": {}, "distance_ft": 5}
    _missing(_attack(**charmed), "target.is_charmer_of_attacker")
    assert _attack(**{
        **charmed, "target": {"is_charmer_of_attacker": False},
    }).data["roll"] == "straight"
    assert _attack(**{
        **charmed, "target": {"is_charmer_of_attacker": True},
    }).exit_code == 1

    grappled = {"attacker": {"conditions": ["Grappled"]},
                "target": {}, "distance_ft": 5}
    _missing(_attack(**grappled), "target.is_grappler_of_attacker")
    assert _attack(**{
        **grappled, "target": {"is_grappler_of_attacker": False},
    }).data["roll"] == "disadvantage"
    assert _attack(**{
        **grappled, "target": {"is_grappler_of_attacker": True},
    }).data["roll"] == "straight"

    invisible_attacker = {
        "attacker": {"conditions": ["Invisible"]},
        "target": {}, "distance_ft": 5,
    }
    _missing(_attack(**invisible_attacker), "target.can_see_attacker")
    assert _attack(**{
        **invisible_attacker, "target": {"can_see_attacker": False},
    }).data["roll"] == "advantage"
    assert _attack(**{
        **invisible_attacker, "target": {"can_see_attacker": True},
    }).data["roll"] == "straight"

    invisible_target = {
        "attacker": {}, "target": {"conditions": ["Invisible"]},
        "distance_ft": 5,
    }
    _missing(_attack(**invisible_target), "attacker.can_see_target")
    assert _attack(**{
        **invisible_target, "attacker": {"can_see_target": False},
    }).data["roll"] == "disadvantage"
    assert _attack(**{
        **invisible_target, "attacker": {"can_see_target": True},
    }).data["reason_code"] == "rules-ambiguous"


def test_check_condition_fact_matrices():
    blinded = {"actor_conditions": ["Blinded"], "dc": 5,
               "d20_result": 20}
    _missing(_check(**blinded), "check_requires")
    assert _check(**{**blinded, "check_requires": ["sight"]}).data[
        "auto_fail"]
    assert _check(**{**blinded, "check_requires": []}).data["success"]

    deafened = {"actor_conditions": ["Deafened"], "dc": 5,
                "d20_result": 20}
    _missing(_check(**deafened), "check_requires")
    assert _check(**{**deafened, "check_requires": ["hearing"]}).data[
        "auto_fail"]
    assert _check(**{**deafened, "check_requires": []}).data["success"]

    frightened = {"actor_conditions": ["Frightened"], "dc": 10}
    _missing(_check(**frightened), "frightened_source_in_sight")
    assert _check(**{
        **frightened, "frightened_source_in_sight": False,
    }).data["roll"] == "straight"
    assert _check(**{
        **frightened, "frightened_source_in_sight": True,
    }).data["roll"] == "disadvantage"

    social = {"social": True, "dc": 10}
    _missing(_check(**social), "target_charmed_by_actor")
    assert _check(**{
        **social, "target_charmed_by_actor": False,
    }).data["roll"] == "straight"
    assert _check(**{
        **social, "target_charmed_by_actor": True,
    }).data["roll"] == "advantage"
    _missing(_check(dc=10, target_charmed_by_actor=True), "social")


@pytest.mark.parametrize("condition,embed_atom", [
    ("Stunned", "condition.stunned.incapacitated"),
    ("Paralyzed", "condition.paralyzed.incapacitated"),
    ("Petrified", "condition.petrified.incapacitated"),
    ("Unconscious", "condition.unconscious.inert"),
])
def test_ranged_enemy_dependencies_and_incapacitated_embeds(
        condition, embed_atom):
    base = {"attacker": {}, "target": {}, "distance_ft": 30,
            "ranged": True}
    _missing(_attack(**base), "nearby_enemies")
    assert _attack(**{**base, "nearby_enemies": []}).data[
        "roll"] == "straight"
    # A supplied false prerequisite is sufficient; no condition census is
    # needed for an enemy that cannot see the attacker.
    assert _attack(**{
        **base, "nearby_enemies": [{"can_see_attacker": False}],
    }).data["roll"] == "straight"
    _missing(_attack(**{
        **base, "nearby_enemies": [{"can_see_attacker": True}],
    }), "nearby_enemies[0].conditions")
    threatening = _attack(**{
        **base,
        "nearby_enemies": [{"can_see_attacker": True, "conditions": []}],
    })
    assert threatening.data["roll"] == "disadvantage"
    embedded = _attack(**{
        **base,
        "nearby_enemies": [{"can_see_attacker": True,
                            "conditions": [condition]}],
    })
    assert embedded.data["roll"] == "straight"
    assert embed_atom in embedded.rule_ids


def test_ranged_enemy_dependency_claim_evidence():
    for condition, embed_atom in (
            ("Stunned", "condition.stunned.incapacitated"),
            ("Paralyzed", "condition.paralyzed.incapacitated"),
            ("Petrified", "condition.petrified.incapacitated"),
            ("Unconscious", "condition.unconscious.inert")):
        test_ranged_enemy_dependencies_and_incapacitated_embeds(
            condition, embed_atom)


@pytest.mark.parametrize("query_type,params", [
    ("attack.modifiers", {
        "attacker": {"conditions": ["Hexcursed"]}, "target": {},
        "distance_ft": 5,
    }),
    ("check.make", {"actor_conditions": ["Hexcursed"], "dc": 10}),
])
def test_roll_surfaces_share_condition_category_gate(
        query_type, params, monkeypatch):
    unknown = E.query(query_type, params)
    assert unknown.data["reason_code"] == "unsupported-content"

    field = "attacker" if query_type == "attack.modifiers" else None
    wrong_params = dict(params)
    if field:
        wrong_params[field] = {"conditions": ["Fireball"]}
    else:
        wrong_params["actor_conditions"] = ["Fireball"]
    wrong = E.query(query_type, wrong_params)
    assert wrong.data["reason_code"] == "invalid-input"

    handler_globals = E.adapters[0]._handlers[query_type].__globals__
    modeled_name = ("_ATTACK_MODELED" if query_type == "attack.modifiers"
                    else "_CHECK_MODELED")
    modeled = handler_globals[modeled_name]
    monkeypatch.setitem(handler_globals, modeled_name, modeled - {"poisoned"})
    if field:
        unmodeled_params = {
            "attacker": {"conditions": ["Poisoned"]}, "target": {},
            "distance_ft": 5,
        }
    else:
        unmodeled_params = {"actor_conditions": ["Poisoned"], "dc": 10}
    unmodeled = E.query(query_type, unmodeled_params)
    assert unmodeled.data["reason_code"] == "unmodeled-rule"


def test_condition_category_gate_claim_evidence(monkeypatch):
    test_roll_surfaces_share_condition_category_gate(
        "attack.modifiers", {
            "attacker": {"conditions": ["Hexcursed"]}, "target": {},
            "distance_ft": 5,
        }, monkeypatch)
    test_roll_surfaces_share_condition_category_gate(
        "check.make", {"actor_conditions": ["Hexcursed"], "dc": 10},
        monkeypatch)


def _ready_server():
    server = Server([ADAPTER])
    init = {"jsonrpc": "2.0", "id": 1, "method": "initialize",
            "params": {"protocolVersion": PROTOCOL_VERSION,
                       "capabilities": {},
                       "clientInfo": {"name": "dependency-test",
                                      "version": "1.0"}}}
    assert "result" in server.handle(init)
    server.handle({"jsonrpc": "2.0", "method": "notifications/initialized"})
    return server


@pytest.mark.parametrize("query_type,tool_name,params,missing_path", [
    ("attack.modifiers", "attack_modifiers", {
        "attacker": {"conditions": ["Frightened"]}, "target": {},
        "distance_ft": 5,
    }, "attacker.frightened_source_in_sight"),
    ("check.make", "check_make", {
        "actor_conditions": ["Blinded"], "dc": 10,
    }, "check_requires"),
])
def test_library_cli_mcp_missing_fact_parity(
        query_type, tool_name, params, missing_path, capsys):
    library = E.query(query_type, params).as_dict()

    assert cli.main(["query", query_type, json.dumps(params)]) == 2
    command = json.loads(capsys.readouterr().out)

    server = _ready_server()
    response = server.handle({
        "jsonrpc": "2.0", "id": 2, "method": "tools/call",
        "params": {"name": tool_name, "arguments": params},
    })
    mcp = response["result"]["structuredContent"]

    for payload in (library, command, mcp):
        assert payload["exit_code"] == 2
        assert payload["data"]["reason_code"] == "missing-fact"
        assert payload["data"]["missing_inputs"] == [missing_path]
        assert payload["data"]["suggested_next_action"] == "provide-facts"


def test_transport_parity_claim_evidence(capsys):
    test_library_cli_mcp_missing_fact_parity(
        "attack.modifiers", "attack_modifiers", {
            "attacker": {"conditions": ["Frightened"]}, "target": {},
            "distance_ft": 5,
        }, "attacker.frightened_source_in_sight", capsys)
    test_library_cli_mcp_missing_fact_parity(
        "check.make", "check_make", {
            "actor_conditions": ["Blinded"], "dc": 10,
        }, "check_requires", capsys)


def test_condition_dependency_contract_is_complete_and_executable():
    contract = json.loads(
        (ADAPTER / "condition_dependencies.json").read_text())
    assert contract["schema_version"] == "1.0"
    attack = contract["surfaces"]["attack.modifiers"]
    checks = contract["surfaces"]["check.make"]
    assert set(attack["effects"]) == {
        "attacker.charmed", "attacker.frightened", "attacker.poisoned",
        "attacker.prone", "attacker.blinded", "attacker.restrained",
        "attacker.grappled", "attacker.invisible", "attacker.exhaustion",
        "target.prone", "target.blinded", "target.restrained",
        "target.paralyzed", "target.stunned", "target.petrified",
        "target.unconscious", "target.invisible",
        "nearby-enemy.incapacitated",
    }
    assert set(checks["effects"]) == {
        "actor.blinded", "actor.deafened", "actor.poisoned",
        "actor.frightened", "actor.exhaustion", "target.charmed-social",
    }
    atoms = Adapter(ADAPTER).atoms
    for surface in contract["surfaces"].values():
        for effect in surface["effects"].values():
            assert effect["condition"]
            assert isinstance(effect["required_facts"], list)
            assert effect["rule_ids"]
            assert set(effect["rule_ids"]) <= set(atoms)
    assert attack["query_dependencies"]["ranged.close-combat"][
        "required_facts"] == ["nearby_enemies"]
