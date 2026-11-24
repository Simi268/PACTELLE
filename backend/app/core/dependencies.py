from uuid import UUID

import jwt

from fastapi import Depends, HTTPException, status
from fastapi.security import (
    HTTPBearer,
    HTTPAuthorizationCredentials
)
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import decode_access_token

from app.models.user import User
from app.models.organization import Organization
from app.models.membership import OrganizationMembership
from app.models.contract import Contract
from app.models.document import ContractDocument


bearer_scheme = HTTPBearer(auto_error=False)

VALID_ROLES = {"owner", "admin", "member"}


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: Session = Depends(get_db)
) -> User:

    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired authentication token.",
        headers={"WWW-Authenticate": "Bearer"}
    )

    if credentials is None:
        raise credentials_exception

    try:
        payload = decode_access_token(credentials.credentials)
        user_id = UUID(payload["sub"])

    except (jwt.InvalidTokenError, ValueError, KeyError):
        raise credentials_exception

    user = db.query(User).filter(
        User.id == user_id
    ).first()

    if user is None:
        raise credentials_exception

    return user


def get_current_active_user(
    current_user: User = Depends(get_current_user)
) -> User:

    if not current_user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Your account has been deactivated."
        )

    return current_user


def get_current_organization(
    organization_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
) -> Organization:

    membership = db.query(OrganizationMembership).filter(
        OrganizationMembership.user_id == current_user.id,
        OrganizationMembership.organization_id == organization_id
    ).first()

    if membership is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have access to this organization."
        )

    organization = db.query(Organization).filter(
        Organization.id == organization_id
    ).first()

    if organization is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Organization not found."
        )

    return organization


def require_organization_role(*allowed_roles: str):

    if not allowed_roles:
        raise ValueError("At least one allowed role must be specified.")

    invalid_roles = set(allowed_roles) - VALID_ROLES

    if invalid_roles:
        raise ValueError(
            f"Invalid organization roles: {invalid_roles}"
        )

    def role_dependency(
        organization_id: UUID,
        current_user: User = Depends(get_current_active_user),
        db: Session = Depends(get_db)
    ) -> OrganizationMembership:

        membership = db.query(OrganizationMembership).filter(
            OrganizationMembership.user_id == current_user.id,
            OrganizationMembership.organization_id == organization_id
        ).first()

        if membership is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Organization not found."
            )

        if membership.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to perform this operation."
            )

        return membership

    return role_dependency


def get_authorized_contract(
    contract_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
) -> Contract:

    contract = (
        db.query(Contract)
        .join(
            OrganizationMembership,
            OrganizationMembership.organization_id == Contract.organization_id
        )
        .filter(
            Contract.id == contract_id,
            OrganizationMembership.user_id == current_user.id
        )
        .first()
    )

    if contract is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Contract not found."
        )

    return contract


def get_authorized_document(
    document_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
) -> ContractDocument:

    document = (
        db.query(ContractDocument)
        .join(
            Contract,
            Contract.id == ContractDocument.contract_id
        )
        .join(
            OrganizationMembership,
            OrganizationMembership.organization_id == Contract.organization_id
        )
        .filter(
            ContractDocument.id == document_id,
            OrganizationMembership.user_id == current_user.id
        )
        .first()
    )

    if document is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found."
        )

    return document

def require_contract_role(*allowed_roles: str):

    if not allowed_roles:
        raise ValueError("At least one allowed role must be specified.")

    invalid_roles = set(allowed_roles) - VALID_ROLES

    if invalid_roles:
        raise ValueError(
            f"Invalid organization roles: {invalid_roles}"
        )

    def contract_role_dependency(
        contract_id: UUID,
        current_user: User = Depends(get_current_active_user),
        db: Session = Depends(get_db)
    ) -> Contract:

        result = (
            db.query(Contract, OrganizationMembership.role)
            .join(
                OrganizationMembership,
                OrganizationMembership.organization_id
                == Contract.organization_id
            )
            .filter(
                Contract.id == contract_id,
                OrganizationMembership.user_id == current_user.id
            )
            .first()
        )

        if result is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Contract not found."
            )

        contract, user_role = result

        if user_role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to perform this operation."
            )

        return contract

    return contract_role_dependency