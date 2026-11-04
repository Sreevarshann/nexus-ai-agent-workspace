from nexus.agents.verify import verify_report

EVIDENCE = {
    "S1": "The pilot achieved round-trip efficiency of 91.3 percent across three commercial sites.",
    "S2": "The warranty covers 10 years or 6,000 cycles, guaranteeing 80 percent capacity.",
    "D1": "[D1] Revenue by region\nregion | revenue\nNorth | 20068214.8",
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
