import uuid

import pytest

from fastapi.testclient import TestClient

from app.main import app
from app.core.database import get_db
from app.core.security import create_access_token

from app.models.user import User
from app.models.organization import Organization
from app.models.membership import OrganizationMembership
from app.models.contract import Contract
from app.models.document import ContractDocument

from fastapi import HTTPException

from app.core.dependencies import require_contract_role

@pytest.fixture
def client(db_session):

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()


@pytest.fixture
def two_organizations(db_session):

    organization_a = Organization(
        name="Organization A"
    )

    organization_b = Organization(
        name="Organization B"
    )

    user_a = User(
        full_name="User A",
        email="usera@example.com",
        password_hash="test_hash",
        is_active=True
    )

    user_b = User(
        full_name="User B",
        email="userb@example.com",
        password_hash="test_hash",
        is_active=True
    )

    db_session.add_all([
        organization_a,
        organization_b,
        user_a,
        user_b
    ])

    db_session.flush()

    membership_a = OrganizationMembership(
        organization_id=organization_a.id,
        user_id=user_a.id,
        role="owner"
    )

    membership_b = OrganizationMembership(
        organization_id=organization_b.id,
        user_id=user_b.id,
        role="owner"
    )

    contract_a = Contract(
        organization_id=organization_a.id,
        title="Contract A",
        status="active"
    )

    contract_b = Contract(
        organization_id=organization_b.id,
        title="Contract B",
        status="active"
    )

    db_session.add_all([
        membership_a,
        membership_b,
        contract_a,
        contract_b
    ])

    db_session.flush()

    document_a = ContractDocument(
        contract_id=contract_a.id,
        original_filename="contract_a.pdf",
        stored_filename="contract_a.pdf",
        storage_path="uploads/contract_a.pdf",
        file_type="pdf",
        file_size=100,
        processing_status="uploaded"
    )

    document_b = ContractDocument(
        contract_id=contract_b.id,
        original_filename="contract_b.pdf",
        stored_filename="contract_b.pdf",
        storage_path="uploads/contract_b.pdf",
        file_type="pdf",
        file_size=100,
        processing_status="uploaded"
    )

    db_session.add_all([
        document_a,
        document_b
    ])

    db_session.commit()

    return {
        "user_a": user_a,
        "user_b": user_b,
        "document_a": document_a,
        "document_b": document_b
    }


def test_user_can_access_own_document(
    client,
    two_organizations
):

    user = two_organizations["user_a"]
    document = two_organizations["document_a"]

    token = create_access_token(user.id)

    response = client.get(
        f"/api/v1/documents/{document.id}/text",
        headers={
            "Authorization": f"Bearer {token}"
        }
    )

    assert response.status_code == 200


def test_user_cannot_access_other_organization_document(
    client,
    two_organizations
):

    user = two_organizations["user_a"]
    document = two_organizations["document_b"]

    token = create_access_token(user.id)

    response = client.get(
        f"/api/v1/documents/{document.id}/text",
        headers={
            "Authorization": f"Bearer {token}"
        }
    )

    assert response.status_code == 404


def test_unauthenticated_user_cannot_access_document(
    client,
    two_organizations
):

    document = two_organizations["document_a"]

    response = client.get(
        f"/api/v1/documents/{document.id}/text"
    )

    assert response.status_code == 401
