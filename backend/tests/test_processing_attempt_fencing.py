from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

from app.api.v1 import document_processing
from app.core.security import create_access_token
from app.models.document import ContractDocument
from app.services.document_recovery import claim_stale_processing_documents


def test_recovery_invalidates_stale_processing_attempt(
    db_session, contract_api_data
):
    document = contract_api_data["document_a"]
    old_attempt_id = uuid4()
    document.processing_status = "processing"
    document.processing_attempt_id = old_attempt_id
    document.processing_started_at = (
        datetime.now(timezone.utc) - timedelta(minutes=45)
    )
    db_session.commit()

    claimed = claim_stale_processing_documents(db_session, stale_after_minutes=15)

    assert document.id in claimed
    db_session.refresh(document)
    assert document.processing_status == "failed"
    assert document.processing_attempt_id is None
    assert document.processing_started_at is None


def test_new_attempt_token_is_not_invalidated_by_recovery(
    db_session, contract_api_data
):
    document = contract_api_data["document_a"]
    current_attempt_id = uuid4()
    document.processing_status = "processing"
    document.processing_attempt_id = current_attempt_id
    document.processing_started_at = datetime.now(timezone.utc)
    db_session.commit()

    claimed = claim_stale_processing_documents(db_session, stale_after_minutes=15)

    assert document.id not in claimed
    db_session.refresh(document)
    assert document.processing_status == "processing"
    assert document.processing_attempt_id == current_attempt_id


def test_superseded_worker_cannot_change_document_or_intelligence(
    monkeypatch, tmp_path, db_session, contract_api_data
):
    import app.services.document_pipeline as pipeline
    from sqlalchemy.orm import sessionmaker

    document = contract_api_data["document_a"]
    current_attempt_id = uuid4()
    stale_attempt_id = uuid4()
    document.processing_status = "processing"
    document.processing_attempt_id = current_attempt_id
    document.processing_started_at = datetime.now(timezone.utc)
    db_session.commit()

    connection = db_session.connection()
    test_session_local = sessionmaker(
        bind=connection, autoflush=False, autocommit=False,
        join_transaction_mode="create_savepoint",
    )
    monkeypatch.setattr(pipeline, "SessionLocal", test_session_local)
    monkeypatch.setattr(pipeline, "_backend_root", lambda: tmp_path)
    monkeypatch.setattr(
        pipeline, "extract_document",
        lambda file_path, file_type: [{
            "unit_index": 0, "page_number": 1,
            "text": "1. Services\nThe vendor provides support.",
        }],
    )

    file_path = tmp_path / document.storage_path
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_bytes(b"test")

    result = pipeline.process_document_pipeline(document.id, stale_attempt_id)

    assert result["status"] == "superseded"
    db_session.refresh(document)
    assert document.processing_status == "processing"
    assert document.processing_attempt_id == current_attempt_id
    assert document.processing_started_at is not None


def test_start_processing_assigns_and_schedules_attempt_token(
    api_client, contract_api_data, db_session, monkeypatch
):
    document = contract_api_data["document_a"]
    owner = contract_api_data["owner_a"]
    organization_id = contract_api_data["organization_a"].id
    scheduled = {}

    def capture_task(self, func, *args, **kwargs):
        scheduled["func"] = func
        scheduled["args"] = args

    monkeypatch.setattr(
        document_processing.BackgroundTasks, "add_task", capture_task
    )

    response = api_client.post(
        f"/api/v1/documents/{document.id}/process",
        headers={"Authorization": f"Bearer {create_access_token(owner.id)}"},
    )

    assert response.status_code == 202

    attempt_id = UUID(response.json()["processing_attempt_id"])

    assert scheduled["func"] is document_processing.run_document_processing
    assert scheduled["args"] == (
        document.id,
        attempt_id,
        organization_id,
    )

    db_session.expire_all()

    refreshed = db_session.query(ContractDocument).filter(
        ContractDocument.id == document.id
    ).one()

    assert refreshed.processing_status == "processing"
    assert refreshed.processing_attempt_id == attempt_id
    assert refreshed.processing_started_at is not None
