"""Verdict envelope. Content-neutral: no game terms live in this package (T7)."""

from dataclasses import dataclass, field

LEGAL = 0
ILLEGAL = 1
CANNOT_ADJUDICATE = 2

_NAMES = {LEGAL: "legal", ILLEGAL: "illegal", CANNOT_ADJUDICATE: "cannot-adjudicate"}


@dataclass
class Citation:
    section: str
    page: int | None = None
    quote: str | None = None

    def as_dict(self):
        d = {"section": self.section}
        if self.page is not None:
            d["page"] = self.page
        if self.quote:
            d["quote"] = self.quote
        return d


@dataclass
class Verdict:
    exit_code: int
    why: str
    citations: list[Citation] = field(default_factory=list)
    adapter: str = ""
    rule_ids: list[str] = field(default_factory=list)

    @property
    def verdict(self):
        return _NAMES[self.exit_code]

    def as_dict(self):
        return {
            "verdict": self.verdict,
            "exit_code": self.exit_code,
            "why": self.why,
            "citations": [c.as_dict() for c in self.citations],
            "rule_ids": self.rule_ids,
            "adapter": self.adapter,
        }


def legal(why, citations=(), adapter="", rule_ids=()):
    return Verdict(LEGAL, why, list(citations), adapter, list(rule_ids))


def illegal(why, citations=(), adapter="", rule_ids=()):
    return Verdict(ILLEGAL, why, list(citations), adapter, list(rule_ids))


def cannot_adjudicate(why, citations=(), adapter="", rule_ids=()):
    return Verdict(CANNOT_ADJUDICATE, why, list(citations), adapter, list(rule_ids))
