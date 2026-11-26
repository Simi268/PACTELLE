import uuid

import pytest

from app.services.cross_contract_comparator import (
    compare_obligation_pair,
    compare_cross_contract_obligations,
)


def make_obligation(
    contract_id=None,
    evidence_type="renewal_notice",
    value=90,
    unit="days",
    verification_status="verified",
    analysis_eligible=True,
):
    return {
        "evidence_id": str(uuid.uuid4()),
        "contract_id": str(contract_id or uuid.uuid4()),
        "contract_title": "Vendor Agreement",
        "obligation_type": evidence_type,
        "obligation_family": "renewal",
        "claim": f"Non-renewal requires {value} {unit} notice.",
        "original_text": f"Notice required {value} {unit}.",
        "duration": (
            {"value": value, "unit": unit}
            if value is not None
            else None
        ),
        "verification_status": verification_status,
        "analysis_eligible": analysis_eligible,
        "provenance": {
            "page_number": 1,
            "char_start": 10,
            "char_end": 50,
        },
    }


# --------------------------------------------------
# PAIR COMPARISON
# --------------------------------------------------


def test_same_duration_is_similar():
    first = make_obligation(value=90)
    second = make_obligation(value=90)

    result = compare_obligation_pair(first, second)

    assert result["comparison_type"] == "similar"
    assert result["duration_comparison"]["matches"] is True


def test_different_duration_is_term_variance():
    first = make_obligation(value=90)
    second = make_obligation(value=30)

    result = compare_obligation_pair(first, second)

    assert result["comparison_type"] == "term_variance"
    assert result["duration_comparison"]["matches"] is False
    assert result["requires_review"] is True


def test_months_and_days_are_not_assumed_equivalent():
    first = make_obligation(value=3, unit="months")
    second = make_obligation(value=90, unit="days")

    result = compare_obligation_pair(first, second)

    assert result["comparison_type"] == "term_variance"


def test_same_month_duration_is_similar():
    first = make_obligation(value=3, unit="months")
    second = make_obligation(value=3, unit="months")

    result = compare_obligation_pair(first, second)

    assert result["comparison_type"] == "similar"


def test_missing_duration_returns_insufficient_data():
    first = make_obligation(value=None)
    second = make_obligation(value=90)

    result = compare_obligation_pair(first, second)

    assert result["comparison_type"] == "insufficient_data"
    assert result["duration_comparison"]["matches"] is None


def test_different_obligation_types_are_not_compared():
    first = make_obligation(
        evidence_type="renewal_notice"
    )

    second = make_obligation(
        evidence_type="termination_notice"
    )

    result = compare_obligation_pair(first, second)

    assert result is None


def test_same_contract_obligations_are_not_compared():
    contract_id = uuid.uuid4()

    first = make_obligation(contract_id=contract_id)
    second = make_obligation(contract_id=contract_id)

    result = compare_obligation_pair(first, second)

    assert result is None


def test_rejected_evidence_is_not_compared():
    first = make_obligation(
        verification_status="rejected",
        analysis_eligible=False,
    )

    second = make_obligation()

    result = compare_obligation_pair(first, second)

    assert result is None


def test_unverified_evidence_produces_provisional_assessment():
    first = make_obligation(
        verification_status="unverified"
    )

    second = make_obligation(
        verification_status="verified"
    )

    result = compare_obligation_pair(first, second)

    assert result["assessment_status"] == "provisional"
    assert result["requires_review"] is True


def test_verified_evidence_does_not_confirm_legal_conflict():
    first = make_obligation(value=90)
    second = make_obligation(value=30)

    result = compare_obligation_pair(first, second)

    assert result["assessment_status"] == "confirmed"
    assert result["comparison_type"] == "term_variance"

    # A verified comparison is not a legal conclusion.
    assert result["comparison_type"] != "potential_conflict"


# --------------------------------------------------
# MULTIPLE OBLIGATION COMPARISON
# --------------------------------------------------


def test_compares_multiple_contracts():
    obligations = [
        make_obligation(value=90),
        make_obligation(value=90),
        make_obligation(value=30),
    ]

    result = compare_cross_contract_obligations(
        obligations
    )

    assert result["summary"]["total_obligations"] == 3
    assert result["summary"]["total_comparisons"] == 3

    assert result["summary"]["similar"] == 1
    assert result["summary"]["term_variance"] == 2


def test_comparison_skips_rejected_evidence():
    obligations = [
        make_obligation(value=90),
        make_obligation(
            value=30,
            verification_status="rejected",
            analysis_eligible=False,
        ),
    ]

    result = compare_cross_contract_obligations(
        obligations
    )

    assert result["summary"]["total_comparisons"] == 0
    assert result["summary"]["skipped_rejected"] == 1


def test_multiple_contracts_with_different_types():
    obligations = [
        make_obligation(
            evidence_type="renewal_notice"
        ),
        make_obligation(
            evidence_type="payment_deadline",
            value=30,
        ),
    ]

    result = compare_cross_contract_obligations(
        obligations
    )

    assert result["summary"]["total_comparisons"] == 0


def test_empty_obligations():
    result = compare_cross_contract_obligations([])

    assert result["summary"]["total_obligations"] == 0
    assert result["summary"]["total_comparisons"] == 0
    assert result["comparisons"] == []


def test_invalid_obligations_are_skipped():
    obligations = [
        {
            "contract_id": None,
            "obligation_type": "renewal_notice",
        },
        {
            "contract_id": str(uuid.uuid4()),
            "obligation_type": None,
        },
    ]

    result = compare_cross_contract_obligations(
        obligations
    )

    assert result["summary"]["total_comparisons"] == 0
    assert result["summary"]["skipped_invalid"] == 2


# --------------------------------------------------
# EVIDENCE TRACEABILITY
# --------------------------------------------------


def test_comparison_preserves_both_evidence_references():
    first = make_obligation(value=90)
    second = make_obligation(value=30)

    result = compare_obligation_pair(first, second)

    assert len(result["evidence"]) == 2

    assert (
        result["evidence"][0]["evidence_id"]
        == first["evidence_id"]
    )

    assert (
        result["evidence"][1]["evidence_id"]
        == second["evidence_id"]
    )

    assert (
        result["evidence"][0]["provenance"]["page_number"]
        == 1
    )