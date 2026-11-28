from types import SimpleNamespace
from uuid import uuid4

from app.services.obligation_normalizer import normalize_evidence_record
from app.services.cross_contract_comparator import compare_obligation_pair
from app.services.portfolio_intelligence_engine import analyze_organization_portfolio
from app.services.portfolio_finding_generator import generate_portfolio_findings


def make_obligation(source_text, contract_id, period):
    evidence = SimpleNamespace(
        id=uuid4(),
        document_id=uuid4(),
        clause_id=uuid4(),
        evidence_type="liability_cap",
        claim=f"Aggregate liability is capped by fees paid or payable during the preceding {period} months.",
        evidence_text=source_text,
        verification_status="verified",
        confidence=None,
        extraction_method="rule_based",
        page_number=1,
        char_start=0,
        char_end=len(source_text),
    )
    item = normalize_evidence_record(
        evidence,
        contract_id=contract_id,
        contract_title="Test contract",
    )
    item["analysis_eligible"] = True
    return item


def make_liability_comparison(first_period, second_period):
    return {
        "classification": "material_liability_variation",
        "comparison_type": "liability_variance",
        "obligation_type": "liability_cap",
        "explanation": "Liability reference periods differ.",
        "evidence": [
            {"evidence_id": str(uuid4()), "contract_id": str(uuid4())},
            {"evidence_id": str(uuid4()), "contract_id": str(uuid4())},
        ],
        "liability_comparison": {
            "first": {
                "scope": ["general"],
                "cap_basis": "fees_paid_or_payable",
                "cap_multiplier": None,
                "reference_period": first_period,
                "source_supported": True,
            },
            "second": {
                "scope": ["general"],
                "cap_basis": "fees_paid_or_payable",
                "cap_multiplier": None,
                "reference_period": second_period,
                "source_supported": True,
            },
            "scope_matches": True,
            "comparable_scope": True,
            "differing_attributes": ["reference_period"],
        },
        "requires_human_review": True,
        "legal_conflict_established": False,
    }


# EXISTING TESTS


def test_normalizer_extracts_general_liability_attributes():
    item = make_obligation(
        "Each party's aggregate liability arising out of this Agreement shall not exceed fees paid or payable during the 12 months preceding the event.",
        uuid4(),
        12,
    )
    attrs = item["liability_attributes"]

    assert attrs["scope"] == ["general"]
    assert attrs["reference_period"] == {"value": 12, "unit": "months"}
    assert attrs["cap_basis"] == "fees_paid_or_payable"


def test_normalizer_extracts_confidentiality_data_scope_and_multiplier():
    item = make_obligation(
        "Aggregate liability for breach of confidentiality or data protection obligations shall not exceed two (2) times the fees paid or payable during the twelve (12) months preceding the event.",
        uuid4(),
        12,
    )
    attrs = item["liability_attributes"]

    assert attrs["scope"] == ["confidentiality", "data_protection"]
    assert attrs["cap_multiplier"] == 2.0


def test_comparator_flags_same_scope_liability_cap_variation():
    first = make_obligation(
        "Aggregate liability arising out of this Agreement shall not exceed fees paid or payable during the preceding 12 months.",
        uuid4(),
        12,
    )
    second = make_obligation(
        "Aggregate liability arising out of this Agreement shall not exceed fees paid or payable during the preceding 6 months.",
        uuid4(),
        6,
    )

    result = compare_obligation_pair(first, second)

    assert result["comparison_type"] == "liability_variance"
    assert result["liability_comparison"]["comparable_scope"] is True


def test_comparator_flags_different_liability_scopes():
    first = make_obligation(
        "Aggregate liability arising out of this Agreement shall not exceed fees paid or payable during the preceding 12 months.",
        uuid4(),
        12,
    )
    second = make_obligation(
        "Aggregate liability for breach of confidentiality obligations shall not exceed two (2) times fees paid or payable during the preceding 12 months.",
        uuid4(),
        12,
    )

    result = compare_obligation_pair(first, second)

    assert result["comparison_type"] == "scope_variation"
    assert result["liability_comparison"]["comparable_scope"] is False


def test_material_liability_variation_generates_provisional_review_finding():
    first = make_obligation(
        "Aggregate liability arising out of this Agreement shall not exceed fees paid or payable during the preceding 12 months.",
        uuid4(),
        12,
    )
    second = make_obligation(
        "Aggregate liability arising out of this Agreement shall not exceed fees paid or payable during the preceding 6 months.",
        uuid4(),
        6,
    )

    intelligence = analyze_organization_portfolio([first, second])
    generated = generate_portfolio_findings(intelligence)

    assert generated["summary"]["generated_findings"] == 1

    finding = generated["findings"][0]

    assert finding["assessment_status"] == "provisional"
    assert finding["details"]["requires_human_review"] is True
    assert finding["details"]["legal_conflict_established"] is False


