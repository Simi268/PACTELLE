from datetime import datetime, timezone
from uuid import UUID, uuid4
import logging

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import get_authorized_document
from app.models.document import ContractDocument
from app.orchestration.document_processing_runner import (
    run_document_processing,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/documents", tags=["Document Intelligence"])


@router.post("/{document_id}/process", status_code=status.HTTP_202_ACCEPTED)
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
    previous_started_at = document.processing_started_at
    previous_attempt_id = document.processing_attempt_id
    attempt_id = uuid4()

    try:
        # Resolve organization ownership while the request session is active.
        organization_id = document.contract.organization_id

        document.processing_status = "processing"
        document.processing_started_at = datetime.now(timezone.utc)
        document.processing_attempt_id = attempt_id
        db.commit()

        background_tasks.add_task(
            run_document_processing,
            document_id,
            attempt_id,
            organization_id,
        )

    except Exception:
        db.rollback()
        logger.exception(
            "Could not schedule processing for document %s",
            document_id,
        )

        refreshed_document = (
            db.query(ContractDocument)
            .filter(ContractDocument.id == document_id)
            .first()
        )

        if refreshed_document is not None:
            refreshed_document.processing_status = previous_status
            refreshed_document.processing_started_at = previous_started_at
            refreshed_document.processing_attempt_id = previous_attempt_id

            try:
                db.commit()
            except Exception:
                db.rollback()
                logger.exception(
                    "Could not restore processing state for %s",
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
        "processing_attempt_id": str(attempt_id),
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
        "processing_started_at": document.processing_started_at,
        "processed_at": document.processed_at,
    }