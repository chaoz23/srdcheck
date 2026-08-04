"""Operational ownership artifacts stay explicit and linked (issue #42)."""

import pathlib
import re


ROOT = pathlib.Path(__file__).resolve().parents[1]


def read(path):
    return (ROOT / path).read_text(encoding="utf-8")


def normalized(path):
    return re.sub(r"\s+", " ", read(path)).lower()


def test_takeover_packet_keeps_unverified_human_gates_visible():
    takeover = normalized("docs/TAKEOVER.md")
    for required in (
        "protected transaction-room ledger",
        "unresolved; do not silently attribute",
        "not private identity or contact evidence",
        "at least 30 calendar days",
        "second-maintainer release drill",
        "not ready to close",
    ):
        assert required in takeover


def test_operational_runbooks_and_release_contract_are_linked():
    architecture = read("docs/ARCHITECTURE-OPERATIONS.md")
    for path in (
        "docs/RELEASE.md",
        "docs/INCIDENT-RESPONSE.md",
        "docs/SUPPORT.md",
        "docs/release-contract.md",
        "docs/product-truths.md",
    ):
        assert path in architecture
        assert (ROOT / path).is_file()


def test_codeowners_and_pr_template_make_accountability_explicit():
    owners = read(".github/CODEOWNERS")
    template = normalized(".github/PULL_REQUEST_TEMPLATE.md")
    assert "* @chaoz23" in owners
    assert "does not constitute independent review" in read(
        "docs/ARCHITECTURE-OPERATIONS.md")
    assert "human maintainer accountable" in template
    assert "benchmark questions/golds" in template
