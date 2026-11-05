"""Deterministic citation and numeric-claim verification.

This does not ask the model to grade itself. For each cited sentence it checks that:
* every cited label exists in the evidence that was actually retrieved (fabricated labels are removed),
* the sentence shares enough content words with the cited passages (lexical support),
* every number in the sentence appears in the cited passages or in computed data results; calendar years and
  discrete counts (including written counts such as "three") must match exactly.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

_LABEL = re.compile(r"\[((?:S|D)\d+)\]")
_NUM = re.compile(r"(?<![\w.])(\d{1,3}(?:,\d{3})+|\d+(?:\.\d+)?)(%?)")
_YEAR = re.compile(r"(?:1[89]|2[01])\d\d")  # 1800-2199 written without separators
_LIST_MARKER = re.compile(r"^(?:[-*+]\s+)?\d{1,3}[.)]\s+")
# Written counts from zero to ninety-nine; larger written numbers and ordinals are not recognised.
_SMALL_WORDS = "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen"
_SMALL = (_SMALL_WORDS + " seventeen eighteen nineteen").split()
_TENS_WORDS = "twenty thirty forty fifty sixty seventy eighty ninety"
_TENS = _TENS_WORDS.split()
_WORD_VALUES = {w: i for i, w in enumerate(_SMALL)} | {w: 20 + 10 * i for i, w in enumerate(_TENS)}
_WORD_NUM = re.compile(
    rf"\b(?:({'|'.join(_TENS)})(?:-(?:{'|'.join(_SMALL[1:10])}))?|(?:{'|'.join(_SMALL)}))\b", re.IGNORECASE
)
_CURRENCY = ("$", "€", "£")
_UNIT_AFTER = re.compile(r"\s?([A-Za-z]+)")
# An integer followed by one of these is a measurement (which may be rounded), not a discrete count.
_UNIT_WORDS = "percent kg g mg t tonnes tons lb lbs km m cm mm metres meters metre meter square sq kw mw gw kwh mwh"
_UNITS = frozenset(
    (_UNIT_WORDS + " gwh w wh v kv ah mah h hr hrs hours min minutes s sec seconds ms l litres liters ml mph").split()
)
_STOP = set(
    [
        "a",
        "an",
        "the",
        "and",
        "or",
        "but",
        "of",
        "to",
        "in",
        "on",
        "for",
        "with",
        "by",
        "from",
        "as",
        "at",
        "is",
        "are",
        "was",
        "were",
        "be",
        "been",
        "being",
        "this",
        "that",
        "these",
        "those",
        "it",
        "its",
        "their",
        "there",
        "here",
        "which",
        "who",
        "whom",
        "whose",
        "what",
        "when",
        "where",
        "why",
        "how",
        "than",
        "then",
        "also",
        "more",
        "most",
        "less",
        "least",
        "very",
        "can",
        "could",
        "may",
        "might",
        "will",
        "would",
        "should",
        "into",
        "over",
        "under",
        "about",
        "after",
        "before",
        "between",
        "across",
        "such",
        "not",
        "no",
    ]
)

SUPPORT_THRESHOLD = 0.34


@dataclass
class ClaimCheck:
    sentence: str
    labels: list[str]
    support: float
    numbers_ok: bool
    unknown_labels: list[str] = field(default_factory=list)
    unmatched_numbers: list[str] = field(default_factory=list)

    @property
    def verdict(self) -> str:
        if self.unknown_labels and not set(self.labels) - set(self.unknown_labels):
            return "unsupported"
        if self.support >= SUPPORT_THRESHOLD and self.numbers_ok:
            return "supported"
        if self.support >= SUPPORT_THRESHOLD / 2 and self.numbers_ok:
            return "weak"
        return "unsupported"


def _words(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]+", text.lower()) if len(w) > 2 and w not in _STOP}


@dataclass(frozen=True)
class _Quantity:
    text: str  # how the value is reported when it is unmatched
    value: Decimal
    exact: bool  # years and discrete counts only match an equal value


def _is_count(raw: str, text: str, start: int, end: int) -> bool:
    """A bare integer below 1000 with no percent, currency or measurement unit is read as a discrete count."""
    if "." in raw or Decimal(raw) >= 1000 or text[start - 1 : start] in _CURRENCY:
        return False
    unit = _UNIT_AFTER.match(text, end)
    return not (unit and unit.group(1).lower() in _UNITS)


def _quantities(text: str, *, claim: bool) -> list[_Quantity]:
    out = []
    for m in _NUM.finditer(text):
        raw = m.group(1).replace(",", "")
        exact = bool(_YEAR.fullmatch(raw)) or (not m.group(2) and _is_count(raw, text, m.start(), m.end()))
        out.append(_Quantity(raw, Decimal(raw), claim and exact))
    for m in _WORD_NUM.finditer(text):
        word = m.group(0).lower()
        if claim and word == "one":
            continue  # "one of the sites", "no one": too often not a quantity to check in a claim
        tens, unit = [*word.split("-"), ""][:2] if m.group(1) else (word, "")
        out.append(_Quantity(word, Decimal(_WORD_VALUES[tens] + _WORD_VALUES.get(unit, 0)), claim))
    return out


def _supported(q: _Quantity, cited: list[_Quantity]) -> bool:
    if q.exact:
        return any(c.value == q.value for c in cited)
    # allow display rounding
    return any(abs(c.value - q.value) <= max(Decimal("0.005") * abs(c.value), Decimal("0.051")) for c in cited)


def split_sentences(markdown: str) -> list[str]:
    out = []
    for line in markdown.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("|"):
            out.append(line)  # table rows are checked as one claim each
            continue
        out.extend(s.strip() for s in re.split(r"(?<=[.!?])\s+(?=[A-Z(\[])", line) if s.strip())
    return out


def verify_report(markdown: str, evidence_text: dict[str, str]) -> tuple[str, dict[str, Any]]:
    """Returns (cleaned_markdown, report). ``evidence_text`` maps label → text the label refers to."""
    known = set(evidence_text)
    checks: list[ClaimCheck] = []
    for sent in split_sentences(markdown):
        labels = list(dict.fromkeys(_LABEL.findall(sent)))
        if not labels:
            continue
        unknown = [lab for lab in labels if lab not in known]
        valid = [lab for lab in labels if lab in known]
        body = _LIST_MARKER.sub("", _LABEL.sub("", sent), count=1)
        sw = _words(body)
        cited = " ".join(evidence_text[lab] for lab in valid)
        support = len(sw & _words(cited)) / len(sw) if sw and valid else 0.0
        cited_nums = _quantities(cited, claim=False)
        unmatched = sorted({q.text for q in _quantities(body, claim=True) if not _supported(q, cited_nums)})
        checks.append(ClaimCheck(sent[:400], labels, round(support, 3), not unmatched, unknown, unmatched))

    cleaned = markdown
    removed = sorted({lab for c in checks for lab in c.unknown_labels})
    for lab in removed:
        cleaned = cleaned.replace(f"[{lab}]", "")

    counts = {"supported": 0, "weak": 0, "unsupported": 0}
    for c in checks:
        counts[c.verdict] += 1
    cited_labels = sorted({lab for c in checks for lab in c.labels if lab in known}, key=lambda s: (s[0], int(s[1:])))
    report = {
        "claims_checked": len(checks),
        **counts,
        "fabricated_labels_removed": removed,
        "cited_labels": cited_labels,
        "uncited_evidence": sorted(known - set(cited_labels), key=lambda s: (s[0], int(s[1:]))),
        "claims": [
            {
                "sentence": c.sentence,
                "labels": c.labels,
                "support": c.support,
                "verdict": c.verdict,
                "unmatched_numbers": c.unmatched_numbers,
            }
            for c in checks
        ],
        "method": "deterministic lexical-overlap and numeric-match checks against retrieved evidence",
    }
    return cleaned, report


def used_labels(markdown: str) -> set[str]:
    return set(_LABEL.findall(markdown))
