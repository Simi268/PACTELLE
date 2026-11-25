from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import (
    require_organization_role,
    get_authorized_contract
)

from app.models.contract import Contract
from app.models.document import ContractDocument
from app.models.membership import OrganizationMembership

from app.schemas.contract import ContractResponse
from app.schemas.document import DocumentResponse

from fastapi import HTTPException, status

from app.core.dependencies import require_contract_role

from app.schemas.contract import (
    ContractCreateRequest,
    ContractUpdateRequest
)


router = APIRouter(
    prefix="/contracts",
    tags=["Contracts"]
)


# 1. List contracts belonging to an organization
@router.get(
    "/organizations/{organization_id}",
    response_model=list[ContractResponse]
)
def list_organization_contracts(
    organization_id: UUID,
    membership: OrganizationMembership = Depends(
        require_organization_role("owner", "admin", "member")
    ),
    db: Session = Depends(get_db)
):

    contracts = (
        db.query(Contract)
        .filter(
            Contract.organization_id == organization_id
        )
        .order_by(Contract.created_at.desc())
        .all()
    )

    return contracts


# 2. View individual contract details
@router.get(
    "/{contract_id}",
    response_model=ContractResponse
)
def get_contract_details(
    contract: Contract = Depends(get_authorized_contract)
):

    return contract


# 3. List documents belonging to a contract
@router.get(
    "/{contract_id}/documents",
    response_model=list[DocumentResponse]
)
def list_contract_documents(
    contract: Contract = Depends(get_authorized_contract),
    db: Session = Depends(get_db)
):

    documents = (
        db.query(ContractDocument)
        .filter(
            ContractDocument.contract_id == contract.id
        )
        .order_by(ContractDocument.created_at.desc())
        .all()
    )

    return documents
@router.post(
    "/organizations/{organization_id}",
    response_model=ContractResponse,
    status_code=status.HTTP_201_CREATED
)
def create_contract(
    organization_id: UUID,
    request: ContractCreateRequest,
    membership: OrganizationMembership = Depends(
        require_organization_role("owner", "admin")
    ),
    db: Session = Depends(get_db)
):
    if (
        request.effective_date
        and request.expiration_date
        and request.expiration_date < request.effective_date
    ):
        raise HTTPException(
            status_code=422,
            detail="Expiration date cannot be before effective date."
        )

    contract = Contract(
        organization_id=organization_id,
        title=request.title,
        contract_type=request.contract_type,
        status=request.status,
        effective_date=request.effective_date,
        expiration_date=request.expiration_date
    )

    db.add(contract)
    db.commit()
    db.refresh(contract)

    return contract

@router.patch(
    "/{contract_id}",
    response_model=ContractResponse
)
def update_contract(
    request: ContractUpdateRequest,
    contract: Contract = Depends(
        require_contract_role("owner", "admin")
    ),
    db: Session = Depends(get_db)
):
    updates = request.model_dump(exclude_unset=True)

    if not updates:
        raise HTTPException(
            status_code=400,
            detail="No update fields were provided."
        )

    effective_date = updates.get(
        "effective_date",
        contract.effective_date
    )

    expiration_date = updates.get(
        "expiration_date",
        contract.expiration_date
    )

    if (
        effective_date
        and expiration_date
        and expiration_date < effective_date
    ):
        raise HTTPException(
            status_code=422,
            detail="Expiration date cannot be before effective date."
        )

    for field, value in updates.items():
        setattr(contract, field, value)

    db.commit()
    db.refresh(contract)

    return contract