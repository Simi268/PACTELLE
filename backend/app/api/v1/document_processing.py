from uuid import UUID

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    HTTPException,
    status,
)

from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import get_authorized_document

from app.models.document import ContractDocument

from app.services.document_pipeline import process_document_pipeline


router = APIRouter(
    prefix="/documents",
    tags=["Document Intelligence"],
)


@router.post(
    "/{document_id}/process",
    status_code=status.HTTP_202_ACCEPTED,
)
def start_document_processing(
    document_id: UUID,
    background_tasks: BackgroundTasks,
    document: ContractDocument = Depends(get_authorized_document),
    db: Session = Depends(get_db),
):
    if document.processing_status == "processing":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Document is already being processed.",
        )

    document.processing_status = "processing"
    db.commit()

    background_tasks.add_task(
        process_document_pipeline,
        document_id,
    )

    return {
        "message": "Document processing started.",
        "document_id": str(document_id),
        "processing_status": "processing",
    }


@router.get("/{document_id}/processing-status")
def get_document_processing_status(
    document_id: UUID,
    document: ContractDocument = Depends(get_authorized_document),
):
    return {
        "document_id": str(document.id),
        "processing_status": document.processing_status,
        "filename": document.original_filename,
    }