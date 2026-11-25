from datetime import date, timedelta

from app.core.security import create_access_token

from app.models.contract import Contract
from app.models.risk_finding import RiskFinding

from app.models.clause import ContractClause
from app.models.evidence_record import EvidenceRecord
from app.models.risk_finding_evidence import RiskFindingEvidence


def auth_headers(user):
    token = create_access_token(user.id)

    return {
        "Authorization": f"Bearer {token}"
    }


def create_risk(
    db_session,
    contract,
    *,
    risk_type="renewal_exposure",
    rule_id="RENEWAL-001",
    severity="medium",
    status="open",
    assessment_status="provisional",
    deadline=None,
):
    finding = RiskFinding(
        contract_id=contract.id,
        risk_type=risk_type,
        title="Test Risk",
        description="Test risk finding.",
        severity=severity,
        status=status,
        assessment_status=assessment_status,
        detection_method="rule_based",
        rule_id=rule_id,
        rule_version="1.0",
        deadline_date=deadline,
    )

    db_session.add(finding)
    db_session.flush()

    return finding


def test_dashboard_counts_populated_records(
    api_client,
    db_session,
    contract_api_data,
):
    data = contract_api_data

    today = date.today()

    expiring_contract = Contract(
        organization_id=data["organization_a"].id,
        title="Expiring Contract",
        contract_type="vendor",
        status="active",
        expiration_date=today + timedelta(days=10),
    )

    db_session.add(expiring_contract)
    db_session.flush()

    create_risk(
        db_session,
        data["contract_a"],
        severity="high",
    )

    create_risk(
        db_session,
        data["contract_a"],
        risk_type="payment_risk",
        rule_id="PAYMENT-001",
        severity="low",
    )

    create_risk(
        db_session,
        data["contract_a"],
        risk_type="resolved_risk",
        rule_id="RESOLVED-001",
        severity="medium",
        status="resolved",
    )

    db_session.commit()

    response = api_client.get(
        f"/api/v1/organizations/"
        f"{data['organization_a'].id}/dashboard",
        headers=auth_headers(data["owner_a"]),
    )

    assert response.status_code == 200

    result = response.json()

    assert result["contracts"]["total"] == 3
    assert result["documents"]["total"] == 1

    assert result["risks"]["total_open"] == 2
    assert result["risks"]["by_severity"]["high"] == 1
    assert result["risks"]["by_severity"]["low"] == 1

    assert (
        result["monitoring"]["contracts_expiring_next_30_days"]
        == 1
    )


def test_upcoming_renewals_respects_deadline_window(
    api_client,
    db_session,
    contract_api_data,
):
    data = contract_api_data

    today = date.today()

    create_risk(
        db_session,
        data["contract_a"],
        deadline=today + timedelta(days=10),
    )

    create_risk(
        db_session,
        data["empty_contract"],
        deadline=today + timedelta(days=40),
    )

    create_risk(
        db_session,
        data["contract_a"],
        rule_id="OLD-RENEWAL",
        deadline=today + timedelta(days=5),
    )

    db_session.commit()

    response = api_client.get(
        f"/api/v1/organizations/"
        f"{data['organization_a'].id}/upcoming-renewals?days=30",
        headers=auth_headers(data["owner_a"]),
    )

    assert response.status_code == 200

    result = response.json()

    assert result["total"] == 1

    assert (
        result["renewals"][0]["days_until_deadline"]
        == 10
    )


def test_expiring_contracts_respects_date_window(
    api_client,
    db_session,
    contract_api_data,
):
    data = contract_api_data

    today = date.today()

    expiring = Contract(
        organization_id=data["organization_a"].id,
        title="Expires Soon",
        contract_type="vendor",
        status="active",
        expiration_date=today + timedelta(days=15),
    )

    later = Contract(
        organization_id=data["organization_a"].id,
        title="Expires Later",
        contract_type="vendor",
        status="active",
        expiration_date=today + timedelta(days=60),
    )

    expired = Contract(
        organization_id=data["organization_a"].id,
        title="Already Expired",
        contract_type="vendor",
        status="expired",
        expiration_date=today - timedelta(days=5),
    )

    terminated = Contract(
        organization_id=data["organization_a"].id,
        title="Terminated Contract",
        contract_type="vendor",
        status="terminated",
        expiration_date=today + timedelta(days=5),
    )

    db_session.add_all([
        expiring,
        later,
        expired,
        terminated,
    ])

    db_session.commit()

    response = api_client.get(
        f"/api/v1/organizations/"
        f"{data['organization_a'].id}/expiring-contracts?days=30",
        headers=auth_headers(data["owner_a"]),
    )

    assert response.status_code == 200

    result = response.json()

    assert result["total"] == 1
    assert result["contracts"][0]["title"] == "Expires Soon"
    assert result["contracts"][0]["days_until_expiration"] == 15


