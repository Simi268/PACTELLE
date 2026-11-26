from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.services.obligation_normalizer import (
    normalize_unit,
    extract_duration,
    get_obligation_definition,
    normalize_evidence_record,
    normalize_evidence_records,
    group_obligations_by_family,
    group_obligations_by_type,
)


def make_evidence(
    evidence_type="renewal_notice",
    claim="Non-renewal requires at least 90 days' advance written notice.",
    evidence_text="The customer must provide 90 days' notice.",
    verification_status="unverified",
    confidence=None,
):
    return SimpleNamespace(
        id=uuid4(),
        document_id=uuid4(),
        clause_id=uuid4(),
        evidence_type=evidence_type,
        claim=claim,
        evidence_text=evidence_text,
        verification_status=verification_status,
        confidence=confidence,
        extraction_method="rule_based",
        page_number=2,
        char_start=100,
        char_end=150,
    )


# --------------------------------------------------
# UNIT NORMALIZATION
# --------------------------------------------------


@pytest.mark.parametrize(
    ("unit", "expected"),
    [
        ("day", "days"),
        ("days", "days"),
        ("week", "weeks"),
        ("weeks", "weeks"),
        ("month", "months"),
        ("months", "months"),
        ("year", "years"),
        ("years", "years"),
    ],
)
def test_normalize_unit(unit, expected):
    assert normalize_unit(unit) == expected


# --------------------------------------------------
# DURATION EXTRACTION
# --------------------------------------------------


@pytest.mark.parametrize(
    ("claim", "expected"),
    [
        ("Notice required within 90 days.", {
            "value": 90,
            "unit": "days",
        }),
        ("Renewal period of 3 months.", {
            "value": 3,
            "unit": "months",
        }),
        ("Payment due within 2 weeks.", {
            "value": 2,
            "unit": "weeks",
        }),
        ("Liability period of 1 year.", {
            "value": 1,
            "unit": "years",
        }),
        ("Notice required within 30 DAYS.", {
            "value": 30,
            "unit": "days",
        }),
    ],
)
def test_extract_duration(claim, expected):
    assert extract_duration(claim) == expected


@pytest.mark.parametrize(
    "claim",
    [
        "",
        "The agreement may be renewed automatically.",
        "Payment must be made promptly.",
        "The parties shall provide written notice.",
    ],
)
def test_extract_duration_returns_none_without_duration(claim):
    assert extract_duration(claim) is None


def test_extract_duration_does_not_convert_months_to_days():
    result = extract_duration(
        "Renewal notice requires 3 months."
    )

    assert result == {
        "value": 3,
        "unit": "months",
    }


# --------------------------------------------------
# OBLIGATION DEFINITIONS
# --------------------------------------------------


def test_get_existing_obligation_definition():
    result = get_obligation_definition("renewal_notice")

    assert result is not None
    assert result["family"] == "renewal"


def test_unknown_obligation_definition_returns_none():
    result = get_obligation_definition(
        "unknown_obligation"
    )

    assert result is None


# --------------------------------------------------
# SINGLE EVIDENCE NORMALIZATION
# --------------------------------------------------


def test_normalize_renewal_notice_evidence():
    evidence = make_evidence()

    contract_id = uuid4()

    result = normalize_evidence_record(
        evidence,
        contract_id=contract_id,
        contract_title="Vendor Agreement",
    )

    assert result is not None

    assert result["obligation_type"] == "renewal_notice"
    assert result["obligation_family"] == "renewal"

    assert result["duration"] == {
        "value": 90,
        "unit": "days",
    }

    assert result["contract_id"] == str(contract_id)
    assert result["contract_title"] == "Vendor Agreement"


def test_normalization_preserves_original_evidence():
    evidence = make_evidence(
        evidence_text="Original contractual wording."
    )

    result = normalize_evidence_record(evidence)

    assert result["original_text"] == (
        "Original contractual wording."
    )

    assert result["claim"] == evidence.claim


