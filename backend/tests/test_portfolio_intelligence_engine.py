import uuid

from app.services.portfolio_intelligence_engine import (
    analyze_organization_portfolio,
)


def make_obligation(
    contract_id=None,
    value=90,
    unit="days",
    verification_status="verified",
    eligible=True,
    text=None,
):
    if text is None:
        text = (
            f"Vendor shall notify Customer "
            f"{value} {unit} before changing subprocessors."
        )

    return {
        "evidence_id": str(uuid.uuid4()),
        "contract_id": str(contract_id or uuid.uuid4()),
        "contract_title": "Vendor Agreement",
        "obligation_type": "subprocessor_change_notice",
        "obligation_family": "data_protection",
        "claim": text,
        "original_text": text,
        "duration": (
            {"value": value, "unit": unit}
            if value is not None
            else None
        ),
        "verification_status": verification_status,
        "analysis_eligible": eligible,
        "provenance": {
            "document_id": str(uuid.uuid4()),
            "clause_id": str(uuid.uuid4()),
            "page_number": 1,
            "char_start": 10,
            "char_end": 100,
        },
    }


def test_empty_portfolio():
    result = analyze_organization_portfolio([])

    assert result["summary"]["total_obligations"] == 0
    assert result["summary"]["total_comparisons"] == 0
    assert result["comparisons"] == []
    assert result["human_review_queue"] == []


def test_similar_obligations_are_classified():
    obligations = [
        make_obligation(value=90),
        make_obligation(value=90),
    ]

    result = analyze_organization_portfolio(obligations)

    comparison = result["comparisons"][0]

    assert comparison["classification"] == "similar_obligation"
    assert comparison["legal_conflict_established"] is False


def test_different_terms_are_classified_as_variation():
    obligations = [
        make_obligation(value=90),
        make_obligation(value=30),
    ]

    result = analyze_organization_portfolio(obligations)

    comparison = result["comparisons"][0]

    assert comparison["classification"] == "contractual_variation"
    assert comparison["requires_human_review"] is True


def test_shared_trigger_and_different_parties_flag_dependency():
    obligations = [
        make_obligation(
            value=90,
            text=(
                "Vendor shall notify Customer "
                "90 days before changing subprocessors."
            ),
        ),
        make_obligation(
            value=30,
            text=(
                "Customer shall approve subprocessor changes "
                "30 days before implementation."
            ),
        ),
    ]

    result = analyze_organization_portfolio(obligations)

    comparison = result["comparisons"][0]

    assert (
        comparison["classification"]
        == "potential_operational_dependency"
    )

    assert comparison["operational_dependency_candidate"] is True
    assert comparison["requires_human_review"] is True
    assert comparison["legal_conflict_established"] is False


def test_unverified_evidence_remains_provisional():
    obligations = [
        make_obligation(
            value=90,
            verification_status="unverified",
        ),
        make_obligation(value=30),
    ]

    result = analyze_organization_portfolio(obligations)

    comparison = result["comparisons"][0]

    assert comparison["evidence_assessment"] == "provisional"
    assert comparison["requires_human_review"] is True


def test_rejected_evidence_is_excluded():
    obligations = [
        make_obligation(value=90),
        make_obligation(
            value=30,
            verification_status="rejected",
            eligible=False,
        ),
    ]

    result = analyze_organization_portfolio(obligations)

    assert result["summary"]["eligible_obligations"] == 1
    assert result["summary"]["excluded_obligations"] == 1
    assert result["summary"]["total_comparisons"] == 0


def test_different_obligation_types_are_not_compared():
    first = make_obligation(value=90)

    second = make_obligation(value=30)
    second["obligation_type"] = "payment_deadline"

    result = analyze_organization_portfolio([first, second])

    assert result["summary"]["total_comparisons"] == 0


def test_same_contract_obligations_are_not_compared():
    contract_id = uuid.uuid4()

    obligations = [
        make_obligation(contract_id=contract_id),
        make_obligation(contract_id=contract_id, value=30),
    ]

    result = analyze_organization_portfolio(obligations)

    assert result["summary"]["total_comparisons"] == 0


def test_evidence_provenance_is_preserved():
    obligations = [
        make_obligation(value=90),
        make_obligation(value=30),
    ]

    result = analyze_organization_portfolio(obligations)

    evidence = result["comparisons"][0]["evidence"]

    assert len(evidence) == 2
    assert evidence[0]["provenance"]["document_id"]
    assert evidence[1]["provenance"]["clause_id"]


def test_no_comparison_establishes_legal_conflict():
    obligations = [
        make_obligation(value=90),
        make_obligation(value=30),
    ]

    result = analyze_organization_portfolio(obligations)

    assert result["summary"]["legal_conflicts_established"] == 0

    for comparison in result["comparisons"]:
        assert comparison["legal_conflict_established"] is False


def test_human_review_queue_contains_flagged_variations():
    obligations = [
        make_obligation(value=90),
        make_obligation(value=30),
    ]

    result = analyze_organization_portfolio(obligations)

    assert len(result["human_review_queue"]) == 1


def test_classification_counts_are_consistent():
    obligations = [
        make_obligation(value=90),
        make_obligation(value=90),
        make_obligation(value=30),
    ]

    result = analyze_organization_portfolio(obligations)

    counts = result["summary"]["classification_counts"]

    assert sum(counts.values()) == 3
    assert result["summary"]["total_comparisons"] == 3