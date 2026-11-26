from app.models.portfolio_risk_finding import PortfolioRiskFinding

from app.services.portfolio_analysis_service import (
    run_organization_portfolio_analysis,
)

from tests.test_portfolio_finding_service import (
    prepare_valid_data,
)


def test_portfolio_analysis_completes_for_organization(
    db_session,
    contract_api_data,
):
    data, _, _, _ = prepare_valid_data(
        db_session,
        contract_api_data,
    )

    result = run_organization_portfolio_analysis(
        db_session,
        data["organization_a"].id,
    )

    assert result["status"] == "completed"

    assert result["organization_id"] == str(
        data["organization_a"].id
    )

    assert "retrieval" in result
    assert "intelligence" in result
    assert "generation" in result
    assert "persistence" in result


def test_portfolio_analysis_does_not_mix_organizations(
    db_session,
    contract_api_data,
):
    data = contract_api_data

    prepare_valid_data(db_session, data)

    result = run_organization_portfolio_analysis(
        db_session,
        data["organization_a"].id,
    )

    assert result["organization_id"] == str(
        data["organization_a"].id
    )

    assert result["retrieval"]["contracts_with_obligations"] == 2


def test_repeated_analysis_does_not_duplicate_active_findings(
    db_session,
    contract_api_data,
):
    data = contract_api_data

    prepare_valid_data(db_session, data)

    first = run_organization_portfolio_analysis(
        db_session,
        data["organization_a"].id,
    )

    second = run_organization_portfolio_analysis(
        db_session,
        data["organization_a"].id,
    )

    assert first["persistence"]["created_count"] >= 0

    assert second["persistence"]["created_count"] == 0

    findings = (
        db_session.query(PortfolioRiskFinding)
        .filter(
            PortfolioRiskFinding.organization_id
            == data["organization_a"].id
        )
        .all()
    )

    assert len(findings) == first["persistence"]["created_count"]


def test_analysis_can_be_rolled_back(
    db_session,
    contract_api_data,
):
    data = contract_api_data

    prepare_valid_data(db_session, data)

    result = run_organization_portfolio_analysis(
        db_session,
        data["organization_a"].id,
        commit=False,
    )

    assert result["status"] == "completed"

    db_session.rollback()

    findings = (
        db_session.query(PortfolioRiskFinding)
        .filter(
            PortfolioRiskFinding.organization_id
            == data["organization_a"].id
        )
        .all()
    )

    assert findings == []