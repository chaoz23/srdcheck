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
    data: dict = field(default_factory=dict)

    @property
    def verdict(self):
        return _NAMES[self.exit_code]

    def as_dict(self):
        d = {
            "verdict": self.verdict,
            "exit_code": self.exit_code,
            "why": self.why,
            "citations": [c.as_dict() for c in self.citations],
            "rule_ids": self.rule_ids,
            "adapter": self.adapter,
        }
        if self.data:
            d["data"] = self.data
        return d


def legal(why, citations=(), adapter="", rule_ids=(), data=None):
    return Verdict(LEGAL, why, list(citations), adapter, list(rule_ids),
                   data or {})


def illegal(why, citations=(), adapter="", rule_ids=()):
    return Verdict(ILLEGAL, why, list(citations), adapter, list(rule_ids))


def cannot_adjudicate(why, citations=(), adapter="", rule_ids=()):
    return Verdict(CANNOT_ADJUDICATE, why, list(citations), adapter, list(rule_ids))