# NEW V1.2 BUSINESS IMPACT TESTS


def test_impact_assessment_identifies_shorter_reference_period():
    comparison = make_liability_comparison(
        {"value": 12, "unit": "months"},
        {"value": 6, "unit": "months"},
    )

    generated = generate_portfolio_findings({
        "comparisons": [comparison]
    })

    finding = generated["findings"][0]
    impact = finding["details"]["impact_assessment"]

    assert impact["assessment_type"] == "contractual_liability_variation"
    assert impact["comparison"]["shorter_period"] == "second_contract"
    assert impact["comparison"]["first_contract_period"]["value"] == 12
    assert impact["comparison"]["second_contract_period"]["value"] == 6
    assert impact["impact_level"] == "undetermined"


def test_impact_assessment_handles_missing_reference_period():
    comparison = make_liability_comparison(
        {"value": 12, "unit": "months"},
        None,
    )

    generated = generate_portfolio_findings({
        "comparisons": [comparison]
    })

    finding = generated["findings"][0]
    impact = finding["details"]["impact_assessment"]

    assert impact["human_review_required"] is True
    assert "comparison" not in impact
    assert impact["financial_exposure"]["quantified"] is False


def test_different_liability_scopes_do_not_generate_comparable_finding():
    first = make_obligation(
        "Aggregate liability arising out of this Agreement shall not exceed fees paid or payable during the preceding 12 months.",
        uuid4(),
        12,
    )
    second = make_obligation(
        "Aggregate liability for breach of confidentiality obligations shall not exceed two (2) times fees paid or payable during the preceding 12 months.",
        uuid4(),
        12,
    )

    intelligence = analyze_organization_portfolio([first, second])
    generated = generate_portfolio_findings(intelligence)

    assert generated["summary"]["generated_findings"] == 0


def test_impact_assessment_never_invents_financial_exposure():
    comparison = make_liability_comparison(
        {"value": 12, "unit": "months"},
        {"value": 6, "unit": "months"},
    )

    generated = generate_portfolio_findings({
        "comparisons": [comparison]
    })

    impact = generated["findings"][0]["details"]["impact_assessment"]
    exposure = impact["financial_exposure"]

    assert exposure["quantified"] is False
    assert exposure["amount"] is None
    assert exposure["reason"]


def test_impact_assessment_always_requires_human_review():
    comparison = make_liability_comparison(
        {"value": 12, "unit": "months"},
        {"value": 6, "unit": "months"},
    )

    generated = generate_portfolio_findings({
        "comparisons": [comparison]
    })

    finding = generated["findings"][0]
    impact = finding["details"]["impact_assessment"]

    assert finding["assessment_status"] == "provisional"
    assert impact["human_review_required"] is True
    assert finding["details"]["legal_conflict_established"] is False

def test_impact_assessment_separates_facts_and_interpretation():
    comparison = make_liability_comparison(
        {"value": 12, "unit": "months"},
        {"value": 6, "unit": "months"},
    )

    generated = generate_portfolio_findings({
        "comparisons": [comparison]
    })

    impact = generated["findings"][0]["details"]["impact_assessment"]

    assert len(impact["observed_facts"]) == 3
    assert impact["assumptions"] == []
    assert impact["unknowns"]
    assert impact["impact_level"] == "undetermined"


def test_impact_assessment_contains_evidence_traceability():
    comparison = make_liability_comparison(
        {"value": 12, "unit": "months"},
        {"value": 6, "unit": "months"},
    )

    comparison["evidence"][0].update({
        "contract_title": "Contract A",
        "claim": "Liability capped at 12 months of fees.",
        "original_text": "Fees paid during the preceding 12 months.",
    })

    generated = generate_portfolio_findings({
        "comparisons": [comparison]
    })

    impact = generated["findings"][0]["details"]["impact_assessment"]

    assert len(impact["evidence_basis"]) == 2

    source = impact["evidence_basis"][0]

    assert source["evidence_id"]
    assert source["contract_id"]
    assert source["contract_title"] == "Contract A"
    assert source["source_excerpt"]


