from app.core.security import create_access_token
# 1. Owner can list organization contracts
def test_owner_can_list_contracts(
    api_client, contract_api_data
):
    data = contract_api_data
    token = create_access_token(data["owner_a"].id)

    response = api_client.get(
        f"/api/v1/contracts/organizations/{data['organization_a'].id}",
        headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 200
    assert len(response.json()) == 2


# 2. Member can list organization contracts
def test_member_can_list_contracts(
    api_client, contract_api_data
):
    data = contract_api_data
    token = create_access_token(data["member_a"].id)

    response = api_client.get(
        f"/api/v1/contracts/organizations/{data['organization_a'].id}",
        headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 200
    assert len(response.json()) == 2


# 3. Outsider cannot list another organization's contracts
def test_outsider_cannot_list_contracts(
    api_client, contract_api_data
):
    data = contract_api_data
    token = create_access_token(data["outsider"].id)

    response = api_client.get(
        f"/api/v1/contracts/organizations/{data['organization_a'].id}",
        headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 404


# 4. Unauthenticated user cannot list contracts
def test_unauthenticated_user_cannot_list_contracts(
    api_client, contract_api_data
):
    organization = contract_api_data["organization_a"]

    response = api_client.get(
        f"/api/v1/contracts/organizations/{organization.id}"
    )

    assert response.status_code == 401


# 5. User can view their own contract
def test_user_can_view_own_contract(
    api_client, contract_api_data
):
    data = contract_api_data
    token = create_access_token(data["owner_a"].id)

    response = api_client.get(
        f"/api/v1/contracts/{data['contract_a'].id}",
        headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 200
    assert response.json()["title"] == "Vendor Agreement A"


# 6. User cannot view another organization's contract
def test_user_cannot_view_other_organization_contract(
    api_client, contract_api_data
):
    data = contract_api_data
    token = create_access_token(data["owner_a"].id)

    response = api_client.get(
        f"/api/v1/contracts/{data['contract_b'].id}",
        headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 404


# 7. User can list documents belonging to their contract
def test_user_can_list_contract_documents(
    api_client, contract_api_data
):
    data = contract_api_data
    token = create_access_token(data["owner_a"].id)

    response = api_client.get(
        f"/api/v1/contracts/{data['contract_a'].id}/documents",
        headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 200
    assert len(response.json()) == 1
    assert response.json()[0]["original_filename"] == "agreement_a.pdf"


# 8. Empty contract returns an empty document list
def test_empty_contract_returns_empty_document_list(
    api_client, contract_api_data
):
    data = contract_api_data
    token = create_access_token(data["owner_a"].id)

    response = api_client.get(
        f"/api/v1/contracts/{data['empty_contract'].id}/documents",
        headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 200
    assert response.json() == []


# 9. User cannot list documents from another organization's contract
def test_user_cannot_list_other_organization_documents(
    api_client, contract_api_data
):
    data = contract_api_data
    token = create_access_token(data["owner_a"].id)

    response = api_client.get(
        f"/api/v1/contracts/{data['contract_b'].id}/documents",
        headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 404


# 10. User can view their own document
def test_user_can_view_own_document(
    api_client, contract_api_data
):
    data = contract_api_data
    token = create_access_token(data["owner_a"].id)

    response = api_client.get(
        f"/api/v1/documents/{data['document_a'].id}",
        headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 200
    assert response.json()["original_filename"] == "agreement_a.pdf"


# 11. User cannot view another organization's document
def test_user_cannot_view_other_organization_document(
    api_client, contract_api_data
):
    data = contract_api_data
    token = create_access_token(data["owner_a"].id)

    response = api_client.get(
        f"/api/v1/documents/{data['document_b'].id}",
        headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 404


# 12. Unauthenticated user cannot view a document
def test_unauthenticated_user_cannot_view_document(
    api_client, contract_api_data
):
    document = contract_api_data["document_a"]

    response = api_client.get(
        f"/api/v1/documents/{document.id}"
    )

    assert response.status_code == 401


# 13. Internal storage paths must not be exposed
def test_document_response_does_not_expose_storage_paths(
    api_client, contract_api_data
):
    data = contract_api_data
    token = create_access_token(data["owner_a"].id)

    response = api_client.get(
        f"/api/v1/documents/{data['document_a'].id}",
        headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 200

    response_data = response.json()

    assert "storage_path" not in response_data
    assert "stored_filename" not in response_data# 1. Owner can list organization contracts
def test_owner_can_list_contracts(
    api_client, contract_api_data
):
    data = contract_api_data
    token = create_access_token(data["owner_a"].id)

    response = api_client.get(
        f"/api/v1/contracts/organizations/{data['organization_a'].id}",
        headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 200
    assert len(response.json()) == 2


# 2. Member can list organization contracts
def test_member_can_list_contracts(
    api_client, contract_api_data
):
    data = contract_api_data
    token = create_access_token(data["member_a"].id)

    response = api_client.get(
        f"/api/v1/contracts/organizations/{data['organization_a'].id}",
        headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 200
    assert len(response.json()) == 2


# 3. Outsider cannot list another organization's contracts
def test_outsider_cannot_list_contracts(
    api_client, contract_api_data
):
    data = contract_api_data
    token = create_access_token(data["outsider"].id)

    response = api_client.get(
        f"/api/v1/contracts/organizations/{data['organization_a'].id}",
        headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 404


# 4. Unauthenticated user cannot list contracts
def test_unauthenticated_user_cannot_list_contracts(
    api_client, contract_api_data
):
    organization = contract_api_data["organization_a"]

    response = api_client.get(
        f"/api/v1/contracts/organizations/{organization.id}"
    )

    assert response.status_code == 401


# 5. User can view their own contract
def test_user_can_view_own_contract(
    api_client, contract_api_data
):
    data = contract_api_data
    token = create_access_token(data["owner_a"].id)

    response = api_client.get(
        f"/api/v1/contracts/{data['contract_a'].id}",
        headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 200
    assert response.json()["title"] == "Vendor Agreement A"


# 6. User cannot view another organization's contract
def test_user_cannot_view_other_organization_contract(
    api_client, contract_api_data
):
    data = contract_api_data
    token = create_access_token(data["owner_a"].id)

    response = api_client.get(
        f"/api/v1/contracts/{data['contract_b'].id}",
        headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 404


# 7. User can list documents belonging to their contract
def test_user_can_list_contract_documents(
    api_client, contract_api_data
):
    data = contract_api_data
    token = create_access_token(data["owner_a"].id)

    response = api_client.get(
        f"/api/v1/contracts/{data['contract_a'].id}/documents",
        headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 200
    assert len(response.json()) == 1
    assert response.json()[0]["original_filename"] == "agreement_a.pdf"


# 8. Empty contract returns an empty document list
def test_empty_contract_returns_empty_document_list(
    api_client, contract_api_data
):
    data = contract_api_data
    token = create_access_token(data["owner_a"].id)

    response = api_client.get(
        f"/api/v1/contracts/{data['empty_contract'].id}/documents",
        headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 200
    assert response.json() == []


# 9. User cannot list documents from another organization's contract
def test_user_cannot_list_other_organization_documents(
    api_client, contract_api_data
):
    data = contract_api_data
    token = create_access_token(data["owner_a"].id)

    response = api_client.get(
        f"/api/v1/contracts/{data['contract_b'].id}/documents",
        headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 404


# 10. User can view their own document
def test_user_can_view_own_document(
    api_client, contract_api_data
):
    data = contract_api_data
    token = create_access_token(data["owner_a"].id)

    response = api_client.get(
        f"/api/v1/documents/{data['document_a'].id}",
        headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 200
    assert response.json()["original_filename"] == "agreement_a.pdf"


# 11. User cannot view another organization's document
def test_user_cannot_view_other_organization_document(
    api_client, contract_api_data
):
    data = contract_api_data
    token = create_access_token(data["owner_a"].id)

    response = api_client.get(
        f"/api/v1/documents/{data['document_b'].id}",
        headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 404


# 12. Unauthenticated user cannot view a document
def test_unauthenticated_user_cannot_view_document(
    api_client, contract_api_data
):
    document = contract_api_data["document_a"]

    response = api_client.get(
        f"/api/v1/documents/{document.id}"
    )

    assert response.status_code == 401


# 13. Internal storage paths must not be exposed
def test_document_response_does_not_expose_storage_paths(
    api_client, contract_api_data
):
    data = contract_api_data
    token = create_access_token(data["owner_a"].id)

    response = api_client.get(
        f"/api/v1/documents/{data['document_a'].id}",
        headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 200

    response_data = response.json()

    assert "storage_path" not in response_data
    assert "stored_filename" not in response_data
