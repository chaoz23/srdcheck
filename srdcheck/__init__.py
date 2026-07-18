"""srdcheck — deterministic rules verdicts for game-running agents.

Kernel package: content-neutral (truth T7). Rule content lives in adapters.
"""

from .access import (  # noqa: F401
    AdapterHandle, available_adapters, edition_check, load_adapter,
)
from .verdict import (  # noqa: F401
    CANNOT_ADJUDICATE, ILLEGAL, LEGAL,
    Citation, Verdict, cannot_adjudicate, illegal, legal,
)