@pytest.mark.parametrize(
    "method,endpoint",
    [
        ("POST", "/api/v1/documents/{document_id}/extract"),
        ("POST", "/api/v1/documents/{document_id}/segment"),
        ("POST", "/api/v1/documents/{document_id}/extract-evidence"),
        ("GET", "/api/v1/documents/{document_id}/text"),
    ],
)
def test_user_cannot_operate_on_another_organization_document(
    client, two_organizations, method, endpoint
):
    user = two_organizations["user_a"]
    document = two_organizations["document_b"]

    token = create_access_token(user.id)

    url = endpoint.format(document_id=document.id)

    response = client.request(
        method,
        url,
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 404


def test_user_cannot_upload_to_another_organization_contract(
    client, two_organizations
):
    user = two_organizations["user_a"]
    document = two_organizations["document_b"]

    token = create_access_token(user.id)

    response = client.post(
        f"/api/v1/documents/upload/{document.contract_id}",
        headers={"Authorization": f"Bearer {token}"},
        files={
            "file": (
                "unauthorized.pdf",
                b"%PDF-1.4 test content",
                "application/pdf",
            )
        },
    )

    assert response.status_code == 404

@pytest.mark.parametrize(
    "method,endpoint",
    [
        ("POST", "/api/v1/documents/{document_id}/extract"),
        ("POST", "/api/v1/documents/{document_id}/segment"),
        ("POST", "/api/v1/documents/{document_id}/extract-evidence"),
        ("GET", "/api/v1/documents/{document_id}/text"),
    ],
)
def test_unauthenticated_user_cannot_operate_on_document(
    client, two_organizations, method, endpoint
):
    document = two_organizations["document_a"]
    url = endpoint.format(document_id=document.id)

    response = client.request(method, url)

    assert response.status_code == 401

@pytest.fixture
def rbac_organization(db_session):

    organization = Organization(name="RBAC Test Organization")

    owner = User(
        full_name="Owner User",
        email="owner@rbac.com",
        password_hash="test_hash",
        is_active=True
    )

    admin = User(
        full_name="Admin User",
        email="admin@rbac.com",
        password_hash="test_hash",
        is_active=True
    )

    member = User(
        full_name="Member User",
        email="member@rbac.com",
        password_hash="test_hash",
        is_active=True
    )

    outsider = User(
        full_name="Outsider User",
        email="outsider@rbac.com",
        password_hash="test_hash",
        is_active=True
    )

    db_session.add_all([
        organization,
        owner,
        admin,
        member,
        outsider
    ])

    db_session.flush()

    memberships = [
        OrganizationMembership(
            organization_id=organization.id,
            user_id=owner.id,
            role="owner"
        ),
        OrganizationMembership(
            organization_id=organization.id,
            user_id=admin.id,
            role="admin"
        ),
        OrganizationMembership(
            organization_id=organization.id,
            user_id=member.id,
            role="member"
        )
    ]

    contract = Contract(
        organization_id=organization.id,
        title="RBAC Test Contract",
        status="active"
    )

    db_session.add_all(memberships + [contract])
    db_session.commit()

    return {
        "organization": organization,
        "owner": owner,
        "admin": admin,
        "member": member,
        "outsider": outsider,
        "contract": contract
    }

def test_owner_can_access_admin_operation(rbac_organization, db_session):

    contract = rbac_organization["contract"]
    owner = rbac_organization["owner"]

    dependency = require_contract_role("owner", "admin")

    result = dependency(
        contract_id=contract.id,
        current_user=owner,
        db=db_session
    )

    assert result.id == contract.id


def test_admin_can_access_admin_operation(rbac_organization, db_session):

    contract = rbac_organization["contract"]
    admin = rbac_organization["admin"]

    dependency = require_contract_role("owner", "admin")

    result = dependency(
        contract_id=contract.id,
        current_user=admin,
        db=db_session
    )

    assert result.id == contract.id


def test_member_cannot_access_admin_operation(rbac_organization, db_session):

    contract = rbac_organization["contract"]
    member = rbac_organization["member"]

    dependency = require_contract_role("owner", "admin")

    with pytest.raises(HTTPException) as exc:
        dependency(
            contract_id=contract.id,
            current_user=member,
            db=db_session
        )

    assert exc.value.status_code == 403


def test_member_can_access_analysis_operation(rbac_organization, db_session):

    contract = rbac_organization["contract"]
    member = rbac_organization["member"]

    dependency = require_contract_role("owner", "admin", "member")

    result = dependency(
        contract_id=contract.id,
        current_user=member,
        db=db_session
    )

    assert result.id == contract.id


def test_outsider_cannot_access_contract(rbac_organization, db_session):

    contract = rbac_organization["contract"]
    outsider = rbac_organization["outsider"]

    dependency = require_contract_role("owner", "admin")

    with pytest.raises(HTTPException) as exc:
        dependency(
            contract_id=contract.id,
            current_user=outsider,
            db=db_session
        )

    assert exc.value.status_code == 404


def test_invalid_role_is_rejected():

    with pytest.raises(ValueError):
        require_contract_role("superadmin")


def test_empty_role_list_is_rejected():

    with pytest.raises(ValueError):
        require_contract_role()

def test_owner_can_list_organization_members(
    client, rbac_organization
):
    owner = rbac_organization["owner"]
    organization = rbac_organization["organization"]

    token = create_access_token(owner.id)

    response = client.get(
        f"/api/v1/organizations/{organization.id}/members",
        headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 200
    assert len(response.json()) == 3


def test_admin_can_list_organization_members(
    client, rbac_organization
):
    admin = rbac_organization["admin"]
    organization = rbac_organization["organization"]

    token = create_access_token(admin.id)

    response = client.get(
        f"/api/v1/organizations/{organization.id}/members",
        headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 200
    assert len(response.json()) == 3


def test_member_cannot_list_organization_members(
    client, rbac_organization
):
    member = rbac_organization["member"]
    organization = rbac_organization["organization"]

    token = create_access_token(member.id)

    response = client.get(
        f"/api/v1/organizations/{organization.id}/members",
        headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 403


def test_outsider_cannot_list_organization_members(
    client, rbac_organization
):
    outsider = rbac_organization["outsider"]
    organization = rbac_organization["organization"]

    token = create_access_token(outsider.id)

    response = client.get(
        f"/api/v1/organizations/{organization.id}/members",
        headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 404


def test_unauthenticated_user_cannot_list_organization_members(
    client, rbac_organization
):
    organization = rbac_organization["organization"]

    response = client.get(
        f"/api/v1/organizations/{organization.id}/members"
    )

    assert response.status_code == 401

def test_owner_can_invite_member(
    client, rbac_organization
):
    owner = rbac_organization["owner"]
    organization = rbac_organization["organization"]
    outsider = rbac_organization["outsider"]

    token = create_access_token(owner.id)

    response = client.post(
        f"/api/v1/organizations/{organization.id}/members",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "email": outsider.email,
            "role": "member"
        }
    )

    assert response.status_code == 201
    assert response.json()["email"] == outsider.email
    assert response.json()["role"] == "member"


def test_owner_can_invite_admin(
    client, rbac_organization
):
    owner = rbac_organization["owner"]
    organization = rbac_organization["organization"]
    outsider = rbac_organization["outsider"]

    token = create_access_token(owner.id)

    response = client.post(
        f"/api/v1/organizations/{organization.id}/members",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "email": outsider.email,
            "role": "admin"
        }
    )

    assert response.status_code == 201
    assert response.json()["role"] == "admin"


def test_admin_can_invite_member(
    client, rbac_organization
):
    admin = rbac_organization["admin"]
    organization = rbac_organization["organization"]
    outsider = rbac_organization["outsider"]

    token = create_access_token(admin.id)

    response = client.post(
        f"/api/v1/organizations/{organization.id}/members",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "email": outsider.email,
            "role": "member"
        }
    )

    assert response.status_code == 201


def test_duplicate_membership_is_rejected(
    client, rbac_organization
):
    owner = rbac_organization["owner"]
    organization = rbac_organization["organization"]

    token = create_access_token(owner.id)

    response = client.post(
        f"/api/v1/organizations/{organization.id}/members",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "email": owner.email,
            "role": "member"
        }
    )

    assert response.status_code == 409


def test_inviting_unknown_email_is_rejected(
    client, rbac_organization
):
    owner = rbac_organization["owner"]
    organization = rbac_organization["organization"]

    token = create_access_token(owner.id)

    response = client.post(
        f"/api/v1/organizations/{organization.id}/members",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "email": "unknown@example.com",
            "role": "member"
        }
    )

    assert response.status_code == 404


