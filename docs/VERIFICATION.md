# Numeric claim verification

`verify_report()` in `backend/src/nexus/agents/verify.py` checks each cited sentence of a report against the
evidence its labels point to: `[S#]` source passages and `[D#]` computed data results. It removes labels that do
not exist, scores lexical support, and checks every number in the sentence. This page describes the numeric
check. It is deterministic, needs no services or models, and only compares numbers: a sentence whose numbers all
appear in its evidence is not thereby proven true.

## How a number is checked

1. Citation labels are removed from the sentence, and so is a leading ordered-list marker such as `4)` or `5.`, so
   neither is read as a quantity.
2. Every number in the sentence is parsed into a quantity: value, sign, percent or not, displayed precision, and
   a kind (calendar year, discrete count or measurement).
3. The cited evidence is parsed the same way.
4. Each quantity in the sentence must be matched by at least one cited quantity under the rules below. Any that
   are not matched are listed in `unmatched_numbers`, and the claim is `unsupported`.

Each number is matched independently against all numbers in the cited evidence. The verifier does not check
which entity a number belongs to.

## Supported formats

| Format | Examples | Parsed as |
|---|---|---|
| Integers and decimals | `540`, `0.9`, `91.30` | the value, with the precision as written |
| Comma-grouped | `6,000`, `20,068,215`, `1,250.5` | same as `6000`, `20068215`, `1250.5` |
| Scientific notation | `2.007e+07` | 20 070 000 with four significant figures (data results use this, see below) |
| Sign | `-12%`, `−3.2` (U+2212), `+5` | negative only when `-` or `−` directly precedes the digits and does not follow a word or number, so `2019-2024` and `COVID-19` are not negative |
| Percent | `80%`, `80 %`, `80 percent`, `80 per cent` | a percent value |
| Written counts | `three`, `Twenty-Five`, `ninety-nine` | zero to ninety-nine; hyphenated compounds only |

Not recognised: written numbers above ninety-nine, ordinal words (`third`), fractions, scale words (`20 million`),
leading-decimal forms (`.5`), and numbers glued to letters (`Q1`, `FY2024`, `v2`), which are ignored as before.

## Comparison policy

| Kind | Recognised as | Matches a cited value when |
|---|---|---|
| Calendar year | 1800–2199 written without separators, not a percent | it is exactly equal |
| Discrete count | a written count, or a bare integer below 1000 with no percent sign, currency symbol (`$ € £`) or measurement unit after it | it is exactly equal |
| Measurement | everything else: decimals, percents, currency amounts, integers of 1000 or more, and integers followed by a unit (`kg`, `kWh`, `MW`, `m`, `hours`, …) | it is the cited value rounded to the claim's own precision: \|claim − cited\| ≤ half a unit in the claim's last digit |

These rules apply to every kind:

* **Sign must agree.** `12%` is not supported by `-12%`, and `-80` is not supported by `80`.
* **Percent must agree.** `80%` is not supported by a bare `80` (for example "80 units"), and a bare `80` is not
  supported by `80 percent`. Computed data results (`[D#]`) carry no unit metadata and print percentages without
  a sign. So a bare data value supports a percent claim only when the result itself declares it a percentage:
  its column name or insight key contains `%` or the separate token `pct`, `percent` or `percentage` (for
  example `growth_pct`, `Share (%)`, `change_first_to_last_pct`). Data values printed with `%` match as they do
  in source text. Otherwise the percent claim is rejected: neither the `D` label nor the value's range nor a
  matching value is taken as evidence. A declared-percent value still supports the bare number it displays
  ("growth_pct was 12.5").
* **Data-result precision.** `result_text()` renders floats with four significant figures, so a revenue of
  20068214.8 reaches the verifier as `2.007e+07`. For `[D#]` evidence, a measurement may also differ by up to half
  a unit in the evidence's last digit. So `20,068,215` is supported by `2.007e+07`, but `20,100,000` is not.
* **Written "one" is checked only when it counts something.** In a claim, "one" is a count when the next word
  could be what it counts: "one commercial site" against "three commercial sites" is flagged, just like "1
  commercial site". It is skipped in these cases:
  * it is hyphenated ("one-off");
  * it ends its phrase ("the best one.");
  * it follows a determiner ("no one", "the one that"; the list is `no any every each some the this that which
    such another`);
  * it comes before a pronoun, conjunction, relative word or auxiliary ("one of", "one another", "one that",
    "one must").

  This is a bounded word-list rule, not a parser. In evidence "one" always counts, so "1 control room" is
  supported by "one control room".

Examples:

* `91%` and `91.30%` are supported by `91.3 percent`, but `92%` and `91.34%` are not.
* `1,251 kWh` is supported by `1,250.5 kWh`, but `1,252 kWh` is not.
* `2023` is not supported by `2024`.
* `2 sites` is not supported by `1.98 operators`.
* `3 sites` is supported by `three sites`.

## Before and after

Here is the actual output of `verify_report()` on `main` at `f4985a1`, before this change, and on this branch.
Each sentence cites evidence that it otherwise supports well, so the number alone decides the verdict.

Evidence used:

* `S1`: "In a 14-month pilot at three sites, round-trip efficiency averaged 91.3 percent."
* `S4`: "… began commercial deliveries in 2024, two years after its pilot started in 2022."
* `S5`: "Cell costs changed by -12% in 2024 while installed storage capacity grew by 35%."
* `S6`: "A cabinet weighs 540 kg and is rated for 6,000 cycles."
* `D1`: "North | 2.007e+07", from `result_text()`.

