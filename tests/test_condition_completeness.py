"""Conditions completeness oracle.

Product principle (Oz, 2026-07-18): if a rule is codified in the SRD, it must be
checkable. Honest refusal (exit 2) is for the genuinely undecidable — GM
discretion, RNG, geometry, content outside the SRD. Refusing a *codified* rule as
merely unbuilt is a gap wearing the exit-2 costume, and this oracle forbids it.

Every SRD condition is classified clause-by-clause. Each mechanical clause is
either MODELED (points at a real atom), DEFERRED (names an unbuilt *surface* —
not "we didn't bother"), or has NO mechanical effect. The registry is cross-
checked against the adapter's actual condition list, so a condition can't be
added or renamed without being classified. And at runtime, no condition may be
silently refused on the two built surfaces (attack.modifiers, turn.plan)."""

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from srdcheck.access import load_adapter  # noqa: E402
from srdcheck.adapter import Adapter  # noqa: E402
from srdcheck.engine import Engine  # noqa: E402

A = load_adapter("srd-5.2.1")
ATOMS = Adapter(ROOT / "srdcheck" / "adapters" / "srd-5.2.1").atoms
E = Engine([ROOT / "srdcheck" / "adapters" / "srd-5.2.1"])

# Deferrals must name one of these unbuilt surfaces — a real capability srdcheck
# doesn't expose, never a euphemism for laziness.
ALLOWED_DEFERRALS = {
    "save-ability-typing",   # save.check isn't Str/Dex/Con-typed
    "damage-typing",         # no per-damage-type resistance subsystem
    "ability-check-surface", # no ability/skill-check query
    "social-check-surface",  # no social-interaction query
    "stealth-perception",    # no hidden/perception subsystem
    "geometry",              # positional/line-of-sight (T6, out of scope)
    "graduated-speed",       # graduated per-level Speed reduction
    "initiative",            # initiative is out of scope (T6/RNG)
    "condition-immunity",    # granting immunity to other conditions
}

M = "modeled"      # (M, atom_id)
D = "deferred"     # (D, reason)
N = "no-effect"    # flavor / no mechanical effect

# condition -> list of (status, atom_id_or_reason) for each mechanical clause.
CONDITION_EFFECTS = {
    "Blinded": [(M, "condition.blinded.attacks"), (D, "ability-check-surface")],
    "Charmed": [(M, "condition.charmed.cant-harm-charmer"),
                (D, "social-check-surface")],
    "Deafened": [(D, "ability-check-surface")],
    "Exhaustion": [(M, "condition.exhaustion.d20-penalty"),  # d20 Tests incl saves
                   (M, "condition.exhaustion.speed-reduction")],
    "Frightened": [(M, "condition.frightened.attacks"), (D, "geometry")],
    "Grappled": [(M, "condition.grappled.attacks"),
                 (M, "condition.grappled.speed-zero")],
    "Incapacitated": [(M, "condition.incapacitated.inactive"),
                      (M, "concentration.breaks-on-incapacitated"),
                      (D, "initiative")],
    "Invisible": [(M, "condition.invisible.attacks"), (D, "stealth-perception")],
    "Paralyzed": [(M, "condition.paralyzed.incapacitated"),
                  (M, "condition.paralyzed.speed-zero"),
                  (M, "condition.paralyzed.attacks"),
                  (M, "condition.paralyzed.auto-crit"),
                  (M, "condition.paralyzed.saves-fail")],
    "Petrified": [(M, "condition.petrified.incapacitated"),
                  (M, "condition.petrified.speed-zero"),
                  (M, "condition.petrified.attacks"),
                  (M, "condition.petrified.saves-fail"),
                  (M, "condition.petrified.resist-damage"),
                  (D, "condition-immunity"), (N, "weight x10 / cease aging")],
    "Poisoned": [(M, "condition.poisoned.attacks"),
                 (D, "ability-check-surface")],
    "Prone": [(M, "condition.prone.attacks"), (M, "condition.prone.movement")],
    "Restrained": [(M, "condition.restrained.speed-zero"),
                   (M, "condition.restrained.attacks"),
                   (M, "condition.restrained.saves")],
    "Stunned": [(M, "condition.stunned.incapacitated"),
                (M, "condition.stunned.attacks"),
                (M, "condition.stunned.saves-fail")],
    "Unconscious": [(M, "condition.unconscious.inert"),
                    (M, "condition.unconscious.speed-zero"),
                    (M, "condition.unconscious.attacks"),
                    (M, "condition.unconscious.auto-crit"),
                    (M, "condition.unconscious.saves-fail"),
                    (N, "unaware of surroundings")],
}


def test_registry_matches_the_adapters_conditions():
    # the completeness oracle: registry <-> source. A new/renamed SRD condition
    # can't slip in unclassified.
    assert set(CONDITION_EFFECTS) == set(A.names("condition"))


def test_every_modeled_clause_points_at_a_real_atom():
    for cond, clauses in CONDITION_EFFECTS.items():
        for status, ref in clauses:
            if status == M:
                assert ref in ATOMS, f"{cond}: unknown atom {ref}"


def test_every_deferral_names_an_unbuilt_surface():
    for cond, clauses in CONDITION_EFFECTS.items():
        for status, ref in clauses:
            if status == D:
                assert ref in ALLOWED_DEFERRALS, \
                    f"{cond}: deferral reason {ref!r} is not a recognized " \
                    "unbuilt surface (is it really just unbuilt?)"


def test_every_condition_has_at_least_one_modeled_clause_or_is_pure_deferral():
    # a condition that is ALL deferral/no-effect is allowed only if it genuinely
    # has no attack/economy-surface effect (Deafened). Everything else must model
    # something — otherwise it's a silent gap.
    pure_deferral_ok = {"Deafened"}
    for cond, clauses in CONDITION_EFFECTS.items():
        modeled = any(s == M for s, _ in clauses)
        assert modeled or cond in pure_deferral_ok, \
            f"{cond}: nothing modeled and not a known no-mechanical-surface case"


def test_no_condition_is_silently_refused_on_built_surfaces():
    # the heart of it: for every SRD condition, the two built surfaces return a
    # real verdict (or a NAMED deferral), never the generic "not modeled" refusal.
    for cond in A.names("condition"):
        for probe in ({"attacker": {"conditions": [cond]}, "target": {},
                       "distance_ft": 5},
                      {"attacker": {}, "target": {"conditions": [cond]},
                       "distance_ft": 5}):
            r = E.query("attack.modifiers", probe)
            assert "not modeled" not in r.why, f"attack.modifiers silently refuses {cond}"
        tp = E.query("turn.plan",
                     {"speed": 30, "conditions": [cond], "plan": [{"do": "action"}]})
        assert "not modeled" not in tp.why, f"turn.plan silently refuses {cond}"


def test_deferred_conditions_refuse_with_their_named_reason():
    # Exhaustion is the one turn-economy deferral; it must give its reason, not
    # the generic refusal.
    tp = E.query("turn.plan",
                 {"speed": 30, "conditions": ["Exhaustion"],
                  "plan": [{"do": "action"}]})
    assert tp.exit_code == 2 and "graduated" in tp.why
