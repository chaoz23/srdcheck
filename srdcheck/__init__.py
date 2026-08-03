"""srdcheck — deterministic rules verdicts for game-running agents.

Kernel package: content-neutral (truth T7). Rule content lives in adapters.
"""

def _detect_version():
    """The single source of engine version truth.

    Both answers derive from pyproject's `version`; only the route differs.
    A source checkout is authoritative about itself, so it is checked FIRST:
    importlib.metadata would otherwise report some older srdcheck installed in
    the same interpreter while Python is actually importing this tree. An
    installed wheel has no adjacent pyproject.toml and falls through to
    package metadata.

    Never hardcode a second version literal here — that drift is exactly what
    shipped 0.5.0 with an MCP server announcing itself as 0.2.0.
    """
    import pathlib
    import re
    pyproject = pathlib.Path(__file__).resolve().parent.parent / "pyproject.toml"
    try:
        m = re.search(r'^version\s*=\s*"([^"]+)"',
                      pyproject.read_text(encoding="utf-8"), re.M)
        if m:
            return m.group(1)
    except OSError:
        pass
    from importlib.metadata import PackageNotFoundError, version
    try:
        return version("srdcheck")
    except PackageNotFoundError:
        return "0+unknown"


__version__ = _detect_version()

from .access import (  # noqa: E402,F401
    AdapterHandle, available_adapters, capabilities, edition_check, load_adapter,
)
from .verdict import (  # noqa: F401
    CANNOT_ADJUDICATE, ILLEGAL, LEGAL,
    Citation, Verdict, cannot_adjudicate, illegal, legal,
)
from .table_evaluation import (TABLE_EVALUATION_SCHEMA_VERSION,
                               project_table_evaluation)  # noqa: F401
from .provenance import (ASSERTED_FACTS_SCHEMA,
                         TABLE_DECISION_SCHEMA)  # noqa: F401
from .house_rules import (MANIFEST_SCHEMA, MANIFEST_SCHEMA_ID,
                          POLICY_CONTEXT_SCHEMA, export_manifest,
                          import_manifest, resolve_policy)  # noqa: F401
from .observability import (OBSERVABILITY_SCHEMA_VERSION, JsonLineSink,
                            ObservedResult, observability_contract,
                            observe_query, verdict_id)  # noqa: F401
