import uuid

from app.services.obligation_context_analyzer import (
    analyze_obligation_context,
    compare_obligation_contexts,
    analyze_cross_contract_contexts,
)


def make_obligation(
    text,
    contract_id=None,
    obligation_type="subprocessor_change_notice",
):
    return {
        "evidence_id": str(uuid.uuid4()),
        "contract_id": str(contract_id or uuid.uuid4()),
        "obligation_type": obligation_type,
        "claim": text,
        "original_text": text,
        "analysis_eligible": True,
    }


def test_extract_subprocessor_change_trigger():
    obligation = make_obligation(
        "Vendor must notify Customer before changing subprocessors."
    )

    result = analyze_obligation_context(obligation)

    assert result["trigger"]["trigger_type"] == "subprocessor_change"


def test_extract_security_incident_trigger():
    obligation = make_obligation(
        "Vendor must notify Customer of a security incident."
    )

    result = analyze_obligation_context(obligation)

    assert result["trigger"]["trigger_type"] == "security_incident"


def test_extract_responsible_party():
    obligation = make_obligation(
        "Vendor shall notify Customer before changing subprocessors."
    )

    result = analyze_obligation_context(obligation)

    assert result["responsibility"]["responsible_party"] == "vendor"


def test_extract_recipient():
    obligation = make_obligation(
        "Vendor shall notify Customer before changing subprocessors."
    )

    result = analyze_obligation_context(obligation)

    assert result["recipient"]["recipient_party"] == "customer"


def test_extract_obligation_direction():
    obligation = make_obligation(
        "Vendor shall notify Customer before changing subprocessors."
    )

    result = analyze_obligation_context(obligation)

    assert result["recipient"]["direction"] == "vendor_to_customer"


def test_unknown_trigger_is_handled():
    obligation = make_obligation(
        "Vendor shall provide reasonable assistance."
    )

    result = analyze_obligation_context(obligation)

    assert result["trigger"]["trigger_type"] == "unspecified"


def test_unknown_responsible_party_is_handled():
    obligation = make_obligation(
        "Reasonable assistance must be provided."
    )

    result = analyze_obligation_context(obligation)

    assert result["responsibility"]["responsible_party"] is None


def test_multiple_triggers_are_marked_ambiguous():
    obligation = make_obligation(
        "Vendor must notify Customer of a security incident "
        "during contract termination."
    )

    result = analyze_obligation_context(obligation)

    assert (
        result["trigger"]["trigger_type"]
        == "multiple_or_ambiguous"
    )


def test_same_trigger_relationship():
    first = analyze_obligation_context(
        make_obligation(
            "Vendor shall notify Customer before changing subprocessors."
        )
    )

    second = analyze_obligation_context(
        make_obligation(
            "Supplier must notify Client of subprocessor changes."
        )
    )

    result = compare_obligation_contexts(first, second)

    assert result["trigger_relationship"] == "shared_trigger"


def test_different_responsible_parties_are_not_conflicts():
    first = analyze_obligation_context(
        make_obligation(
            "Vendor shall notify Customer before changing subprocessors."
        )
    )

    second = analyze_obligation_context(
        make_obligation(
            "Customer shall approve subprocessor changes."
        )
    )

    result = compare_obligation_contexts(first, second)

    assert (
        result["responsibility_relationship"]
        == "different_responsible_parties"
    )

    assert result["legal_conflict_established"] is False


def test_missing_context_requires_review():
    first = analyze_obligation_context(
        make_obligation("Vendor shall provide assistance.")
    )

    second = analyze_obligation_context(
        make_obligation("Supplier shall provide support.")
    )

    result = compare_obligation_contexts(first, second)

    assert result["requires_review"] is True


def test_same_contract_is_not_compared():
    contract_id = uuid.uuid4()

    obligations = [
        make_obligation(
            "Vendor shall notify Customer of subprocessor changes.",
            contract_id,
        ),
        make_obligation(
            "Vendor shall notify Customer of security incidents.",
            contract_id,
        ),
    ]

    result = analyze_cross_contract_contexts(obligations)

    assert result["summary"]["context_comparisons"] == 0


def test_cross_contract_context_comparison():
    obligations = [
        make_obligation(
            "Vendor shall notify Customer before changing subprocessors."
        ),
        make_obligation(
            "Customer shall approve subprocessor changes."
        ),
    ]

    result = analyze_cross_contract_contexts(obligations)

    assert result["summary"]["analyzed_obligations"] == 2
    assert result["summary"]["context_comparisons"] == 1


def test_rejected_obligations_are_excluded():
    obligation = make_obligation(
        "Vendor shall notify Customer of security incidents."
    )

    obligation["analysis_eligible"] = False

    result = analyze_cross_contract_contexts([obligation])

    assert result["summary"]["analyzed_obligations"] == 0


def test_context_comparison_never_establishes_legal_conflict():
    obligations = [
        make_obligation(
            "Vendor shall notify Customer before changing subprocessors."
        ),
        make_obligation(
            "Customer shall approve subprocessor changes."
        ),
    ]

    result = analyze_cross_contract_contexts(obligations)

    comparison = result["comparisons"][0]["context_comparison"]

    assert comparison["legal_conflict_established"] is False
