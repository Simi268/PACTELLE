from uuid import UUID
import logging

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

from datetime import datetime, timezone

logger = logging.getLogger(__name__)


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

    previous_status = document.processing_status

    try:
        document.processing_status = "processing"
        document.processing_started_at = datetime.now(timezone.utc)
        db.commit()

        background_tasks.add_task(
            process_document_pipeline,
            document_id,
        )

    except Exception:
        db.rollback()

        logger.exception(
            "Could not schedule processing for document %s",
            document_id,
        )

        # Restore a retryable state.
        refreshed_document = (
            db.query(ContractDocument)
            .filter(ContractDocument.id == document_id)
            .first()
        
        )

        if refreshed_document is not None:
            refreshed_document.processing_status = previous_status

            try:
                db.commit()
            except Exception:
                db.rollback()
                logger.exception(
                    "Could not restore processing status for %s",
                    document_id,
                
                )

        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Document processing could not be scheduled.",
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