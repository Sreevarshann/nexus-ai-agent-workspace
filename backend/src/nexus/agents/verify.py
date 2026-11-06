"""Deterministic citation and numeric-claim verification.

This does not ask the model to grade itself. For each cited sentence it checks that:
* every cited label exists in the evidence that was actually retrieved (fabricated labels are removed),
* the sentence shares enough content words with the cited passages (lexical support),
* every number in the sentence appears in the cited passages or in computed data results; calendar years and
  discrete counts (including written counts such as "three") must match exactly, and sign and percent must agree.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

_LABEL = re.compile(r"\[((?:S|D)\d+)\]")
# A "-" or U+2212 minus directly before the digits is a sign unless it follows a word or number (ranges, "COVID-19").
_NUM = re.compile(r"(?:(?<![\w.])([-\u2212+]))?(?<![\w.])(\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?(?:[eE][-+]?\d+)?)")
_PERCENT_AFTER = re.compile(r"\s?%|\s+per\s?cent\b", re.IGNORECASE)
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
# In a claim, "one" is a count only when the next word could be what it counts ("one commercial site"). It is not
# one when hyphenated ("one-off"), last in its phrase ("the best one."), after a determiner ("no one", "the one
# that"), or before one of these words ("one of", "one another", "one must").
_ONE_BEFORE = frozenset(["no", "any", "every", "each", "some", "the", "this", "that", "which", "such", "another"])
_ONE_AFTER_WORDS = "of another or and nor but who whom whose that which is was are were has had have can could would"
_ONE_AFTER = frozenset((_ONE_AFTER_WORDS + " should may might must will shall does did").split())
_WORD_BEFORE = re.compile(r"([A-Za-z]+)\s+$")
_WORD_AFTER = re.compile(r"\s+([A-Za-z]+)")
_CURRENCY = ("$", "€", "£")
_PERCENT_NAME = re.compile(r"%|(?<![a-z])(?:pct|percent|percentage)(?![a-z])", re.IGNORECASE)
_INSIGHT_ITEM = re.compile(r'"([^"]+)": (-?[\d.]+(?:[eE][-+]?\d+)?)')
_UNIT_AFTER = re.compile(r"\s?([A-Za-z]+)")
# An integer followed by one of these is a measurement (which may be rounded), not a discrete count.
_UNIT_WORDS = "kg g mg t tonnes tons lb lbs km m cm mm metres meters metre meter square sq kw mw gw kwh mwh gwh"
_UNITS = frozenset(
    (_UNIT_WORDS + " w wh v kv ah mah h hr hrs hours min minutes s sec seconds ms l litres liters ml mph").split()
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
    resolution: Decimal  # one unit in the last displayed digit: 1 for "91", 0.1 for "91.3", 10000 for "2.007e+07"
    exact: bool  # years and discrete counts only match an equal value
    percent: bool = False
    data: bool = False  # a value in a computed data result, displayed at four significant figures
    declared_percent: bool = False  # a data value whose column or insight name declares a percentage


def _is_count(raw: str, text: str, start: int, end: int) -> bool:
    """A bare integer below 1000 with no percent, currency or measurement unit is read as a discrete count."""
    if not raw.isdigit() or Decimal(raw) >= 1000 or text[start - 1 : start] in _CURRENCY:
        return False
    unit = _UNIT_AFTER.match(text, end)
    return not (unit and unit.group(1).lower() in _UNITS)


def _one_is_count(text: str, start: int, end: int) -> bool:
    before, after = _WORD_BEFORE.search(text, 0, start), _WORD_AFTER.match(text, end)
    if text[end : end + 1] == "-" or after is None or after.group(1).lower() in _ONE_AFTER:
        return False
    return before is None or before.group(1).lower() not in _ONE_BEFORE


def _declared_percent_spans(text: str) -> list[tuple[int, int]]:
    """Spans of data-result values whose column or insight name declares a percentage ("growth_pct", "Share (%)").

    Relies on the result_text() layout: a title line, a " | "-separated header line, one line per row, and an
    optional "insights: {json}" line.
    """
    lines = text.split("\n")
    if len(lines) < 2:
        return []
    header = lines[1].split(" | ")
    percent_columns = {i for i, name in enumerate(header) if _PERCENT_NAME.search(name)}
    spans = []
    pos = len(lines[0]) + len(lines[1]) + 2
    for line in lines[2:]:
        if line.startswith("insights: "):
            items = _INSIGHT_ITEM.finditer(line)
            spans += [(pos + m.start(2), pos + m.end(2)) for m in items if _PERCENT_NAME.search(m.group(1))]
        elif percent_columns and len(cells := line.split(" | ")) == len(header):
            start = pos
            for i, cell in enumerate(cells):
                if i in percent_columns:
                    spans.append((start, start + len(cell)))
                start += len(cell) + 3
        pos += len(line) + 1
    return spans


def _quantities(text: str, *, claim: bool, data: bool = False) -> list[_Quantity]:
    out = []
    declared = _declared_percent_spans(text) if data else []
    for m in _NUM.finditer(text):
        raw = m.group(2).replace(",", "")
        sign = "-" if m.group(1) in ("-", "\u2212") else ""
        percent = bool(_PERCENT_AFTER.match(text, m.end()))
        exact = bool(_YEAR.fullmatch(raw)) or (not percent and _is_count(raw, text, m.start(2), m.end()))
        shown = sign + raw + ("%" if percent else "")
        value = Decimal(sign + raw)
        resolution = Decimal(1).scaleb(int(value.as_tuple().exponent))
        in_percent_field = any(a <= m.start() < b for a, b in declared)
        out.append(_Quantity(shown, value, resolution, claim and exact, percent, data, in_percent_field))
    for m in _WORD_NUM.finditer(text):
        word = m.group(0).lower()
        if claim and word == "one" and not _one_is_count(text, m.start(), m.end()):
            continue
        tens, unit = [*word.split("-"), ""][:2] if m.group(1) else (word, "")
        percent = bool(_PERCENT_AFTER.match(text, m.end()))
        value = Decimal(_WORD_VALUES[tens] + _WORD_VALUES.get(unit, 0))
        out.append(_Quantity(word + ("%" if percent else ""), value, Decimal(1), claim, percent, data))
    return out


def _supported(q: _Quantity, cited: list[_Quantity]) -> bool:
    # 80% is not supported by a bare 80. Data results print percentages without a sign, so a bare data value
    # supports a percent claim only when its column or insight name declares a percentage.
    cited = [c for c in cited if c.percent == q.percent or (q.percent and c.declared_percent)]
    if q.exact:
        return any(c.value == q.value for c in cited)
    # A measurement may be the cited value rounded to the claim's precision (91 or 91.3 for 91.3, not 91.35).
    # Data results are themselves displayed at four significant figures, so their precision is allowed too.
    return any(abs(c.value - q.value) <= max(q.resolution, c.resolution if c.data else 0) / 2 for c in cited)


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
        cited_nums = [q for lab in valid for q in _quantities(evidence_text[lab], claim=False, data=lab[0] == "D")]
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
