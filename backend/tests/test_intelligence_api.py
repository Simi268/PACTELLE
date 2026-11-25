from app.core.security import create_access_token


def auth_headers(user):
    token = create_access_token(user.id)
    return {"Authorization": f"Bearer {token}"}


def test_dashboard_requires_authentication(api_client, contract_api_data):
    response = api_client.get(
        f"/api/v1/organizations/{contract_api_data['organization_a'].id}/dashboard"
    )

    assert response.status_code == 401


def test_dashboard_forbidden_for_non_member(
    api_client,
    contract_api_data,
):
    response = api_client.get(
        f"/api/v1/organizations/{contract_api_data['organization_a'].id}/dashboard",
        headers=auth_headers(contract_api_data["outsider"]),
    )

    assert response.status_code in (403, 404)


def test_dashboard_accessible_to_member(
    api_client,
    contract_api_data,
):
    response = api_client.get(
        f"/api/v1/organizations/{contract_api_data['organization_a'].id}/dashboard",
        headers=auth_headers(contract_api_data["member_a"]),
    )

    assert response.status_code == 200

    data = response.json()

    assert "contracts" in data
    assert "documents" in data
    assert "risks" in data
    assert "monitoring" in data


def test_upcoming_renewals_endpoint(
    api_client,
    contract_api_data,
):
    response = api_client.get(
        f"/api/v1/organizations/{contract_api_data['organization_a'].id}/upcoming-renewals",
        headers=auth_headers(contract_api_data["owner_a"]),
    )

    assert response.status_code == 200

    data = response.json()

    assert "renewals" in data
    assert "total" in data


def test_expiring_contracts_endpoint(
    api_client,
    contract_api_data,
):
    response = api_client.get(
        f"/api/v1/organizations/{contract_api_data['organization_a'].id}/expiring-contracts",
        headers=auth_headers(contract_api_data["owner_a"]),
    )

    assert response.status_code == 200

    data = response.json()

    assert "contracts" in data
    assert "total" in data


def test_risk_overview_endpoint(
    api_client,
    contract_api_data,
):
    response = api_client.get(
        f"/api/v1/organizations/{contract_api_data['organization_a'].id}/risk-overview",
        headers=auth_headers(contract_api_data["owner_a"]),
    )

    assert response.status_code == 200

    data = response.json()

    assert "summary" in data
    assert "open_findings_by_severity" in data
    assert "open_findings_by_assessment" in data
    assert "open_findings_by_type" in data


def test_expiring_contracts_rejects_invalid_days(
    api_client,
    contract_api_data,
):
    response = api_client.get(
        f"/api/v1/organizations/{contract_api_data['organization_a'].id}/expiring-contracts?days=500",
        headers=auth_headers(contract_api_data["owner_a"]),
    )

    assert response.status_code == 422


def test_upcoming_renewals_rejects_invalid_days(
    api_client,
    contract_api_data,
):
    response = api_client.get(
        f"/api/v1/organizations/{contract_api_data['organization_a'].id}/upcoming-renewals?days=0",
        headers=auth_headers(contract_api_data["owner_a"]),
    )

    assert response.status_code == 422