def test_normalization_preserves_provenance():
    evidence = make_evidence()

    result = normalize_evidence_record(evidence)

    provenance = result["provenance"]

    assert provenance["document_id"] == str(
        evidence.document_id
    )

    assert provenance["clause_id"] == str(
        evidence.clause_id
    )

    assert provenance["page_number"] == 2
    assert provenance["char_start"] == 100
    assert provenance["char_end"] == 150


def test_normalization_preserves_verification_status():
    evidence = make_evidence(
        verification_status="verified"
    )

    result = normalize_evidence_record(evidence)

    assert result["verification_status"] == "verified"


def test_normalization_preserves_confidence():
    evidence = make_evidence(confidence=0.95)

    result = normalize_evidence_record(evidence)

    assert result["confidence"] == 0.95


def test_normalization_preserves_missing_duration():
    evidence = make_evidence(
        claim="The agreement automatically renews."
    )

    result = normalize_evidence_record(evidence)

    assert result["duration"] is None


def test_unknown_evidence_type_is_skipped():
    evidence = make_evidence(
        evidence_type="unknown_type"
    )

    result = normalize_evidence_record(evidence)

    assert result is None


# --------------------------------------------------
# MULTIPLE EVIDENCE NORMALIZATION
# --------------------------------------------------


def test_normalize_multiple_evidence_records():
    evidence_records = [
        make_evidence(
            evidence_type="renewal_notice",
            claim="Non-renewal requires 90 days' notice.",
        ),
        make_evidence(
            evidence_type="payment_deadline",
            claim="Payment is due within 30 days.",
        ),
        make_evidence(
            evidence_type="termination_notice",
            claim="Termination requires 60 days' notice.",
        ),
    ]

    results = normalize_evidence_records(
        evidence_records
    )

    assert len(results) == 3

    assert results[0]["obligation_family"] == "renewal"
    assert results[1]["obligation_family"] == "payment"
    assert results[2]["obligation_family"] == "termination"


def test_normalize_multiple_records_skips_unsupported_types():
    evidence_records = [
        make_evidence(
            evidence_type="renewal_notice"
        ),
        make_evidence(
            evidence_type="unsupported_type"
        ),
    ]

    results = normalize_evidence_records(
        evidence_records
    )

    assert len(results) == 1


def test_normalize_empty_evidence_list():
    results = normalize_evidence_records([])

    assert results == []


# --------------------------------------------------
# GROUPING BY OBLIGATION FAMILY
# --------------------------------------------------


def test_group_obligations_by_family():
    evidence_records = [
        make_evidence(
            evidence_type="renewal_notice"
        ),
        make_evidence(
            evidence_type="renewal_period"
        ),
        make_evidence(
            evidence_type="payment_deadline",
            claim="Payment is due within 30 days.",
        ),
    ]

    obligations = normalize_evidence_records(
        evidence_records
    )

    grouped = group_obligations_by_family(
        obligations
    )

    assert len(grouped["renewal"]) == 2
    assert len(grouped["payment"]) == 1


def test_group_empty_obligations():
    result = group_obligations_by_family([])

    assert result == {}


# --------------------------------------------------
# GROUPING BY OBLIGATION TYPE
# --------------------------------------------------


def test_group_obligations_by_type():
    evidence_records = [
        make_evidence(
            evidence_type="renewal_notice"
        ),
        make_evidence(
            evidence_type="renewal_notice"
        ),
        make_evidence(
            evidence_type="renewal_period"
        ),
    ]

    obligations = normalize_evidence_records(
        evidence_records
    )

    grouped = group_obligations_by_type(
        obligations
    )

    assert len(grouped["renewal_notice"]) == 2
    assert len(grouped["renewal_period"]) == 1


def test_group_empty_obligations_by_type():
    result = group_obligations_by_type([])

    assert result == {}