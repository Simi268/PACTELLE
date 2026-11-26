import uuid

from app.services.portfolio_finding_generator import (
    generate_portfolio_findings,
)


def make_comparison(
    classification="potential_operational_dependency",
    operational_dependency=True,
):
    evidence_a = str(uuid.uuid4())
    evidence_b = str(uuid.uuid4())

    contract_a = str(uuid.uuid4())
    contract_b = str(uuid.uuid4())

    return {
        "classification": classification,
        "comparison_type": "term_variance",
        "obligation_type": "subprocessor_change_notice",
        "explanation": "Potential operational dependency requiring review.",
        "operational_dependency_candidate": operational_dependency,
        "assessment_status": "provisional",
        "evidence": [
            {
                "evidence_id": evidence_a,
                "contract_id": contract_a,
            },
            {
                "evidence_id": evidence_b,
                "contract_id": contract_b,
            },
        ],
        "context_analysis": {
            "trigger_relationship": "shared_trigger",
            "responsibility_relationship": (
                "different_responsible_parties"
            ),
            "direction_relationship": "different_directions",
        },
    }


def test_generates_operational_dependency_finding():
    result = generate_portfolio_findings({
        "comparisons": [make_comparison()]
    })

    assert result["summary"]["generated_findings"] == 1

    finding = result["findings"][0]

    assert finding["finding_type"] == "potential_conflict"
    assert finding["assessment_status"] == "provisional"
    assert finding["status"] == "open"


def test_finding_preserves_contract_references():
    comparison = make_comparison()

    result = generate_portfolio_findings({
        "comparisons": [comparison]
    })

    finding = result["findings"][0]

    expected_contracts = sorted(
        item["contract_id"]
        for item in comparison["evidence"]
    )

    assert finding["contract_ids"] == expected_contracts


def test_finding_preserves_evidence_references():
    comparison = make_comparison()

    result = generate_portfolio_findings({
        "comparisons": [comparison]
    })

    finding = result["findings"][0]

    expected_evidence = sorted(
        item["evidence_id"]
        for item in comparison["evidence"]
    )

    assert finding["evidence_ids"] == expected_evidence


def test_finding_has_deterministic_rule_id():
    comparison = make_comparison()

    first = generate_portfolio_findings({
        "comparisons": [comparison]
    })

    second = generate_portfolio_findings({
        "comparisons": [comparison]
    })

    assert (
        first["findings"][0]["rule_id"]
        == second["findings"][0]["rule_id"]
    )


def test_evidence_order_does_not_change_rule_id():
    comparison = make_comparison()

    first = generate_portfolio_findings({
        "comparisons": [comparison]
    })

    comparison["evidence"].reverse()

    second = generate_portfolio_findings({
        "comparisons": [comparison]
    })

    assert (
        first["findings"][0]["rule_id"]
        == second["findings"][0]["rule_id"]
    )


def test_similar_obligations_do_not_generate_findings():
    comparison = make_comparison(
        classification="similar_obligation",
        operational_dependency=False,
    )

    result = generate_portfolio_findings({
        "comparisons": [comparison]
    })

    assert result["summary"]["generated_findings"] == 0


def test_ordinary_variations_do_not_generate_findings():
    comparison = make_comparison(
        classification="contractual_variation",
        operational_dependency=False,
    )

    result = generate_portfolio_findings({
        "comparisons": [comparison]
    })

    assert result["summary"]["generated_findings"] == 0


def test_dependency_flag_is_required():
    comparison = make_comparison(
        operational_dependency=False,
    )

    result = generate_portfolio_findings({
        "comparisons": [comparison]
    })

    assert result["summary"]["generated_findings"] == 0


def test_missing_contract_reference_prevents_finding():
    comparison = make_comparison()

    comparison["evidence"][1]["contract_id"] = None

    result = generate_portfolio_findings({
        "comparisons": [comparison]
    })

    assert result["summary"]["generated_findings"] == 0


def test_missing_evidence_reference_prevents_finding():
    comparison = make_comparison()

    comparison["evidence"][1]["evidence_id"] = None

    result = generate_portfolio_findings({
        "comparisons": [comparison]
    })

    assert result["summary"]["generated_findings"] == 0


def test_finding_never_claims_legal_conflict():
    result = generate_portfolio_findings({
        "comparisons": [make_comparison()]
    })

    finding = result["findings"][0]

    assert (
        finding["details"]["legal_conflict_established"]
        is False
    )


def test_finding_is_provisional_and_requires_review():
    result = generate_portfolio_findings({
        "comparisons": [make_comparison()]
    })

    finding = result["findings"][0]

    assert finding["assessment_status"] == "provisional"
    assert finding["details"]["requires_human_review"] is True


def test_duplicate_comparisons_are_deduplicated():
    comparison = make_comparison()

    result = generate_portfolio_findings({
        "comparisons": [comparison, comparison]
    })

    assert result["summary"]["generated_findings"] == 1
    assert result["summary"]["skipped_comparisons"] == 1


def test_empty_comparisons():
    result = generate_portfolio_findings({
        "comparisons": []
    })

    assert result["summary"]["generated_findings"] == 0
    assert result["findings"] == []


def test_generator_summary_is_consistent():
    comparisons = [
        make_comparison(),
        make_comparison(
            classification="similar_obligation",
            operational_dependency=False,
        ),
    ]

    result = generate_portfolio_findings({
        "comparisons": comparisons
    })

    summary = result["summary"]

    assert summary["total_comparisons"] == 2
    assert summary["generated_findings"] == 1
    assert summary["skipped_comparisons"] == 1
    assert summary["provisional_findings"] == 1