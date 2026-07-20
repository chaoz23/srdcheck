"""Opportunity Attack trigger goldens (SRD 5.2.1 p.15): provokes only on
voluntary movement out of reach by a creature you can see."""

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from srdcheck.engine import Engine  # noqa: E402

E = Engine([ROOT / "srdcheck" / "adapters" / "srd-5.2.1"])


def oa(**p):
    return E.query("opportunity-attack.provoked", p)


def test_voluntary_movement_by_a_seen_creature_provokes():
    v = oa(movement_kind="voluntary", mover_seen_by_reactor=True)
    assert v.exit_code == 0 and v.data["provoked"] is True
    assert "opportunity-attack.making" in v.rule_ids


def test_disengage_teleport_and_forced_movement_do_not_provoke():
    for kind in ("disengage", "teleport", "forced"):
        v = oa(movement_kind=kind)
        assert v.data["provoked"] is False, kind
        assert "opportunity-attack.avoiding" in v.rule_ids


def test_unseen_mover_does_not_provoke():
    v = oa(movement_kind="voluntary", mover_seen_by_reactor=False)
    assert v.data["provoked"] is False


def test_not_leaving_reach_does_not_provoke():
    assert oa(leaves_reach=False).data["provoked"] is False


def test_default_is_voluntary_and_seen():
    # a bare call assumes the provoking case (voluntary, seen, leaves reach)
    assert oa().data["provoked"] is True


def test_unknown_movement_kind_refuses():
    assert oa(movement_kind="sprint").exit_code == 2
