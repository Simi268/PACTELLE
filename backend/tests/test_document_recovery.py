from datetime import datetime, timedelta, timezone

import pytest

from app.services.document_recovery import (
    find_stale_processing_documents,
)

from app.models.document import ContractDocument


def test_finds_documents_stuck_in_processing(
    db_session,
    contract_api_data,
):
    document = contract_api_data["document_a"]

    document.processing_status = "processing"
    document.processing_started_at = (
        datetime.now(timezone.utc) - timedelta(minutes=20)
    )

    db_session.commit()

    stale_documents = find_stale_processing_documents(
        db_session,
        stale_after_minutes=15,
    )

    assert document.id in {
        item.id for item in stale_documents
    }


def test_ignores_recently_processing_documents(
    db_session,
    contract_api_data,
):
    document = contract_api_data["document_a"]

    document.processing_status = "processing"
    document.processing_started_at = (
        datetime.now(timezone.utc) - timedelta(minutes=5)
    )

    db_session.commit()

    stale_documents = find_stale_processing_documents(
        db_session,
        stale_after_minutes=15,
    )

    assert document.id not in {
        item.id for item in stale_documents
    }


def test_ignores_completed_documents(
    db_session,
    contract_api_data,
):
    document = contract_api_data["document_a"]

    document.processing_status = "completed"
    document.processing_started_at = (
        datetime.now(timezone.utc) - timedelta(minutes=30)
    )

    db_session.commit()

    stale_documents = find_stale_processing_documents(
        db_session,
        stale_after_minutes=15,
    )

    assert document.id not in {
        item.id for item in stale_documents
    }


def test_finds_processing_documents_with_missing_timestamp(
    db_session,
    contract_api_data,
):
    document = contract_api_data["document_a"]

    document.processing_status = "processing"
    document.processing_started_at = None

    db_session.commit()

    stale_documents = find_stale_processing_documents(
        db_session,
        stale_after_minutes=15,
    )

    assert document.id in {
        item.id for item in stale_documents
    }


def test_rejects_invalid_stale_threshold(
    db_session,
):
    with pytest.raises(ValueError):
        find_stale_processing_documents(
            db_session,
            stale_after_minutes=0,
        )

    with pytest.raises(ValueError):
        find_stale_processing_documents(
            db_session,
            stale_after_minutes=-5,
        )


def test_detection_does_not_modify_document_status(
    db_session,
    contract_api_data,
):
    document = contract_api_data["document_a"]

    document.processing_status = "processing"
    document.processing_started_at = (
        datetime.now(timezone.utc) - timedelta(minutes=30)
    )

    db_session.commit()

    find_stale_processing_documents(db_session)

    db_session.refresh(document)

    assert document.processing_status == "processing"

def test_claim_stale_documents_marks_them_failed(
    db_session,
    contract_api_data,
):
    from app.services.document_recovery import (
        claim_stale_processing_documents,
    )

    document = contract_api_data["document_a"]

    previous_processed_at = datetime.now(timezone.utc) - timedelta(days=2)

    document.processing_status = "processing"
    document.processing_started_at = (
        datetime.now(timezone.utc) - timedelta(minutes=30)
    )
    document.processed_at = previous_processed_at

    db_session.commit()

    claimed_ids = claim_stale_processing_documents(
        db_session,
        stale_after_minutes=15,
    )

    assert document.id in claimed_ids

    db_session.refresh(document)

    assert document.processing_status == "failed"
    assert document.processing_started_at is None
    assert document.processed_at == previous_processed_at


def test_claim_does_not_modify_recent_documents(
    db_session,
    contract_api_data,
):
    from app.services.document_recovery import (
        claim_stale_processing_documents,
    )

    document = contract_api_data["document_a"]

    document.processing_status = "processing"
    document.processing_started_at = (
        datetime.now(timezone.utc) - timedelta(minutes=5)
    )

    db_session.commit()

    claimed_ids = claim_stale_processing_documents(db_session)

    assert document.id not in claimed_ids

    db_session.refresh(document)

    assert document.processing_status == "processing"


def test_claim_rejects_invalid_batch_size(
    db_session,
):
    from app.services.document_recovery import (
        claim_stale_processing_documents,
    )

    with pytest.raises(ValueError):
        claim_stale_processing_documents(
            db_session,
            batch_size=0,
        )


def test_claim_respects_batch_size(
    db_session,
    contract_api_data,
):
    from app.services.document_recovery import (
        claim_stale_processing_documents,
    )

    document_a = contract_api_data["document_a"]
    document_b = contract_api_data["document_b"]

    for document in [document_a, document_b]:
        document.processing_status = "processing"
        document.processing_started_at = (
            datetime.now(timezone.utc) - timedelta(minutes=30)
        )

    db_session.commit()

    claimed_ids = claim_stale_processing_documents(
        db_session,
        stale_after_minutes=15,
        batch_size=1,
    )

    assert len(claimed_ids) == 1

    db_session.refresh(document_a)
    db_session.refresh(document_b)

    assert sorted([
        document_a.processing_status,
        document_b.processing_status,
    ]) == ["failed", "processing"]