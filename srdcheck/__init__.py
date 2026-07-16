"""srdcheck — deterministic rules verdicts for game-running agents.

Kernel package: content-neutral (truth T7). Rule content lives in adapters.
"""

from .verdict import (  # noqa: F401
    CANNOT_ADJUDICATE, ILLEGAL, LEGAL,
    Citation, Verdict, cannot_adjudicate, illegal, legal,
)
