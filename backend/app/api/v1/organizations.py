from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import require_organization_role

from app.models.user import User
from app.models.membership import OrganizationMembership

from app.schemas.organization import (
    OrganizationMemberResponse,
    OrganizationMemberInviteRequest,
    OrganizationMemberRoleUpdateRequest
)




router = APIRouter(
    prefix="/organizations",
    tags=["Organizations"]
)


@router.get(
    "/{organization_id}/members",
    response_model=list[OrganizationMemberResponse]
)
def list_organization_members(
    organization_id: UUID,
    membership: OrganizationMembership = Depends(
        require_organization_role("owner", "admin")
    ),
    db: Session = Depends(get_db)
):

    members = (
        db.query(OrganizationMembership, User)
        .join(
            User,
            User.id == OrganizationMembership.user_id
        )
        .filter(
            OrganizationMembership.organization_id == organization_id
        )
        .order_by(OrganizationMembership.created_at.asc())
        .all()
    )

    return [
        OrganizationMemberResponse(
            user_id=user.id,
            full_name=user.full_name,
            email=user.email,
            role=member_membership.role,
            joined_at=member_membership.created_at
        )
        for member_membership, user in members
    ]


@router.post(
    "/{organization_id}/members",
    response_model=OrganizationMemberResponse,
    status_code=status.HTTP_201_CREATED
)
def invite_organization_member(
    organization_id: UUID,
    request: OrganizationMemberInviteRequest,
    current_membership: OrganizationMembership = Depends(
        require_organization_role("owner", "admin")
    ),
    db: Session = Depends(get_db)
):

    email = str(request.email).strip().lower()
    requested_role = request.role.strip().lower()

    if requested_role not in {"admin", "member"}:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Role must be either 'admin' or 'member'."
        )

    user = db.query(User).filter(
        func.lower(User.email) == email
    ).first()

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No registered user exists with this email."
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot add an inactive user."
        )

    existing_membership = db.query(
        OrganizationMembership
    ).filter(
        OrganizationMembership.organization_id == organization_id,
        OrganizationMembership.user_id == user.id
    ).first()

    if existing_membership:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="User is already a member of this organization."
        )

    new_membership = OrganizationMembership(
        organization_id=organization_id,
        user_id=user.id,
        role=requested_role
    )

    try:
        db.add(new_membership)
        db.commit()
        db.refresh(new_membership)

    except IntegrityError:
        db.rollback()

        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Unable to add member. Membership may already exist."
        )

    return OrganizationMemberResponse(
        user_id=user.id,
        full_name=user.full_name,
        email=user.email,
        role=new_membership.role,
        joined_at=new_membership.created_at
    )
@router.delete(
    "/{organization_id}/members/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT
)
def remove_organization_member(
    organization_id: UUID,
    user_id: UUID,
    current_membership: OrganizationMembership = Depends(
        require_organization_role("owner", "admin")
    ),
    db: Session = Depends(get_db)
):
    # Prevent users from removing themselves through this endpoint.
    if current_membership.user_id == user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You cannot remove yourself using this endpoint."
        )

    # Find the target user's membership.
    target_membership = (
        db.query(OrganizationMembership)
        .filter(
            OrganizationMembership.organization_id == organization_id,
            OrganizationMembership.user_id == user_id
        )
        .first()
    )

    if not target_membership:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Organization member not found."
        )

    # Organization owners cannot be removed.
    if target_membership.role == "owner":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="The organization owner cannot be removed."
        )

    # Admins cannot remove other admins.
    if (
        current_membership.role == "admin"
        and target_membership.role == "admin"
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admins cannot remove other admins."
        )

    db.delete(target_membership)
    db.commit()

    return None

@router.patch(
    "/{organization_id}/members/{user_id}/role",
    response_model=OrganizationMemberResponse
)
def update_organization_member_role(
    organization_id: UUID,
    user_id: UUID,
    request: OrganizationMemberRoleUpdateRequest,
    current_membership: OrganizationMembership = Depends(
        require_organization_role("owner")
    ),
    db: Session = Depends(get_db)
):
    # Find the target membership.
    target_membership = (
        db.query(OrganizationMembership)
        .filter(
            OrganizationMembership.organization_id == organization_id,
            OrganizationMembership.user_id == user_id
        )
        .first()
    )

    if target_membership is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Organization member not found."
        )

    # Protect the organization owner.
    if target_membership.role == "owner":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="The organization owner's role cannot be changed."
        )

    # Update the role.
    target_membership.role = request.role

    try:
        db.commit()
        db.refresh(target_membership)

    except IntegrityError:
        db.rollback()

        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Unable to update member role."
        )

    user = db.query(User).filter(
        User.id == user_id
    ).first()

    return OrganizationMemberResponse(
        user_id=user.id,
        full_name=user.full_name,
        email=user.email,
        role=target_membership.role,
        joined_at=target_membership.created_at
    )

@router.delete(
    "/{organization_id}/leave",
    status_code=status.HTTP_204_NO_CONTENT
)
def leave_organization(
    organization_id: UUID,
    current_membership: OrganizationMembership = Depends(
        require_organization_role("owner", "admin", "member")
    ),
    db: Session = Depends(get_db)
):
    # Owners must transfer ownership before leaving.
    if current_membership.role == "owner":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Organization owners must transfer ownership before leaving."
        )

    db.delete(current_membership)
    db.commit()

    return None