def test_risk_overview_separates_open_and_resolved(
    api_client,
    db_session,
    contract_api_data,
):
    data = contract_api_data

    create_risk(
        db_session,
        data["contract_a"],
        severity="high",
        assessment_status="confirmed",
    )

    create_risk(
        db_session,
        data["contract_a"],
        rule_id="PAYMENT-001",
        risk_type="payment_risk",
        severity="low",
        assessment_status="provisional",
    )

    create_risk(
        db_session,
        data["contract_a"],
        rule_id="RESOLVED-001",
        status="resolved",
    )

    db_session.commit()

    response = api_client.get(
        f"/api/v1/organizations/"
        f"{data['organization_a'].id}/risk-overview",
        headers=auth_headers(data["owner_a"]),
    )

    assert response.status_code == 200

    result = response.json()

    summary = result["summary"]

    assert summary["total_findings"] == 3
    assert summary["open_findings"] == 2
    assert summary["resolved_findings"] == 1

    assert result["open_findings_by_severity"]["high"] == 1
    assert result["open_findings_by_severity"]["low"] == 1

    assert result["open_findings_by_assessment"]["confirmed"] == 1
    assert result["open_findings_by_assessment"]["provisional"] == 1


def test_organization_a_cannot_see_organization_b_risks(
    api_client,
    db_session,
    contract_api_data,
):
    data = contract_api_data

    create_risk(
        db_session,
        data["contract_a"],
        rule_id="A-RISK",
    )

    create_risk(
        db_session,
        data["contract_b"],
        rule_id="B-RISK",
    )

    db_session.commit()

    response = api_client.get(
        f"/api/v1/organizations/"
        f"{data['organization_a'].id}/risk-overview",
        headers=auth_headers(data["owner_a"]),
    )

    assert response.status_code == 200

    result = response.json()

    assert result["summary"]["total_findings"] == 1

def test_risk_prioritization_ranks_critical_risks(
    api_client,
    db_session,
    contract_api_data,
):
    data = contract_api_data
    today = date.today()

    create_risk(
        db_session,
        data["contract_a"],
        rule_id="LOW-001",
        severity="low",
        deadline=today + timedelta(days=90),
    )

    create_risk(
        db_session,
        data["contract_a"],
        rule_id="CRITICAL-001",
        severity="critical",
        deadline=today + timedelta(days=2),
    )

    db_session.commit()

    response = api_client.get(
        f"/api/v1/organizations/"
        f"{data['organization_a'].id}/risk-prioritization",
        headers=auth_headers(data["owner_a"]),
    )

    assert response.status_code == 200

    result = response.json()

    assert result["total_open_risks"] == 2

    risks = result["prioritized_risks"]

    assert risks[0]["severity"] == "critical"
    assert risks[1]["severity"] == "low"


def test_risk_prioritization_identifies_overdue_risks(
    api_client,
    db_session,
    contract_api_data,
):
    data = contract_api_data

    create_risk(
        db_session,
        data["contract_a"],
        rule_id="OVERDUE-001",
        severity="high",
        deadline=date.today() - timedelta(days=5),
    )

    db_session.commit()

    response = api_client.get(
        f"/api/v1/organizations/"
        f"{data['organization_a'].id}/risk-prioritization",
        headers=auth_headers(data["owner_a"]),
    )

    assert response.status_code == 200

    result = response.json()

    assert result["overdue_count"] == 1

    risk = result["prioritized_risks"][0]

    assert risk["urgency"] == "overdue"
    assert risk["days_until_deadline"] == -5


def test_high_impact_low_confidence_risk_is_flagged(
    api_client,
    db_session,
    contract_api_data,
):
    data = contract_api_data

    create_risk(
        db_session,
        data["contract_a"],
        rule_id="UNCERTAIN-001",
        severity="critical",
        assessment_status="provisional",
    )

    db_session.commit()

    response = api_client.get(
        f"/api/v1/organizations/"
        f"{data['organization_a'].id}/risk-prioritization",
        headers=auth_headers(data["owner_a"]),
    )

    assert response.status_code == 200

    result = response.json()

    assert result["high_impact_low_confidence_count"] == 1

    risk = result["prioritized_risks"][0]

    assert (
        "high_impact_low_confidence"
        in risk["attention_flags"]
    )


def test_prioritization_excludes_resolved_risks(
    api_client,
    db_session,
    contract_api_data,
):
    data = contract_api_data

    create_risk(
        db_session,
        data["contract_a"],
        rule_id="OPEN-001",
        severity="high",
    )

    create_risk(
        db_session,
        data["contract_a"],
        rule_id="RESOLVED-001",
        severity="critical",
        status="resolved",
    )

    db_session.commit()

    response = api_client.get(
        f"/api/v1/organizations/"
        f"{data['organization_a'].id}/risk-prioritization",
        headers=auth_headers(data["owner_a"]),
    )

    assert response.status_code == 200

    result = response.json()

    assert result["total_open_risks"] == 1


