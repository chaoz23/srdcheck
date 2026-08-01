"""Issue #11/#13: unknown params must refuse loudly; unseen facts compose.
Every test here is a dated table failure (playtests 2026-07-20/24)."""
import pytest
from srdcheck.engine import Engine
from srdcheck.access import default_adapter_paths


@pytest.fixture(scope="module")
def eng():
    return Engine(default_adapter_paths())


class TestHiddenArcher:
    """Playtest finding #5: unknown params silently became a confident
    'straight' roll for a hidden attacker."""

    def test_unknown_fields_refuse_and_name_offenders(self, eng):
        v = eng.query("attack.modifiers",
                      {"attacker": {"unseen": True},
                       "target": {"cannot_see_attacker": True},
                       "distance_ft": 30})
        assert v.exit_code == 2
        assert "attacker.unseen" in v.data["unknown_fields"]
        assert "target.cannot_see_attacker" in v.data["unknown_fields"]
        assert "roll" not in (v.data or {})          # no composed verdict

    def test_correct_field_composes_advantage_with_citation(self, eng):
        v = eng.query("attack.modifiers",
                      {"attacker": {"unseen_by_target": True}, "target": {},
                       "distance_ft": 30})
        assert v.exit_code == 0
        assert v.data["roll"] == "advantage"
        assert any("Unseen Attackers" in c.section for c in v.citations)

    def test_unseen_target_disadvantage(self, eng):
        v = eng.query("attack.modifiers",
                      {"attacker": {}, "target": {"unseen_by_attacker": True},
                       "distance_ft": 30})
        assert v.data["roll"] == "disadvantage"

    def test_seen_exception_no_advantage(self, eng):
        """If the target CAN see the attacker, the caller contradiction
        yields no unseen advantage."""
        v = eng.query("attack.modifiers",
                      {"attacker": {"unseen_by_target": True},
                       "target": {"can_see_attacker": True},
                       "distance_ft": 30})
        assert v.data["roll"] == "straight"

    def test_clean_case_still_straight(self, eng):
        v = eng.query("attack.modifiers", {"attacker": {}, "target": {},
                                             "distance_ft": 30})
        assert v.data["roll"] == "straight"


class TestPassivePerceptionTypo:
    """Playtest finding #13: 'modifier' vs 'perception_modifier' silently
    computed with 0."""

    def test_typo_refuses(self, eng):
        v = eng.query("passive.perception", {"modifier": -1})
        assert v.exit_code == 2
        assert v.data["unknown_fields"] == ["modifier"]

    def test_correct_field_computes(self, eng):
        v = eng.query("passive.perception", {"perception_modifier": -1})
        assert v.exit_code == 0
        assert v.data["score"] == 9