def test_impact_assessment_identifies_missing_financial_inputs():
    comparison = make_liability_comparison(
        {"value": 12, "unit": "months"},
        {"value": 6, "unit": "months"},
    )

    generated = generate_portfolio_findings({
        "comparisons": [comparison]
    })

    impact = generated["findings"][0]["details"]["impact_assessment"]

    exposure = impact["financial_exposure"]

    assert exposure["quantified"] is False
    assert exposure["amount"] is None
    assert exposure["currency"] is None
    assert len(exposure["missing_inputs"]) >= 3


# V2 ENHANCED LIABILITY INTELLIGENCE REGRESSION TESTS


def test_normalizer_extracts_enhanced_multiplier_and_scope():
    item = make_obligation(
        "Aggregate liability for breach of confidentiality, data protection and security obligations shall not exceed three (3) times the fees paid or payable during the preceding twelve (12) months.",
        uuid4(), 12,
    )
    attrs = item["liability_attributes"]
    assert attrs["cap_multiplier"] == 3.0
    assert attrs["reference_period"] == {"value": 12, "unit": "months"}
    assert attrs["scope"] == ["confidentiality", "data_protection", "security"]
    assert attrs["cap_tier"] == "enhanced"


def test_normalizer_extracts_exception_categories_only_when_carveout_language_exists():
    from app.services.obligation_normalizer import extract_liability_attributes

    attrs = extract_liability_attributes(
        "The liability cap shall not apply to fraud, wilful misconduct or gross negligence."
    )
    assert attrs["exception_language_detected"] is True
    assert "fraud" in attrs["exceptions"]
    assert "wilful_misconduct" in attrs["exceptions"]
    assert "gross_negligence" in attrs["exceptions"]

    ordinary = extract_liability_attributes(
        "The enhanced cap covers confidentiality and data protection obligations."
    )
    assert ordinary["exceptions"] == []


def test_comparator_detects_enhanced_cap_multiplier_variation():
    first = make_obligation(
        "Aggregate liability for confidentiality and data protection obligations shall not exceed three (3) times fees paid or payable during the preceding 12 months.",
        uuid4(), 12,
    )
    second = make_obligation(
        "Aggregate liability for confidentiality and data protection obligations shall not exceed two (2) times fees paid or payable during the preceding 12 months.",
        uuid4(), 12,
    )
    result = compare_obligation_pair(first, second)
    assert result["comparison_type"] == "liability_variance"
    assert "cap_multiplier" in result["liability_comparison"]["differing_attributes"]
    assert result["liability_comparison"]["comparable_scope"] is True


def test_comparator_detects_different_liability_exception_categories():
    first = make_obligation(
        "The liability cap shall not apply to fraud, wilful misconduct or intellectual property indemnity claims.",
        uuid4(), 12,
    )
    second = make_obligation(
        "The liability cap shall not apply to fraud or wilful misconduct.",
        uuid4(), 12,
    )
    first["obligation_type"] = "liability_exceptions"
    second["obligation_type"] = "liability_exceptions"
    first["liability_attributes"] = __import__(
        "app.services.obligation_normalizer", fromlist=["extract_liability_attributes"]
    ).extract_liability_attributes(first["original_text"])
    second["liability_attributes"] = __import__(
        "app.services.obligation_normalizer", fromlist=["extract_liability_attributes"]
    ).extract_liability_attributes(second["original_text"])
    result = compare_obligation_pair(first, second)
    assert result["comparison_type"] == "liability_exception_variation"
    assert result["liability_comparison"]["exceptions_only_first"] == [
        "intellectual_property_indemnity"
    ]


def test_liability_exception_finding_remains_provisional_and_traceable():
    first = make_obligation(
        "The liability cap shall not apply to fraud or wilful misconduct.",
        uuid4(), 12,
    )
    second = make_obligation(
        "The liability cap shall not apply to fraud, wilful misconduct or gross negligence.",
        uuid4(), 12,
    )
    for item in (first, second):
        item["obligation_type"] = "liability_exceptions"
        from app.services.obligation_normalizer import extract_liability_attributes
        item["liability_attributes"] = extract_liability_attributes(item["original_text"])
    intelligence = analyze_organization_portfolio([first, second])
    generated = generate_portfolio_findings(intelligence)
    assert generated["summary"]["generated_findings"] == 1
    finding = generated["findings"][0]
    assert finding["assessment_status"] == "provisional"
    assert finding["details"]["requires_human_review"] is True
    assert finding["details"]["legal_conflict_established"] is False
    assert len(finding["details"]["impact_assessment"]["evidence_basis"]) == 2
