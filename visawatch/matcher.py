"""Keyword matching.

An item matches when it contains at least one word from each of the three
configured groups. Matching ignores capitals and punctuation, so "H-1B",
"h1b" and "H.1.B" are treated identically.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_PUNCT = re.compile(r"[^0-9a-z\s]+")
_SPACE = re.compile(r"\s+")


def normalize(text: str) -> str:
    """Punctuation becomes a space, so 'HYD/DEL slots' and 'dropped!!Hyderabad'
    still split into words."""
    return _SPACE.sub(" ", _PUNCT.sub(" ", (text or "").lower())).strip()


def tighten(text: str) -> str:
    """Punctuation is deleted instead, so 'H-1B' and 'H.1.B' both become 'h1b'."""
    return _SPACE.sub(" ", _PUNCT.sub("", (text or "").lower())).strip()


def _word_in(haystack: str, needle: str) -> bool:
    if not needle:
        return False
    return re.search(rf"(?<![0-9a-z]){re.escape(needle)}(?![0-9a-z])", haystack) is not None


def _contains(spaced: str, tight: str, phrase: str) -> bool:
    """A phrase hits if it appears in either normalised form. The two forms are
    complementary: the spaced one catches 'Delhi/Mumbai', the tight one catches
    'H-1B'."""
    return _word_in(spaced, normalize(phrase)) or _word_in(tight, tighten(phrase))


def _hits(spaced: str, tight: str, phrases: list[str]) -> list[str]:
    return [p for p in phrases if _contains(spaced, tight, p)]


@dataclass
class MatchResult:
    matched: bool
    group_a: list[str]
    group_b: list[str]
    group_c: list[str]
    boost: list[str]
    excluded_by: list[str]

    @property
    def high_priority(self) -> bool:
        return bool(self.boost)

    @property
    def all_keywords(self) -> list[str]:
        return self.group_a + self.group_b + self.group_c + self.boost

    def summary(self) -> str:
        parts = [
            f"what: {', '.join(self.group_a) or '-'}",
            f"event: {', '.join(self.group_b) or '-'}",
            f"where: {', '.join(self.group_c) or '-'}",
        ]
        if self.boost:
            parts.append(f"boost: {', '.join(self.boost)}")
        return " | ".join(parts)


def match(text: str, cfg) -> MatchResult:
    spaced, tight = normalize(text), tighten(text)

    excluded = _hits(spaced, tight, cfg.exclude)
    if excluded:
        return MatchResult(False, [], [], [], [], excluded)

    a = _hits(spaced, tight, cfg.group_a)
    b = _hits(spaced, tight, cfg.group_b)
    c = _hits(spaced, tight, cfg.group_c)
    boost = _hits(spaced, tight, cfg.boost)

    return MatchResult(bool(a and b and c), a, b, c, boost, [])