def test_organization_cannot_access_another_organizations_priorities(
    api_client,
    db_session,
    contract_api_data,
):
    data = contract_api_data

    create_risk(
        db_session,
        data["contract_b"],
        rule_id="B-001",
        severity="critical",
    )
    

    db_session.commit()

    response = api_client.get(
        f"/api/v1/organizations/"
        f"{data['organization_b'].id}/risk-prioritization",
        headers=auth_headers(data["owner_a"]),
    )

    assert response.status_code == 404

def create_risk_with_evidence(
    db_session,
    contract,
    document,
    *,
    verification_status="verified",
):
    finding = create_risk(
        db_session,
        contract,
        assessment_status="confirmed",
    )

    clause = ContractClause(
        document_id=document.id,
        clause_number="8.1",
        clause_title="Automatic Renewal",
        category="renewal",
        source_text="The agreement shall automatically renew.",
        page_number=2,
        char_start=100,
        char_end=150,
        extraction_method="rule_based",
    )

    db_session.add(clause)
    db_session.flush()

    evidence = EvidenceRecord(
        document_id=document.id,
        clause_id=clause.id,
        claim="Automatic renewal provision",
        evidence_type="renewal_period",
        evidence_text="The agreement shall automatically renew.",
        page_number=2,
        char_start=100,
        char_end=150,
        extraction_method="rule_based",
        confidence=0.95,
        verification_status=verification_status,
    )

    db_session.add(evidence)
    db_session.flush()

    link = RiskFindingEvidence(
        risk_finding_id=finding.id,
        evidence_record_id=evidence.id,
    )

    db_session.add(link)
    db_session.flush()

    return finding, evidence

def test_risk_explanation_returns_evidence_and_provenance(
    api_client,
    db_session,
    contract_api_data,
):
    data = contract_api_data

    finding, evidence = create_risk_with_evidence(
        db_session,
        data["contract_a"],
        data["document_a"],
    )

    db_session.commit()

    response = api_client.get(
        f"/api/v1/organizations/{data['organization_a'].id}"
        f"/risk-findings/{finding.id}/explanation",
        headers=auth_headers(data["owner_a"]),
    )

    assert response.status_code == 200
    result = response.json()

    assert result["risk_finding_id"] == str(finding.id)
    assert result["supporting_evidence"]

    source = result["supporting_evidence"][0]

    print("\nACTUAL EVIDENCE RESPONSE:")
    print(source)

    assert source["evidence_id"] == str(evidence.id)
    assert source["document"] == "agreement_a.pdf"
    assert source["page_number"] == 2

    assert source["clause"]["clause_number"] == "8.1"
    assert source["clause"]["clause_title"] == "Automatic Renewal"
    assert source["clause"]["page_number"] == 2
    assert source["clause"]["char_start"] == 100
    assert source["clause"]["char_end"] == 150


def test_risk_explanation_separates_rejected_evidence(
    api_client,
    db_session,
    contract_api_data,
):
    data = contract_api_data

    finding, _ = create_risk_with_evidence(
        db_session,
        data["contract_a"],
        data["document_a"],
        verification_status="rejected",
    )

    db_session.commit()

    response = api_client.get(
        f"/api/v1/organizations/{data['organization_a'].id}"
        f"/risk-findings/{finding.id}/explanation",
        headers=auth_headers(data["owner_a"]),
    )

    assert response.status_code == 200

    result = response.json()

    assert len(result["supporting_evidence"]) == 0
    assert len(result["rejected_evidence"]) == 1


def test_risk_explanation_prevents_cross_organization_access(
    api_client,
    db_session,
    contract_api_data,
):
    data = contract_api_data

    finding = create_risk(
        db_session,
        data["contract_b"],
        rule_id="ORG-B-RISK",
    )

    db_session.commit()

    response = api_client.get(
        f"/api/v1/organizations/{data['organization_a'].id}"
        f"/risk-findings/{finding.id}/explanation",
        headers=auth_headers(data["owner_a"]),
    )

    assert response.status_code == 404


def test_risk_explanation_returns_404_for_missing_finding(
    api_client,
    contract_api_data,
):
    data = contract_api_data

    missing_id = "00000000-0000-0000-0000-000000000001"

    response = api_client.get(
        f"/api/v1/organizations/{data['organization_a'].id}"
        f"/risk-findings/{missing_id}/explanation",
        headers=auth_headers(data["owner_a"]),
    )

    assert response.status_code == 404