#!/usr/bin/env python3
"""srdcheck prototype, scoped to one spell: Mage Hand (SRD 5.2.1 p.145).

Demo scaffolding, not the kernel — but the verdict semantics are the real
ones: exit 0 legal / 1 illegal / 2 cannot-adjudicate, citations always,
deterministic always. Rule atoms transcribed from the verified SRD text.
"""

CITE = "SRD 5.2.1 p.145 'Spells > Mage Hand'"

GRANTED = {
    "manipulate_object": "you can use the hand to manipulate an object",
    "open_unlocked": "open an unlocked door or container",
    "stow_retrieve_open": "stow or retrieve an item from an open container",
    "pour_vial": "pour the contents out of a vial",
}
FORBIDDEN = {
    "attack": "The hand can't attack",
    "activate_magic_item": "The hand can't activate magic items",
}
MAX_CARRY_LB = 10
MAX_RANGE_FT = 30


def verdict(p):
    """p: {kind, weight_lb?, distance_ft?} -> verdict dict."""
    def out(v, code, why, cited=True):
        return {"verdict": v, "exit_code": code,
                "citations": [CITE] if cited else [],
                "why": why, "adapter": "srd-5.2.1@demo (mage hand only)"}

    if p.get("distance_ft", 0) > MAX_RANGE_FT:
        return out("illegal", 1,
                   f"The hand vanishes if it is ever more than {MAX_RANGE_FT} feet "
                   f"away from you; the target is {p['distance_ft']} feet away.")
    if p["kind"] in FORBIDDEN:
        return out("illegal", 1, FORBIDDEN[p["kind"]] + ".")
    if p.get("weight_lb", 0) > MAX_CARRY_LB:
        return out("illegal", 1,
                   f"The hand can't carry more than {MAX_CARRY_LB} pounds; "
                   f"the object weighs {p['weight_lb']} pounds.")
    if p["kind"] in GRANTED:
        checks = [f"granted use: '{GRANTED[p['kind']]}'"]
        if "weight_lb" in p:
            checks.append(f"{p['weight_lb']} lb is within the {MAX_CARRY_LB} lb limit")
        if "distance_ft" in p:
            checks.append(f"{p['distance_ft']} ft is within the {MAX_RANGE_FT} ft range")
        return out("legal", 0, "; ".join(checks) + ".")
    return out("cannot-adjudicate", 2,
               "The spell text neither grants nor forbids this use. Whether "
               "'manipulate an object' extends to it — and any check required — "
               "is the GM's ruling to make.")


if __name__ == "__main__":
    import json
    import sys
    print(json.dumps(verdict(json.loads(sys.argv[1])), indent=2))
