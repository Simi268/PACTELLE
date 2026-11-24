from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from app.core.dependencies import get_current_active_user
from app.core.database import get_db
from app.core.security import (
    hash_password,
    verify_password,
    create_access_token
)

from app.models.user import User
from app.models.organization import Organization
from app.models.membership import OrganizationMembership

from app.schemas.auth import (
    RegisterRequest,
    LoginRequest,
    AuthResponse,
    UserResponse,
    OrganizationResponse
)


router = APIRouter(
    prefix="/auth",
    tags=["Authentication"]
)


@router.post(
    "/register",
    response_model=AuthResponse,
    status_code=status.HTTP_201_CREATED
)
def register(
    request: RegisterRequest,
    db: Session = Depends(get_db)
):
    email = str(request.email).strip().lower()

    existing_user = db.query(User).filter(
        func.lower(User.email) == email
    ).first()

    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists."
        )

    try:
        user = User(
            full_name=request.full_name.strip(),
            email=email,
            password_hash=hash_password(request.password),
            is_active=True
        )

        organization = Organization(
            name=request.organization_name.strip()
        )

        db.add(user)
        db.add(organization)

        db.flush()

        membership = OrganizationMembership(
            user_id=user.id,
            organization_id=organization.id,
            role="owner"
        )

        db.add(membership)

        db.commit()

        db.refresh(user)
        db.refresh(organization)

    except IntegrityError:
        db.rollback()

        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Unable to create account. The email may already be registered."
        )

    except Exception:
        db.rollback()
        raise

    access_token = create_access_token(user.id)

    return AuthResponse(
        access_token=access_token,
        user=UserResponse.model_validate(user),
        organization=OrganizationResponse.model_validate(organization)
    )


@router.post(
    "/login",
    response_model=AuthResponse
)
def login(
    request: LoginRequest,
    db: Session = Depends(get_db)
):
    email = str(request.email).strip().lower()

    user = db.query(User).filter(
        func.lower(User.email) == email
    ).first()

    if not user or not verify_password(
        request.password,
        user.password_hash
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
            headers={"WWW-Authenticate": "Bearer"}
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This account has been deactivated."
        )

    membership = db.query(OrganizationMembership).filter(
        OrganizationMembership.user_id == user.id
    ).order_by(OrganizationMembership.created_at.asc()).first()

    if not membership:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Your account is not associated with an organization."
        )

    organization = db.query(Organization).filter(
        Organization.id == membership.organization_id
    ).first()

    if not organization:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Your organization could not be found."
        )

    access_token = create_access_token(user.id)

    return AuthResponse(
        access_token=access_token,
        user=UserResponse.model_validate(user),
        organization=OrganizationResponse.model_validate(organization)
    )

@router.get("/me", response_model=UserResponse)
def get_me(
    current_user: User = Depends(get_current_active_user)
):
    return current_user