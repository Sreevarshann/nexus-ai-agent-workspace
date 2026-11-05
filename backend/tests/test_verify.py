import pytest

from nexus.agents.verify import verify_report

pytestmark = pytest.mark.offline  # pure function: runs without Postgres (pytest -m offline)

EVIDENCE = {
    "S1": "The pilot achieved round-trip efficiency of 91.3 percent across three commercial sites.",
    "S2": "The warranty covers 10 years or 6,000 cycles, guaranteeing 80 percent capacity.",
    "D1": "[D1] Revenue by region\nregion | revenue\nNorth | 20068214.8",
    "S3": "Commercial operation began in 2024 after a pilot that started in 2021.",
    "D2": "[D2] Orders by year\nyear | orders\n2023 | 412\n2024 | 455",
    "S4": "The trial used one control room for 3 sites, each staffed by an average of 1.98 operators.",
}


def test_supported_claims_pass() -> None:
    _, rep = verify_report("The pilot achieved 91.3 percent round-trip efficiency [S1].", EVIDENCE)
    assert rep["supported"] == 1 and rep["unsupported"] == 0


def test_fabricated_labels_are_removed() -> None:
    cleaned, rep = verify_report("Efficiency was 91.3 percent [S1][S9]. Something else entirely [S7].", EVIDENCE)
    assert "[S9]" not in cleaned and "[S7]" not in cleaned and "[S1]" in cleaned
    assert rep["fabricated_labels_removed"] == ["S7", "S9"]


def test_wrong_numbers_are_flagged() -> None:
    _, rep = verify_report("The pilot achieved 97.5 percent round-trip efficiency [S1].", EVIDENCE)
    claim = rep["claims"][0]
    assert claim["verdict"] == "unsupported" and claim["unmatched_numbers"] == ["97.5"]


def test_data_labels_and_rounding() -> None:
    _, rep = verify_report("North America generated 20068214.8 in revenue [D1].", EVIDENCE)
    assert rep["claims"][0]["unmatched_numbers"] == []


def test_uncited_evidence_reported() -> None:
    _, rep = verify_report("Warranty is 10 years or 6,000 cycles [S2].", EVIDENCE)
    assert "S1" in rep["uncited_evidence"]


# Behaviour the numeric checks must keep while their policy changes.


def test_comma_grouping_is_equivalent_in_both_directions() -> None:
    _, rep = verify_report("The warranty covers 6000 cycles [S2].", EVIDENCE)
    assert rep["claims"][0]["unmatched_numbers"] == []
    evidence = {"S1": "The fleet completed 6000 cycles."}
    _, rep = verify_report("The fleet completed 6,000 cycles [S1].", evidence)
    assert rep["claims"][0]["unmatched_numbers"] == []


def test_citation_label_digits_are_not_claim_quantities() -> None:
    _, rep = verify_report("The pilot achieved 91.3 percent round-trip efficiency [S1][S2].", EVIDENCE)
    assert rep["claims"][0]["unmatched_numbers"] == [] and rep["claims"][0]["verdict"] == "supported"


def test_only_fabricated_labels_make_a_claim_unsupported() -> None:
    cleaned, rep = verify_report("The pilot achieved 91.3 percent round-trip efficiency [S9].", EVIDENCE)
    assert rep["claims"][0]["verdict"] == "unsupported" and cleaned.count("[S9]") == 0


def test_every_number_in_a_claim_is_checked() -> None:
    _, rep = verify_report("The warranty covers 10 years or 6,000 cycles at 80 percent capacity [S2].", EVIDENCE)
    assert rep["claims"][0]["unmatched_numbers"] == []
    _, rep = verify_report("The warranty covers 12 years or 6,000 cycles at 80 percent capacity [S2].", EVIDENCE)
    assert rep["claims"][0]["unmatched_numbers"] == ["12"] and rep["claims"][0]["verdict"] == "unsupported"


