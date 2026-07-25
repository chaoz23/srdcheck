"""Issue #12: the name registries are closed sets, census-anchored — the test
re-runs the extraction independently and compares against entities.json."""
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from build_name_registries import extract  # noqa: E402

ENTS = json.loads((ROOT / "srdcheck/adapters/srd-5.2.1/entities.json").read_text())


def test_registry_matches_independent_extraction():
    fresh = extract()
    for cat, names in fresh.items():
        assert ENTS.get(cat) == names, f"{cat}: registry drifted from source text"


def test_expected_cardinalities():
    assert len(ENTS["class"]) == 12
    assert len(ENTS["subclass"]) == 12      # exactly one per class in SRD 5.2.1
    assert len(ENTS["species"]) == 9
    assert len(ENTS["feat"]) == 17


def test_jurisdiction_spot_checks():
    from srdcheck.engine import Engine
    from srdcheck.access import default_adapter_paths
    eng = Engine(default_adapter_paths())
    assert eng.jurisdiction("Alert").exit_code == 0        # was exit 2 (bug)
    assert eng.jurisdiction("Paladin").exit_code == 0
    assert eng.jurisdiction("Life Domain").exit_code == 0
    assert eng.jurisdiction("Hexblade").exit_code == 2     # correctly outside
    assert eng.jurisdiction("Variant Human").exit_code == 2
