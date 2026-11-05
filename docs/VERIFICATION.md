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
  supported by `80 percent`. There is one exception, for computed data results (`[D#]`). Their values never
  carry a percent sign, so a percent claim may be supported by a bare value in a data result, such as a
  `growth_pct` column.
* **Data-result precision.** `result_text()` renders floats with four significant figures, so a revenue of
  20068214.8 reaches the verifier as `2.007e+07`. For `[D#]` evidence, a measurement may also differ by up to half
  a unit in the evidence's last digit. So `20,068,215` is supported by `2.007e+07`, but `20,100,000` is not.
* **"one" is not checked in claims**, because it is usually a pronoun or determiner ("one of the sites", "no one").
  It still counts in evidence, so a claim of "1 control room" is supported by "one control room".

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

* `pytest tests/test_verify.py`: 33 passed. Against the previous verifier, 17 of them fail: the year, count,
  written-count, list-marker, sign, percent, rounding and scientific-notation cases. One of the 17,
  `test_wrong_numbers_are_flagged`, fails only because of the `97.5` → `97.5%` report format change.
* `citation_grounding` has 19 known-answer cases, up from 6. With the previous verifier, accuracy is 0.684
  (13/19) and `evals.run --offline` exits 1. With this branch, accuracy is 1.0 and the run exits 0. The threshold
  is unchanged: accuracy ≥ 1.0.
* `pytest -m offline`: 77 passed with no services.
* Full backend suite against a throwaway pgvector container: 174 passed.
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
  `12.5`. A bare value in a data result can't be told apart from a percent, so percent claims are allowed
  against it.
* **Ordinals and dates.** Digit ordinals such as `4th` are read as the count 4. Ordinal words are not read at
  all. An ISO date's month and day are separate counts.
* **The comparison matrix is not covered.** In compare missions, chart values in the comparison matrix are
  checked by `_number_in_text()` in `nexus/agents/graph.py`. That check still uses the old relative tolerance.
  It is a separate path with structured `numeric_value` fields and is a candidate follow-up.
