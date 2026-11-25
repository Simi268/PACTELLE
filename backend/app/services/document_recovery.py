from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.models.document import ContractDocument


DEFAULT_STALE_THRESHOLD_MINUTES = 15
DEFAULT_RECOVERY_BATCH_SIZE = 50


def find_stale_processing_documents(
    db: Session,
    stale_after_minutes: int = DEFAULT_STALE_THRESHOLD_MINUTES,
):
    """Return stale processing documents without modifying them."""
    if stale_after_minutes <= 0:
        raise ValueError("Stale threshold must be greater than zero.")

    cutoff_time = datetime.now(timezone.utc) - timedelta(
        minutes=stale_after_minutes
    )

    return (
        db.query(ContractDocument)
        .filter(
            ContractDocument.processing_status == "processing",
            (
                ContractDocument.processing_started_at.is_(None)
                | (ContractDocument.processing_started_at < cutoff_time)
            ),
        )
        .order_by(ContractDocument.processing_started_at.asc())
        .all()
    )


def claim_stale_processing_documents(
    db: Session,
    stale_after_minutes: int = DEFAULT_STALE_THRESHOLD_MINUTES,
    batch_size: int = DEFAULT_RECOVERY_BATCH_SIZE,
):
    """Atomically invalidate stale attempts and mark documents failed.

    PostgreSQL row locks with SKIP LOCKED prevent multiple recovery workers
    from claiming the same document. Clearing processing_attempt_id fences
    off the old worker: its next ownership check will fail.
    """
    if stale_after_minutes <= 0:
        raise ValueError("Stale threshold must be greater than zero.")
    if batch_size <= 0:
        raise ValueError("Batch size must be greater than zero.")

    cutoff_time = datetime.now(timezone.utc) - timedelta(
        minutes=stale_after_minutes
    )

    try:
        stale_documents = (
            db.query(ContractDocument)
            .filter(
                ContractDocument.processing_status == "processing",
                (
                    ContractDocument.processing_started_at.is_(None)
                    | (ContractDocument.processing_started_at < cutoff_time)
                ),
            )
            .order_by(ContractDocument.processing_started_at.asc())
            .limit(batch_size)
            .with_for_update(skip_locked=True)
            .all()
        )

        claimed_ids = []
        for document in stale_documents:
            document.processing_status = "failed"
            document.processing_started_at = None
            document.processing_attempt_id = None
            claimed_ids.append(document.id)

        db.commit()
        return claimed_ids
    except Exception:
        db.rollback()
        raise
