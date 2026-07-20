#!/usr/bin/env python3
"""Coverage census (Measured Engine M0): what fraction of realistic combat-turn
events can srdcheck adjudicate, and where do the gaps cluster?

Each corpus event is routed to a srdcheck query (or marked as having none).
Outcomes:
  ADJUDICATED  — a query exists and returns a verdict (exit 0/1)
  REFUSED      — a query exists but honestly refuses (exit 2): a modeled-scope gap
  UNCOVERED    — no query exists for this event kind: an unbuilt-capability gap

Reports coverage per event-kind (never a single blended number, T9), so the gap
histogram prioritizes what to deepen. Run: python bench/coverage.py
"""

import collections
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from srdcheck.engine import Engine  # noqa: E402

E = Engine([ROOT / "srdcheck" / "adapters" / "srd-5.2.1"])
CORPUS = [json.loads(l) for l in (ROOT / "bench" / "sets" / "coverage.jsonl").open()]

# Scope decides what "coverage" even means. in-scope = rules adjudication srdcheck
# should do. longtail = in-scope in principle but the swamp (per-spell effects) —
# deliberately deferred (T8). out-of-scope = GM discretion / RNG / VTT geometry,
# which srdcheck correctly never does (T6) — NOT a gap.
SCOPE = {
    "movement": "in-scope", "action-economy": "in-scope",
    "attack-modifiers": "in-scope", "condition-movement": "in-scope",
    "roll-composition": "in-scope", "reaction": "in-scope",
    "enumeration": "in-scope", "spell-economy": "in-scope",
    "state-transition": "in-scope", "creature-stats": "in-scope",
    "encounter-budget": "in-scope", "specific-spell-modeled": "in-scope",
    "feature-prereq": "in-scope", "damage-hp": "in-scope",
    "death-saves": "in-scope", "saving-throw": "in-scope",
    "unmodeled-condition": "in-scope",
    "ranged-attack": "in-scope", "opportunity-attack": "in-scope",
    "difficult-terrain": "in-scope", "grapple-shove": "in-scope",
    "help-action": "in-scope",
    "spell-effect": "longtail",
    "contest": "out-of-scope", "skill-check": "out-of-scope",
    "initiative": "out-of-scope", "cover-geometry": "out-of-scope",
}


def classify(ev):
    route = ev["route"]
    if not route.get("type"):
        return "UNCOVERED", None
    v = E.query(route["type"], route.get("params", {}))
    if v.exit_code in (0, 1):
        return "ADJUDICATED", v.exit_code
    return "REFUSED", v.why


def main():
    by_kind = collections.defaultdict(collections.Counter)
    for ev in CORPUS:
        status, _ = classify(ev)
        by_kind[ev["kind"]][status] += 1

    def scope_counts(scope):
        c = collections.Counter()
        for kind, counter in by_kind.items():
            if SCOPE.get(kind) == scope:
                c.update(counter)
        return c

    ins = scope_counts("in-scope")
    in_total = sum(ins.values())
    adj = ins["ADJUDICATED"]
    print("=== Coverage census (Measured Engine M0) ===")
    print(f"IN-SCOPE coverage: {adj}/{in_total} = {adj / in_total * 100:.0f}% "
          "adjudicated (the honest denominator — GM/RNG/VTT excluded)")
    print(f"  refused (modeled-scope gap): {ins['REFUSED']}  |  "
          f"uncovered (unbuilt): {ins['UNCOVERED']}")

    print("\nCLOSEABLE in-scope gaps — the A priority (concentrated?):")
    for kind in sorted(by_kind, key=lambda k: -(by_kind[k]['REFUSED']
                                                + by_kind[k]['UNCOVERED'])):
        if SCOPE.get(kind) != "in-scope":
            continue
        gap = by_kind[kind]["REFUSED"] + by_kind[kind]["UNCOVERED"]
        if gap:
            ex = next(e["event"] for e in CORPUS if e["kind"] == kind)
            print(f"  {kind:<20} gap={gap}  e.g. {ex}")

    lt = scope_counts("longtail")
    oos = scope_counts("out-of-scope")
    print(f"\nLONGTAIL (the swamp — keep refusing, T8): "
          f"{sum(lt.values())} events, e.g. per-spell effects")
    print(f"OUT-OF-SCOPE (correctly never covered, T6): {sum(oos.values())} "
          "events — GM discretion / RNG / VTT geometry. A feature, not a gap.")


if __name__ == "__main__":
    main()
