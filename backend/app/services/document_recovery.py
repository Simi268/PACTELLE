from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.models.document import ContractDocument


DEFAULT_STALE_THRESHOLD_MINUTES = 15


def find_stale_processing_documents(
    db: Session,
    stale_after_minutes: int = DEFAULT_STALE_THRESHOLD_MINUTES,
):
    """
    Identify documents that may have been abandoned during processing.

    This function only identifies candidates.
    It does not change document status or schedule retries.
    """

    if stale_after_minutes <= 0:
        raise ValueError(
            "Stale threshold must be greater than zero."
        )

    cutoff_time = (
        datetime.now(timezone.utc)
        - timedelta(minutes=stale_after_minutes)
    )

    stale_documents = (
        db.query(ContractDocument)
        .filter(
            ContractDocument.processing_status == "processing",
            (
                (ContractDocument.processing_started_at.is_(None))
                |
                (
                    ContractDocument.processing_started_at
                    < cutoff_time
                )
            ),
        )
        .order_by(
            ContractDocument.processing_started_at.asc()
        )
        .all()
    )

    return stale_documents