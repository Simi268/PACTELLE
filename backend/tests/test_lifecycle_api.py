from pathlib import Path

from app.core.security import create_access_token
from app.models.contract import Contract
from app.models.document import ContractDocument


def auth_headers(user):
    token = create_access_token(user.id)
    return {"Authorization": f"Bearer {token}"}


# ============================================================
# CONTRACT CREATION TESTS
# ============================================================

def test_owner_can_create_contract(api_client, contract_api_data):
    data = contract_api_data

    response = api_client.post(
        f"/api/v1/contracts/organizations/{data['organization_a'].id}",
        headers=auth_headers(data["owner_a"]),
        json={
            "title": "New Vendor Agreement",
            "contract_type": "vendor",
            "status": "draft"
        }
    )

    assert response.status_code == 201
    assert response.json()["title"] == "New Vendor Agreement"
    assert response.json()["status"] == "draft"


def test_member_cannot_create_contract(api_client, contract_api_data):
    data = contract_api_data

    response = api_client.post(
        f"/api/v1/contracts/organizations/{data['organization_a'].id}",
        headers=auth_headers(data["member_a"]),
        json={
            "title": "Unauthorized Contract",
            "contract_type": "vendor"
        }
    )

    assert response.status_code == 403


def test_outsider_cannot_create_contract(api_client, contract_api_data):
    data = contract_api_data

    response = api_client.post(
        f"/api/v1/contracts/organizations/{data['organization_a'].id}",
        headers=auth_headers(data["outsider"]),
        json={
            "title": "Unauthorized Contract"
        }
    )

    assert response.status_code == 404


def test_invalid_contract_status_rejected(api_client, contract_api_data):
    data = contract_api_data

    response = api_client.post(
        f"/api/v1/contracts/organizations/{data['organization_a'].id}",
        headers=auth_headers(data["owner_a"]),
        json={
            "title": "Invalid Status Contract",
            "status": "pending"
        }
    )

    assert response.status_code == 422


def test_invalid_contract_dates_rejected(api_client, contract_api_data):
    data = contract_api_data

    response = api_client.post(
        f"/api/v1/contracts/organizations/{data['organization_a'].id}",
        headers=auth_headers(data["owner_a"]),
        json={
            "title": "Invalid Date Contract",
            "effective_date": "2026-12-31",
            "expiration_date": "2026-01-01"
        }
    )

    assert response.status_code == 422


# ============================================================
# CONTRACT UPDATE TESTS
# ============================================================

def test_owner_can_update_contract(api_client, contract_api_data):
    data = contract_api_data

    response = api_client.patch(
        f"/api/v1/contracts/{data['contract_a'].id}",
        headers=auth_headers(data["owner_a"]),
        json={
            "title": "Updated Vendor Agreement",
            "status": "active"
        }
    )

    assert response.status_code == 200
    assert response.json()["title"] == "Updated Vendor Agreement"


def test_member_cannot_update_contract(api_client, contract_api_data):
    data = contract_api_data

    response = api_client.patch(
        f"/api/v1/contracts/{data['contract_a'].id}",
        headers=auth_headers(data["member_a"]),
        json={
            "title": "Unauthorized Update"
        }
    )

    assert response.status_code == 403


def test_user_cannot_update_other_organization_contract(
    api_client,
    contract_api_data
):
    data = contract_api_data

    response = api_client.patch(
        f"/api/v1/contracts/{data['contract_b'].id}",
        headers=auth_headers(data["owner_a"]),
        json={
            "title": "Unauthorized Update"
        }
    )

    assert response.status_code == 404


def test_empty_contract_update_rejected(api_client, contract_api_data):
    data = contract_api_data

    response = api_client.patch(
        f"/api/v1/contracts/{data['contract_a'].id}",
        headers=auth_headers(data["owner_a"]),
        json={}
    )

    assert response.status_code == 400


def test_invalid_contract_update_dates_rejected(
    api_client,
    contract_api_data
):
    data = contract_api_data

    response = api_client.patch(
        f"/api/v1/contracts/{data['contract_a'].id}",
        headers=auth_headers(data["owner_a"]),
        json={
            "effective_date": "2026-12-31",
            "expiration_date": "2026-01-01"
        }
    )

    assert response.status_code == 422


# ============================================================
# DOCUMENT PROCESSING STATUS TESTS
# ============================================================

def test_owner_can_update_document_status(api_client, contract_api_data):
    data = contract_api_data

    response = api_client.patch(
        f"/api/v1/documents/{data['document_a'].id}/status",
        headers=auth_headers(data["owner_a"]),
        json={
            "processing_status": "completed"
        }
    )

    assert response.status_code == 200
    assert response.json()["processing_status"] == "completed"


def test_member_cannot_update_document_status(
    api_client,
    contract_api_data
):
    data = contract_api_data

    response = api_client.patch(
        f"/api/v1/documents/{data['document_a'].id}/status",
        headers=auth_headers(data["member_a"]),
        json={
            "processing_status": "completed"
        }
    )

    assert response.status_code == 403