| Claim | Before | After |
|---|---|---|
| … began commercial deliveries in 2019 [S4] | supported | unsupported, `2019` |
| … began commercial deliveries in 2023 [S4] | supported | unsupported, `2023` |
| The pilot ran at 2 sites … [S1] | supported | unsupported, `2` |
| The pilot ran at 3 sites … [S1] | supported, because 1–3 were never checked | supported, 3 = "three" |
| The pilot ran at four sites … [S1] | supported | unsupported, `four` |
| … efficiency averaged 91 percent [S1] | supported | supported |
| … efficiency averaged 91.34 percent [S1] | supported | unsupported, `91.34%` |
| A cabinet weighs 542 kg [S6] | supported, within 0.5% | unsupported, `542` |
| A cabinet is rated for 6000 cycles [S6] | supported | supported |
| Cell costs changed by 12% in 2024 [S5] | supported | unsupported, `12%` |
| North revenue reached 20,068,215 by region [D1] | unsupported, `20068215` | supported |
| 4) The pilot ran at three sites with 91.3 percent … [S1] | unsupported, `4` | supported |

The review of `67bf771` found two more false positives, which are now fixed. Before and after on this branch:

| Claim | Evidence | `67bf771` | Now |
|---|---|---|---|
| The pilot ran at one commercial site [S1] | "The pilot ran at three commercial sites." | supported | unsupported, `one` |
| The warehouse recorded 80 percent occupied capacity [D1] | `occupied capacity \| units` / `80 \| boxes` | supported | unsupported, `80%` |

To reproduce a row, run:

```bash
cd backend && uv run python -c 'from nexus.agents.verify import verify_report; print(verify_report(
  "Northwind Energy Labs began commercial deliveries in 2023 [S4].",
  {"S4": "Northwind Energy Labs began commercial deliveries in 2024, two years after its pilot started in 2022."}
)[1]["claims"][0])'
```

Removing the old year exemption would not have been enough on its own. The previous tolerance,
`max(0.5% of the cited value, 0.051)`, puts 2019 within ten years of 2024.

## Report format

The public interface and the report fields are unchanged. `unmatched_numbers` is still a sorted list of strings.
Each entry is written as the claim's value without comma grouping, with a leading `-` for negative values and a
trailing `%` for percents. Written counts appear as the word. Examples: `"2019"`, `"-80"`, `"97.5%"`, `"four"`.
Before this change, percents lost their `%`, so the old `"97.5"` is now `"97.5%"`. The API and frontend read only
the count fields (`claims_checked`, `supported`, `weak`, `unsupported`), and those are unchanged.

## Validation

All of these were run on this branch:

* `pytest tests/test_verify.py`: 39 passed. Against `f4985a1`, 21 of them fail: the year, count, written-count,
  list-marker, sign, percent, rounding, scientific-notation, written-"one" and data-percent cases. One of the 21,
  `test_wrong_numbers_are_flagged`, fails only because of the `97.5` → `97.5%` report format change. Against
  `67bf771`, the first review head, 4 fail: the written-"one" and data-percent cases.
* `citation_grounding` has 25 known-answer cases, up from 6. Accuracy on the earlier verifiers:
  * `f4985a1`: 0.684 on the first 19 cases; `evals.run --offline` exits 1.
  * `67bf771`: 0.92 (23/25); exits 1.
  * this branch: 1.0; exits 0.

  The threshold is unchanged: accuracy ≥ 1.0.
* `pytest -m offline`: 83 passed with no services.
* Full backend suite against a throwaway pgvector container: 180 passed.
* ruff, ruff format and mypy are clean.

None of this involved a real model.

## Limitations

* **Numbers, not meaning.** A matching number does not prove the claim. The verifier does not associate a value
  with its entity or unit, so "capacity grew by -12% [S5]" is supported because `-12%` appears in S5, even
  though S5 says costs changed by -12%. It does not detect contradictions or check uncited sentences, and it does
  no unit conversion (`1.5 MWh` and `1,500 kWh` do not match).
* **Count versus measurement is a heuristic.** A bare integer below 1000 without a recognised unit is treated as
  a count and must match exactly. So "averaged 5 cycles per day" is not supported by "4.97 cycles": "cycles" is
  not a unit, and the claim is flagged. The unit list is short and English-only.
* **Data results.** The `[D#]` allowance uses the precision of the value as displayed. It cannot tell a float
  that `result_text()` rounded from a value that was already exact, so `12.46` is accepted against a displayed
  `12.5`.
* **Percent meaning in data rests on names.** A percentage column is only recognised if its name says so:
  `occupancy_rate` holding percentages is not recognised, so a correct percent claim against it is flagged. A
  misleadingly named column is trusted. Columns are located by the `result_text()` layout (title line, `" | "`
  header line, one line per row), so a cell value that itself contains `" | "` breaks the alignment for that
  row, and the percent claim is then rejected.
* **Written "one".** The word lists are short and English-only. Unlisted uses can still be read as counts, for
  example "one day" in "one day the site failed".
* **Ordinals and dates.** Digit ordinals such as `4th` are read as the count 4. Ordinal words are not read at
  all. An ISO date's month and day are separate counts.
* **The comparison matrix is not covered.** In compare missions, chart values in the comparison matrix are
  checked by `_number_in_text()` in `nexus/agents/graph.py`. That check still uses the old relative tolerance.
  It is a separate path with structured `numeric_value` fields and is a candidate follow-up.
