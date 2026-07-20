"""Passive Perception (SRD 5.2.1 p.22) — 10 + modifier, and honest refusal of the
non-SRD ±5 Advantage/Disadvantage adjustment."""

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from srdcheck.engine import Engine  # noqa: E402

E = Engine([ROOT / "srdcheck" / "adapters" / "srd-5.2.1"])


def pp(**p):
    return E.query("passive.perception", p)


def test_score_is_10_plus_modifier():
    assert pp(perception_modifier=4).data["score"] == 14
    assert pp().data["score"] == 10


def test_advantage_disadvantage_are_refused_as_non_srd():
    assert pp(perception_modifier=4, advantage=True).exit_code == 2
    assert pp(perception_modifier=4, disadvantage=True).exit_code == 2
