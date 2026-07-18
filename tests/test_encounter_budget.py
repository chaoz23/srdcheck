"""encounter.xp-budget (#4, SRD 5.2.1 p.202)."""
import pathlib, sys
ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from srdcheck.engine import Engine  # noqa: E402
E = Engine([ROOT / "srdcheck" / "adapters" / "srd-5.2.1"])

def q(**p): return E.query("encounter.xp-budget", p)

def test_issue_example():
    v = q(level=3, difficulty="moderate")
    assert v.exit_code == 0
    assert v.data["per_character"] == 225
    assert v.data["citation"] == "SRD 5.2.1 p.202"
    assert v.citations[0].page == 202

def test_transcription_accuracy_boundaries():
    assert q(level=1, difficulty="low").data["per_character"] == 50
    assert q(level=20, difficulty="high").data["per_character"] == 22000
    assert q(level=17, difficulty="high").data["per_character"] == 11700

def test_party_size_gives_total():
    v = q(level=5, difficulty="high", party_size=4)
    assert v.data["per_character"] == 1100 and v.data["total"] == 4400

def test_case_insensitive_difficulty():
    assert q(level=2, difficulty="MODERATE").data["per_character"] == 150

def test_out_of_range_refuses():
    assert q(level=21, difficulty="low").exit_code == 2
    assert q(level=0, difficulty="low").exit_code == 2
    assert q(level=5, difficulty="deadly").exit_code == 2

def test_cited():
    v = q(level=10, difficulty="moderate")
    assert v.citations and v.citations[0].quote
