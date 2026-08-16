"""Query handlers for the srd-5.2.1 adapter.

Game logic lives here, in the adapter — never in the kernel (truth T7).
Handlers read their facts from rule atoms (parameters + citations); the
control flow below is the code escape hatch the adapter spec allows.

This package is the handler registry only. Each rule domain owns one module;
see its docstring for the queries it answers. `common` is the shared base and
depends on no sibling.
"""

from srdcheck.adapter import Handler

from .content import feature_uses, mage_hand_use, spell_facts
from .turn import reaction_available, turn_options, turn_plan
from .rolls import attack_modifiers, roll_compose
from .checks import check_make, concentration_check, save_check
from .state import event_apply, transition_commit
from .creatures import creature_stats, creature_valid, encounter_xp_budget
from .actions import (grapple_initiate, help_assist,
                      opportunity_attack_provoked, passive_perception)


HANDLERS: dict[str, Handler] = {
    "spell.facts": spell_facts,
    "feature.uses": feature_uses,
    "mage-hand.use": mage_hand_use,
    "turn.plan": turn_plan,
    "turn.options": turn_options,
    "reaction.available": reaction_available,
    "roll.compose": roll_compose,
    "attack.modifiers": attack_modifiers,
    "event.apply": event_apply,
    "transition.commit": transition_commit,
    "creature.valid": creature_valid,
    "creature.stats": creature_stats,
    "encounter.xp-budget": encounter_xp_budget,
    "save.check": save_check,
    "check.make": check_make,
    "concentration.check": concentration_check,
    "opportunity-attack.provoked": opportunity_attack_provoked,
    "grapple.initiate": grapple_initiate,
    "passive.perception": passive_perception,
    "help.assist": help_assist,
}