def test_outsider_cannot_update_document_status(
    api_client,
    contract_api_data
):
    data = contract_api_data

    response = api_client.patch(
        f"/api/v1/documents/{data['document_a'].id}/status",
        headers=auth_headers(data["outsider"]),
        json={
            "processing_status": "completed"
        }
    )

    assert response.status_code == 404


def test_invalid_document_status_rejected(api_client, contract_api_data):
    data = contract_api_data

    response = api_client.patch(
        f"/api/v1/documents/{data['document_a'].id}/status",
        headers=auth_headers(data["owner_a"]),
        json={
            "processing_status": "approved"
        }
    )

    assert response.status_code == 422


# ============================================================
# DOCUMENT DELETION TESTS
# ============================================================

def test_owner_can_delete_document_and_physical_file(
    api_client,
    contract_api_data,
    db_session,
    tmp_path,
    monkeypatch
):
    data = contract_api_data
    document = data["document_a"]

    # Use a temporary directory instead of real uploads.
    monkeypatch.setattr(
        "app.api.v1.documents.UPLOAD_DIR",
        tmp_path
    )

    file_path = tmp_path / "stored_a.pdf"
    file_path.write_bytes(b"%PDF-test-content")

    document.storage_path = str(file_path)
    db_session.commit()

    document_id = document.id

    response = api_client.delete(
        f"/api/v1/documents/{document_id}",
        headers=auth_headers(data["owner_a"])
    )

    assert response.status_code == 204
    assert not file_path.exists()

    deleted_document = db_session.query(
        ContractDocument
    ).filter(
        ContractDocument.id == document_id
    ).first()

    assert deleted_document is None


def test_member_cannot_delete_document(
    api_client,
    contract_api_data
):
    data = contract_api_data

    response = api_client.delete(
        f"/api/v1/documents/{data['document_a'].id}",
        headers=auth_headers(data["member_a"])
    )

    assert response.status_code == 403


def test_outsider_cannot_delete_document(
    api_client,
    contract_api_data
):
    data = contract_api_data

    response = api_client.delete(
        f"/api/v1/documents/{data['document_a'].id}",
        headers=auth_headers(data["outsider"])
    )

    assert response.status_code == 404


def test_user_cannot_delete_other_organization_document(
    api_client,
    contract_api_data
):
    data = contract_api_data

    response = api_client.delete(
        f"/api/v1/documents/{data['document_b'].id}",
        headers=auth_headers(data["owner_a"])
    )

    assert response.status_code == 404


def test_delete_document_with_missing_physical_file(
    api_client,
    contract_api_data,
    tmp_path,
    monkeypatch
):
    data = contract_api_data
    document = data["document_a"]

    monkeypatch.setattr(
        "app.api.v1.documents.UPLOAD_DIR",
        tmp_path
    )

    missing_file = tmp_path / "missing.pdf"
    document.storage_path = str(missing_file)

    response = api_client.delete(
        f"/api/v1/documents/{document.id}",
        headers=auth_headers(data["owner_a"])
    )

    assert response.status_code == 204
    assert not missing_file.exists()


def test_delete_rejects_path_outside_upload_directory(
    api_client,
    contract_api_data,
    tmp_path,
    monkeypatch
):
    data = contract_api_data
    document = data["document_a"]

    upload_root = tmp_path / "uploads"
    upload_root.mkdir()

    outside_file = tmp_path / "outside.pdf"
    outside_file.write_bytes(b"test")

    monkeypatch.setattr(
        "app.api.v1.documents.UPLOAD_DIR",
        upload_root
    )

    document.storage_path = str(outside_file)

    response = api_client.delete(
        f"/api/v1/documents/{document.id}",
        headers=auth_headers(data["owner_a"])
    )

    assert response.status_code == 400
    assert outside_file.exists()


def test_database_failure_restores_physical_file(
    api_client,
    contract_api_data,
    db_session,
    tmp_path,
    monkeypatch
):
    data = contract_api_data
    document = data["document_a"]

    monkeypatch.setattr(
        "app.api.v1.documents.UPLOAD_DIR",
        tmp_path
    )

    file_path = tmp_path / "stored_a.pdf"
    file_path.write_bytes(b"%PDF-test-content")

    document.storage_path = str(file_path)
    db_session.commit()

    document_id = document.id

    def failing_commit():
        raise RuntimeError("Simulated database failure")

    monkeypatch.setattr(db_session, "commit", failing_commit)

    response = api_client.delete(
        f"/api/v1/documents/{document_id}",
        headers=auth_headers(data["owner_a"])
    )

    assert response.status_code == 500
    assert file_path.exists()

    # The database rollback should preserve the document record.
    monkeypatch.undo()

    remaining_document = db_session.query(
        ContractDocument
    ).filter(
        ContractDocument.id == document_id
    ).first()

    assert remaining_document is not None