def test_display_rounding_of_a_measurement_is_accepted() -> None:
    _, rep = verify_report("The pilot achieved 91 percent round-trip efficiency [S1].", EVIDENCE)
    assert rep["claims"][0]["unmatched_numbers"] == [] and rep["claims"][0]["verdict"] == "supported"


# Calendar years are compared exactly.


def _numbers_of(report: str) -> tuple[str, list[str]]:
    claim = verify_report(report, EVIDENCE)[1]["claims"][0]
    return claim["verdict"], claim["unmatched_numbers"]


def test_correct_year_is_supported() -> None:
    assert _numbers_of("Commercial operation began in 2024 after the pilot [S3].") == ("supported", [])


def test_wrong_year_is_flagged() -> None:
    assert _numbers_of("Commercial operation began in 2019 after the pilot [S3].") == ("unsupported", ["2019"])


def test_adjacent_year_is_not_accepted_as_rounding() -> None:
    # 2023 is within the 0.5% measurement tolerance of 2024; a year must still match exactly.
    assert _numbers_of("Commercial operation began in 2023 after the pilot [S3].") == ("unsupported", ["2023"])


def test_every_year_in_a_claim_must_be_cited() -> None:
    assert _numbers_of("The pilot started in 2021 and commercial operation began in 2024 [S3].")[1] == []
    assert _numbers_of("The pilot started in 2020 and commercial operation began in 2024 [S3].")[1] == ["2020"]


def test_years_in_data_results_match_exactly() -> None:
    assert _numbers_of("Orders by year reached 455 in 2024 [D2].") == ("supported", [])
    assert _numbers_of("Orders by year reached 455 in 2025 [D2].") == ("unsupported", ["2025"])


# Discrete counts, digits or written, are compared exactly.


def test_wrong_small_count_is_flagged() -> None:
    assert _numbers_of("The pilot ran at 2 commercial sites [S1].") == ("unsupported", ["2"])


def test_written_count_matches_its_digits() -> None:
    assert _numbers_of("The pilot ran at 3 commercial sites [S1].") == ("supported", [])
    assert _numbers_of("The trial covered three sites from a control room [S4].") == ("supported", [])
    assert _numbers_of("The trial used 1 control room for its sites [S4].") == ("supported", [])


def test_written_count_mismatch_is_flagged() -> None:
    assert _numbers_of("The pilot ran at 4 commercial sites [S1].") == ("unsupported", ["4"])
    assert _numbers_of("The trial covered four sites from a control room [S4].") == ("unsupported", ["four"])


def test_hyphenated_written_counts() -> None:
    evidence = {"S1": "The survey reached 25 utilities across the region."}
    _, rep = verify_report("The survey reached twenty-five utilities [S1].", evidence)
    assert rep["claims"][0]["unmatched_numbers"] == []
    _, rep = verify_report("The survey reached Twenty-Six utilities [S1].", evidence)
    assert rep["claims"][0]["unmatched_numbers"] == ["twenty-six"]


def test_pronoun_one_is_not_a_claim_quantity() -> None:
    assert _numbers_of("One of the commercial sites reached 91.3 percent efficiency [S1].") == ("supported", [])


def test_counts_are_not_matched_by_rounding_a_nearby_measurement() -> None:
    # 2 is within the old 0.051 absolute tolerance of 1.98 operators, but a count needs an equal value.
    assert _numbers_of("The trial used one control room for 2 sites [S4].") == ("unsupported", ["2"])


def test_list_markers_are_not_claim_quantities() -> None:
    assert _numbers_of("4) The pilot achieved 91.3 percent round-trip efficiency [S1].") == ("supported", [])
    assert _numbers_of("- 5. 91.3 percent round-trip efficiency was achieved in the pilot [S1].") == ("supported", [])
    assert _numbers_of("6. 97.5 percent round-trip efficiency was achieved in the pilot [S1].")[1] == ["97.5"]
