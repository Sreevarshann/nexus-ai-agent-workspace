"""Deterministic citation and numeric-claim verification.

This does not ask the model to grade itself. For each cited sentence it checks that:
* every cited label exists in the evidence that was actually retrieved (fabricated labels are removed),
* the sentence shares enough content words with the cited passages (lexical support),
* every number in the sentence appears in the cited passages or in computed data results; calendar years must
  match exactly.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

_LABEL = re.compile(r"\[((?:S|D)\d+)\]")
_NUM = re.compile(r"(?<![\w.])(\d{1,3}(?:,\d{3})+|\d+(?:\.\d+)?)(%?)")
_YEAR = re.compile(r"(?:1[89]|2[01])\d\d")  # 1800-2199 written without separators
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


def _numbers(text: str) -> set[str]:
    return {m.group(1).replace(",", "") for m in _NUM.finditer(text)}


def _num_in(n: str, haystack_nums: set[str]) -> bool:
    if n in haystack_nums:
        return True
    if _YEAR.fullmatch(n):
        return False  # a calendar year is exact: 2019 must not pass as a rounding of 2024
    try:
        v = float(n)
    except ValueError:
        return False
    for h in haystack_nums:
        try:
            hv = float(h)
        except ValueError:
            continue
        if abs(hv - v) <= max(0.005 * abs(hv), 0.051):  # allow display rounding
            return True
    return False


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
        body = _LABEL.sub("", sent)
        sw = _words(body)
        cited = " ".join(evidence_text[lab] for lab in valid)
        support = len(sw & _words(cited)) / len(sw) if sw and valid else 0.0
        nums = {n for n in _numbers(body) if n not in {"1", "2", "3"}}
        cited_nums = _numbers(cited)
        unmatched = sorted(n for n in nums if not _num_in(n, cited_nums))
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
