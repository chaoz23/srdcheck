"""v0.3 formula blanks: a stat formula with unsupplied blanks must render as
the FORMULA, never as a complete-looking number. Origin: live table 2026-07-24
— grapple.initiate returned 'DC 8' when the true DC was 13 (8 + STR 2 + PB 3).
Audit (2026-07-26): grapple.initiate and passive.perception were the only
stat-formula surfaces with silent-zero blanks; roll-resolution lanes
(save.check, check.make, concentration.check) display their composition and
legality-gate defaults (distance/weight/speed) are benign no-ops."""
import pytest
from srdcheck.engine import Engine
from srdcheck.access import default_adapter_paths


@pytest.fixture(scope="module")
def eng():
    return Engine(default_adapter_paths())


class TestGrappleBlanks:
    def test_no_blanks_yields_formula_never_a_number(self, eng):
        v = eng.query("grapple.initiate", {"kind": "grapple"})
        assert v.exit_code == 0
        assert "dc" not in v.data
        assert "8 + Strength modifier" in v.data["dc_formula"]
        assert "DC 8" not in v.verdict  # the exact wrong-looking render

    def test_live_table_regression_dc13(self, eng):
        v = eng.query("grapple.initiate",
                      {"kind": "grapple", "str_modifier": 2,
                       "proficiency_bonus": 3})
        assert v.exit_code == 0
        assert v.data["dc"] == 13
        assert v.data["dc_formula"].startswith("8 + ")

    def test_partial_blanks_still_formula_only(self, eng):
        v = eng.query("grapple.initiate",
                      {"kind": "shove", "str_modifier": 4})
        assert "dc" not in v.data


class TestPassiveBlanks:
    def test_no_modifier_yields_formula(self, eng):
        v = eng.query("passive.perception", {})
        assert v.exit_code == 0
        assert "score" not in v.data
        assert v.data["score_formula"] == "10 + perception_modifier"

    def test_with_modifier_resolves(self, eng):
        v = eng.query("passive.perception", {"perception_modifier": 4})
        assert v.data["score"] == 14
