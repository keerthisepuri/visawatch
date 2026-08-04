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


# A real slot report reads "BULK SLOTS DROPPED HYD" - the what, the event and the
# city land within a few words of each other. A long discussion post that happens
# to contain "slots" in one paragraph and "open" in another is not a slot report.
# Requiring the three groups to appear close together is what separates the two.
PROXIMITY_WORDS = 20
QUESTION_MARKERS = (
    "anyone able", "is it possible", "can i get", "can i book", "how do i",
    "how can i", "when will", "does anyone know", "any idea", "any luck",
    "should i", "what are the chances", "is there any chance", "please help",
    "need help", "any suggestions", "has anyone",
)


@dataclass
class MatchResult:
    matched: bool
    group_a: list[str]
    group_b: list[str]
    group_c: list[str]
    boost: list[str]
    excluded_by: list[str]
    is_question: bool = False

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


def looks_like_a_question(text: str) -> bool:
    """Questions and 'my experience' write-ups are not slot drops."""
    first_line = (text or "").strip().split("\n", 1)[0]
    if first_line.rstrip().endswith("?"):
        return True
    spaced = normalize(text)
    return any(marker in spaced for marker in QUESTION_MARKERS)


def match(text: str, cfg) -> MatchResult:
    spaced, tight = normalize(text), tighten(text)

    excluded = _hits(spaced, tight, cfg.exclude)
    if excluded:
        return MatchResult(False, [], [], [], [], excluded)

    question = looks_like_a_question(text)
    boost = _hits(spaced, tight, cfg.boost)

    words = spaced.split()
    hits = {
        "a": _positions(words, cfg.group_a),
        "b": _positions(words, cfg.group_b),
        "c": _positions(words, cfg.group_c),
    }
    a_all = sorted({ph for _, ph in hits["a"]})
    b_all = sorted({ph for _, ph in hits["b"]})
    c_all = sorted({ph for _, ph in hits["c"]})

    # The window decides whether this is a slot report; the reported keywords are
    # everything found, so the alert text stays informative.
    matched = _closest_window(hits) is not None
    return MatchResult(matched, a_all, b_all, c_all, boost, [], question)


def _positions(words: list[str], phrases: list[str]) -> list[tuple[int, str]]:
    """Where each configured phrase occurs, as a word index."""
    found: list[tuple[int, str]] = []
    for phrase in phrases:
        target = normalize(phrase).split()
        tight_target = tighten(phrase)
        if not target:
            continue
        n = len(target)
        for i in range(len(words) - n + 1):
            chunk = words[i:i + n]
            if chunk == target or (n == 1 and tighten(chunk[0]) == tight_target):
                found.append((i, phrase))
    return found


def _closest_window(hits: dict) -> dict | None:
    """Is there a span of PROXIMITY_WORDS words containing all three groups?"""
    events = sorted(
        [(pos, group, phrase) for group, plist in hits.items() for pos, phrase in plist]
    )
    if not events or not all(hits.values()):
        return None

    best = None
    for start in range(len(events)):
        groups: dict[str, list[str]] = {}
        span = 0
        for end in range(start, len(events)):
            pos, group, phrase = events[end]
            if pos - events[start][0] > PROXIMITY_WORDS:
                break
            if phrase not in groups.setdefault(group, []):
                groups[group].append(phrase)
            if len(groups) == 3:
                span = pos - events[start][0]
        if len(groups) == 3 and (best is None or span < best[0]):
            best = (span, {g: list(p) for g, p in groups.items()})
    return best[1] if best else None
