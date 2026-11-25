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