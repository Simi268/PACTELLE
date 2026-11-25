import logging
import uuid

from pathlib import Path

from fastapi import (
    APIRouter,
    UploadFile,
    File,
    Depends,
    HTTPException,
    status
)

from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import (
    get_authorized_contract,
    get_authorized_document,
    require_document_role
)

from app.models.contract import Contract
from app.models.document import ContractDocument

from app.services.document_storage import (
    save_document,
    UPLOAD_DIR
)

from app.schemas.document import (
    DocumentResponse,
    DocumentStatusUpdateRequest
)


logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/documents",
    tags=["Documents"]
)


# 1. Upload a document
@router.post("/upload/{contract_id}")
async def upload_document(
    contract: Contract = Depends(get_authorized_contract),
    file: UploadFile = File(...),
    db: Session = Depends(get_db)
):

    file_data = await save_document(file)

    document = ContractDocument(
        contract_id=contract.id,
        original_filename=file_data["original_filename"],
        stored_filename=file_data["stored_filename"],
        storage_path=file_data["storage_path"],
        file_type=file_data["file_type"],
        file_size=file_data["file_size"],
        processing_status="uploaded"
    )

    try:
        db.add(document)
        db.commit()
        db.refresh(document)

    except Exception:
        db.rollback()

        Path(file_data["storage_path"]).unlink(missing_ok=True)

        raise HTTPException(
            status_code=500,
            detail="Document registration failed."
        )

    return {
        "message": "Document uploaded successfully",
        "document_id": str(document.id),
        "filename": document.original_filename,
        "status": document.processing_status
    }


# 2. View document details
@router.get(
    "/{document_id}",
    response_model=DocumentResponse
)
def get_document_details(
    document: ContractDocument = Depends(get_authorized_document)
):
    return document


# 3. Update document processing status
@router.patch(
    "/{document_id}/status",
    response_model=DocumentResponse
)
def update_document_status(
    request: DocumentStatusUpdateRequest,
    document: ContractDocument = Depends(
        require_document_role("owner", "admin")
    ),
    db: Session = Depends(get_db)
):

    document.processing_status = request.processing_status

    db.commit()
    db.refresh(document)

    return document


# 4. Delete document and its physical file
@router.delete(
    "/{document_id}",
    status_code=status.HTTP_204_NO_CONTENT
)
def delete_document(
    document: ContractDocument = Depends(
        require_document_role("owner", "admin")
    ),
    db: Session = Depends(get_db)
):

    upload_root = Path(UPLOAD_DIR).resolve()
    file_path = Path(document.storage_path).resolve()

    # Prevent deletion outside the configured upload directory.
    if (
        file_path == upload_root
        or not file_path.is_relative_to(upload_root)
    ):
        raise HTTPException(
            status_code=400,
            detail="Invalid document storage path."
        )

    quarantine_path = file_path.with_name(
        f"{file_path.name}.deleting-{uuid.uuid4().hex}"
    )

    file_moved = False

    try:
        # Move the file first instead of permanently deleting it.
        if file_path.exists():
            file_path.rename(quarantine_path)
            file_moved = True

        # Delete the database record.
        # Related clauses, evidence and evidence links are handled
        # by the existing database cascade configuration.
        db.delete(document)
        db.commit()

    except Exception:
        db.rollback()

        # Restore the file if the database operation failed.
        if file_moved and quarantine_path.exists():
            quarantine_path.rename(file_path)

        logger.exception(
            "Document deletion failed for document %s",
            document.id
        )

        raise HTTPException(
            status_code=500,
            detail="Document deletion failed."
        )

    # Database deletion succeeded. Permanently remove the quarantined file.
    if file_moved:
        try:
            quarantine_path.unlink(missing_ok=True)
        except OSError:
            logger.exception(
                "Could not remove quarantined file for document %s",
                document.id
            )

    return None