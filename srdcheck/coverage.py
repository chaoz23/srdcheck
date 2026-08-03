"""Canonical per-query coverage claims attached to every verdict path."""

import json
import pathlib

from . import verdict as v


_CLAIMS_PATH = pathlib.Path(__file__).resolve().parent / "capability_claims.json"
_QUERY_CLAIMS = {
    (item["adapter"], item["query_type"]): item
    for item in json.loads(_CLAIMS_PATH.read_text(encoding="utf-8"))[
        "query_coverage"]
}


def apply_query_scope(result, adapter, query_type):
    """Apply one canonical claim; unknown or non-verdict results stay safe."""
    if not isinstance(result, v.Verdict):
        return result
    claim = _QUERY_CLAIMS.get((adapter, query_type))
    if claim is None:
        return result
    return v.with_scope(
        result,
        coverage_level=claim["coverage_level"],
        checked_scope=claim["checked_scope"],
        unchecked_scope=claim["unchecked_scope"],
        assumptions=claim["assumptions"],
    )
