from datetime import date
from types import SimpleNamespace
from uuid import uuid4

from app.services.risk_explanation import explain_risk_finding


def make_finding(
    evidence_links=None,
    assessment_status="confirmed",
):
    return SimpleNamespace(
        id=uuid4(),
        title="Automatic Renewal Exposure",
        risk_type="renewal_exposure",
        description="Automatic renewal provisions were identified.",
        severity="medium",
        status="open",
        assessment_status=assessment_status,
        deadline_date=date(2026, 12, 31),
        detection_method="rule_based",
        rule_id="RENEWAL-001",
        rule_version="1.0",
        evidence_links=evidence_links or [],
    )


def make_evidence(
    verification_status="verified",
    confidence=0.9,
):
    document = SimpleNamespace(
        original_filename="vendor_agreement.pdf"
    )

    clause = SimpleNamespace(
        clause_number="8.1",
        clause_title="Renewal",
        category="renewal",
        source_text="The agreement shall automatically renew.",
        page_number=2,
        char_start=100,
        char_end=150,
        extraction_method="rule_based",
    )

    evidence = SimpleNamespace(
        id=uuid4(),
        claim="Automatic renewal provision",
        evidence_type="renewal_period",
        evidence_text="The agreement shall automatically renew.",
        verification_status=verification_status,
        confidence=confidence,
        extraction_method="rule_based",
        page_number=2,
        char_start=100,
        char_end=150,
        document=document,
        clause=clause,
    )

    return SimpleNamespace(
        evidence_record=evidence
    )


def test_explanation_includes_document_and_clause_provenance():

    finding = make_finding([
        make_evidence()
    ])

    result = explain_risk_finding(finding)

    evidence = result["supporting_evidence"][0]

    assert evidence["document"] == "vendor_agreement.pdf"
    assert evidence["clause"]["clause_number"] == "8.1"
    assert evidence["clause"]["page_number"] == 2


def test_explanation_separates_verified_evidence():

    finding = make_finding([
        make_evidence("verified"),
        make_evidence("unverified"),
    ])

    result = explain_risk_finding(finding)

    assert result["evidence_summary"]["verified"] == 1
    assert result["evidence_summary"]["unverified"] == 1


def test_rejected_evidence_is_not_supporting_evidence():

    finding = make_finding([
        make_evidence("rejected")
    ])

    result = explain_risk_finding(finding)

    assert len(result["supporting_evidence"]) == 0
    assert len(result["rejected_evidence"]) == 1


def test_provisional_finding_requires_human_review():

    finding = make_finding(
        [make_evidence()],
        assessment_status="provisional",
    )

    result = explain_risk_finding(finding)

    assert result["human_review_required"] is True


def test_missing_evidence_is_reported():

    finding = make_finding()

    result = explain_risk_finding(finding)

    assert result["supporting_evidence"] == []
    assert result["human_review_required"] is True
    assert len(result["uncertainties"]) > 0


def test_missing_clause_provenance_is_reported():

    evidence = make_evidence()

    evidence.evidence_record.clause = None

    finding = make_finding([evidence])

    result = explain_risk_finding(finding)

    assert any(
        "Clause provenance is unavailable" in item
        for item in result["uncertainties"]
    )


def test_recommendation_is_provided():

    result = explain_risk_finding(make_finding())

    assert result["recommended_action"]