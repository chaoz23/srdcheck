import json
import pathlib
import re
import subprocess
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from srdcheck.engine import Engine  # noqa: E402

ADAPTER = ROOT / "adapters" / "srd-5.2.1"


def engine():
    return Engine([ADAPTER])


def test_jurisdiction_known_content():
    e = engine()
    assert e.jurisdiction("Fireball").exit_code == 0
    assert e.jurisdiction("mage hand").exit_code == 0
    assert e.jurisdiction("Grappled").exit_code == 0
    assert e.jurisdiction("Aboleth").exit_code == 0
    assert e.jurisdiction("Disengage").exit_code == 0


def test_jurisdiction_unknown_content():
    e = engine()
    for name in ("Hexblade", "Gloomherald", "Silvery Barbs", "Booming Blade"):
        v = e.jurisdiction(name)
        assert v.exit_code == 2, name
        assert "cannot be adjudicated" in v.why


def test_mage_hand_demo_goldens():
    """The 8 demo scenarios are the adapter's first gold set."""
    e = engine()
    scenarios = [json.loads(l) for l in
                 (ROOT / "demo/mage-hand/scenarios.jsonl").open()]
    expected = {"mh-1": 0, "mh-2": 1, "mh-3": 1, "mh-4": 0,
                "mh-5": 2, "mh-6": 1, "mh-7": 1, "mh-8": 2}
    for s in scenarios:
        v = e.query("mage-hand.use", s["proposal"])
        assert v.exit_code == expected[s["id"]], (s["id"], v.why)
        if v.exit_code != 2:
            assert v.citations, s["id"]
        assert v.rule_ids, s["id"]


def test_unknown_query_type_is_exit_2():
    v = engine().query("wish.settle-argument", {})
    assert v.exit_code == 2


def test_determinism():
    e = engine()
    p = {"kind": "untie_knots", "distance_ft": 15}
    first = e.query("mage-hand.use", p).as_dict()
    for _ in range(20):
        assert e.query("mage-hand.use", p).as_dict() == first


def test_verdict_latency_budget():
    """T11: p95 single verdict < 100 ms (engine pre-loaded)."""
    e = engine()
    times = []
    for _ in range(100):
        t0 = time.perf_counter()
        e.query("mage-hand.use", {"kind": "attack"})
        times.append(time.perf_counter() - t0)
    times.sort()
    assert times[94] < 0.100, f"p95 {times[94]*1000:.2f} ms"


def test_kernel_is_game_free():
    """T7 lint: the kernel package contains no game vocabulary."""
    banned = re.compile(
        r"(?i)\b(spell|mage|hand|attack|wizard|dungeon|dragon|d20|dice|"
        r"condition|grapple|srd 5|feet|pounds)\b")
    for f in (ROOT / "srdcheck").glob("*.py"):
        for i, line in enumerate(f.read_text().splitlines(), 1):
            assert not banned.search(line), f"{f.name}:{i}: {line.strip()}"


def test_cli_exit_codes():
    def run(*args, stdin=None):
        return subprocess.run(
            [sys.executable, "-m", "srdcheck", *args],
            capture_output=True, text=True, input=stdin, cwd=ROOT)
    assert run("jurisdiction", "Fireball").returncode == 0
    assert run("jurisdiction", "Hexblade").returncode == 2
    r = run("query", "mage-hand.use", '{"kind": "attack"}')
    assert r.returncode == 1
    assert json.loads(r.stdout)["citations"]
    r = run("--pipe", stdin='{"type": "jurisdiction", "params": {"name": "Prone"}}')
    assert r.returncode == 0
    assert run("--schema").returncode == 0
    assert run("query", "x", "not-json").returncode == 3