def test_member_cannot_invite_users(
    client, rbac_organization
):
    member = rbac_organization["member"]
    organization = rbac_organization["organization"]
    outsider = rbac_organization["outsider"]

    token = create_access_token(member.id)

    response = client.post(
        f"/api/v1/organizations/{organization.id}/members",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "email": outsider.email,
            "role": "member"
        }
    )

    assert response.status_code == 403


def test_outsider_cannot_invite_users(
    client, rbac_organization
):
    outsider = rbac_organization["outsider"]
    organization = rbac_organization["organization"]
    member = rbac_organization["member"]

    token = create_access_token(outsider.id)

    response = client.post(
        f"/api/v1/organizations/{organization.id}/members",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "email": member.email,
            "role": "member"
        }
    )

    assert response.status_code == 404


def test_unauthenticated_user_cannot_invite_members(
    client, rbac_organization
):
    organization = rbac_organization["organization"]
    outsider = rbac_organization["outsider"]

    response = client.post(
        f"/api/v1/organizations/{organization.id}/members",
        json={
            "email": outsider.email,
            "role": "member"
        }
    )

    assert response.status_code == 401

def test_owner_can_remove_member(
    client, rbac_organization, db_session
):
    owner = rbac_organization["owner"]
    member = rbac_organization["member"]
    organization = rbac_organization["organization"]

    token = create_access_token(owner.id)

    response = client.delete(
        f"/api/v1/organizations/{organization.id}/members/{member.id}",
        headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 204

    membership = (
        db_session.query(OrganizationMembership)
        .filter(
            OrganizationMembership.organization_id == organization.id,
            OrganizationMembership.user_id == member.id
        )
        .first()
    )

    assert membership is None


def test_owner_can_remove_admin(
    client, rbac_organization, db_session
):
    owner = rbac_organization["owner"]
    admin = rbac_organization["admin"]
    organization = rbac_organization["organization"]

    token = create_access_token(owner.id)

    response = client.delete(
        f"/api/v1/organizations/{organization.id}/members/{admin.id}",
        headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 204


def test_admin_can_remove_member(
    client, rbac_organization
):
    admin = rbac_organization["admin"]
    member = rbac_organization["member"]
    organization = rbac_organization["organization"]

    token = create_access_token(admin.id)

    response = client.delete(
        f"/api/v1/organizations/{organization.id}/members/{member.id}",
        headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 204


def test_admin_cannot_remove_another_admin(
    client, rbac_organization
):
    admin = rbac_organization["admin"]
    owner = rbac_organization["owner"]
    organization = rbac_organization["organization"]

    # The owner is also protected, so this checks the owner safeguard.
    token = create_access_token(admin.id)

    response = client.delete(
        f"/api/v1/organizations/{organization.id}/members/{owner.id}",
        headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 403


def test_member_cannot_remove_users(
    client, rbac_organization
):
    member = rbac_organization["member"]
    owner = rbac_organization["owner"]
    organization = rbac_organization["organization"]

    token = create_access_token(member.id)

    response = client.delete(
        f"/api/v1/organizations/{organization.id}/members/{owner.id}",
        headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 403


def test_outsider_cannot_remove_members(
    client, rbac_organization
):
    outsider = rbac_organization["outsider"]
    member = rbac_organization["member"]
    organization = rbac_organization["organization"]

    token = create_access_token(outsider.id)

    response = client.delete(
        f"/api/v1/organizations/{organization.id}/members/{member.id}",
        headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 404


def test_user_cannot_remove_themselves(
    client, rbac_organization
):
    owner = rbac_organization["owner"]
    organization = rbac_organization["organization"]

    token = create_access_token(owner.id)

    response = client.delete(
        f"/api/v1/organizations/{organization.id}/members/{owner.id}",
        headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 400


def test_unauthenticated_user_cannot_remove_members(
    client, rbac_organization
):
    member = rbac_organization["member"]
    organization = rbac_organization["organization"]

    response = client.delete(
        f"/api/v1/organizations/{organization.id}/members/{member.id}"
    )

    assert response.status_code == 401

def test_owner_can_promote_member_to_admin(
    client, rbac_organization
):
    owner = rbac_organization["owner"]
    member = rbac_organization["member"]
    organization = rbac_organization["organization"]

    token = create_access_token(owner.id)

    response = client.patch(
        f"/api/v1/organizations/{organization.id}/members/{member.id}/role",
        headers={"Authorization": f"Bearer {token}"},
        json={"role": "admin"}
    )

    assert response.status_code == 200
    assert response.json()["role"] == "admin"


def test_owner_can_demote_admin_to_member(
    client, rbac_organization
):
    owner = rbac_organization["owner"]
    admin = rbac_organization["admin"]
    organization = rbac_organization["organization"]

    token = create_access_token(owner.id)

    response = client.patch(
        f"/api/v1/organizations/{organization.id}/members/{admin.id}/role",
        headers={"Authorization": f"Bearer {token}"},
        json={"role": "member"}
    )

    assert response.status_code == 200
    assert response.json()["role"] == "member"


def test_admin_cannot_change_member_role(
    client, rbac_organization
):
    admin = rbac_organization["admin"]
    member = rbac_organization["member"]
    organization = rbac_organization["organization"]

    token = create_access_token(admin.id)

    response = client.patch(
        f"/api/v1/organizations/{organization.id}/members/{member.id}/role",
        headers={"Authorization": f"Bearer {token}"},
        json={"role": "admin"}
    )

    assert response.status_code == 403


def test_member_cannot_change_roles(
    client, rbac_organization
):
    member = rbac_organization["member"]
    admin = rbac_organization["admin"]
    organization = rbac_organization["organization"]

    token = create_access_token(member.id)

    response = client.patch(
        f"/api/v1/organizations/{organization.id}/members/{admin.id}/role",
        headers={"Authorization": f"Bearer {token}"},
        json={"role": "member"}
    )

    assert response.status_code == 403


def test_owner_role_cannot_be_changed(
    client, rbac_organization
):
    owner = rbac_organization["owner"]
    organization = rbac_organization["organization"]

    token = create_access_token(owner.id)

    response = client.patch(
        f"/api/v1/organizations/{organization.id}/members/{owner.id}/role",
        headers={"Authorization": f"Bearer {token}"},
        json={"role": "member"}
    )

    assert response.status_code == 403


def test_outsider_cannot_change_member_role(
    client, rbac_organization
):
    outsider = rbac_organization["outsider"]
    member = rbac_organization["member"]
    organization = rbac_organization["organization"]

    token = create_access_token(outsider.id)

    response = client.patch(
        f"/api/v1/organizations/{organization.id}/members/{member.id}/role",
        headers={"Authorization": f"Bearer {token}"},
        json={"role": "admin"}
    )

    assert response.status_code == 404

def test_member_can_leave_organization(
    client, rbac_organization, db_session
):
    member = rbac_organization["member"]
    organization = rbac_organization["organization"]

    token = create_access_token(member.id)

    response = client.delete(
        f"/api/v1/organizations/{organization.id}/leave",
        headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 204

    membership = db_session.query(OrganizationMembership).filter(
        OrganizationMembership.organization_id == organization.id,
        OrganizationMembership.user_id == member.id
    ).first()

    assert membership is None


def test_admin_can_leave_organization(
    client, rbac_organization, db_session
):
    admin = rbac_organization["admin"]
    organization = rbac_organization["organization"]

    token = create_access_token(admin.id)

    response = client.delete(
        f"/api/v1/organizations/{organization.id}/leave",
        headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 204

    membership = db_session.query(OrganizationMembership).filter(
        OrganizationMembership.organization_id == organization.id,
        OrganizationMembership.user_id == admin.id
    ).first()

    assert membership is None


def test_owner_cannot_leave_organization(
    client, rbac_organization, db_session
):
    owner = rbac_organization["owner"]
    organization = rbac_organization["organization"]

    token = create_access_token(owner.id)

    response = client.delete(
        f"/api/v1/organizations/{organization.id}/leave",
        headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 403

    membership = db_session.query(OrganizationMembership).filter(
        OrganizationMembership.organization_id == organization.id,
        OrganizationMembership.user_id == owner.id
    ).first()

    assert membership is not None
    assert membership.role == "owner"


def test_outsider_cannot_leave_organization(
    client, rbac_organization
):
    outsider = rbac_organization["outsider"]
    organization = rbac_organization["organization"]

    token = create_access_token(outsider.id)

    response = client.delete(
        f"/api/v1/organizations/{organization.id}/leave",
        headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 404


def test_unauthenticated_user_cannot_leave_organization(
    client, rbac_organization
):
    organization = rbac_organization["organization"]

    response = client.delete(
        f"/api/v1/organizations/{organization.id}/leave"
    )

    assert response.status_code == 401