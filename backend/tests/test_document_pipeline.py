from datetime import date

from sqlalchemy import func
from sqlalchemy.orm import sessionmaker

import app.services.document_pipeline as pipeline

from app.models.clause import ContractClause
from app.models.document import ContractDocument
from app.models.evidence_record import EvidenceRecord
from app.models.risk_finding import RiskFinding
from app.models.risk_finding_evidence import RiskFindingEvidence


RENEWAL_TEXT = (
    "3. Term and Automatic Renewal\n"
    "This Agreement automatically renews for successive "
    "twelve (12) month periods.\n"
    "Either party must provide notice of non-renewal "
    "at least thirty (30) days before the end of the current term."
)


SERVICES_TEXT = (
    "3. Services\n"
    "The Vendor shall provide software implementation services."
)


def configure_pipeline(
    monkeypatch,
    db_session,
    tmp_path,
    extracted_units,
):
    """
    Configure the pipeline to use the test database connection
    and a temporary document storage directory.
    """

    document_root = tmp_path

    connection = db_session.connection()

    TestSessionLocal = sessionmaker(
        bind=connection,
        autoflush=False,
        autocommit=False,
        join_transaction_mode="create_savepoint",
    )

    monkeypatch.setattr(
        pipeline,
        "SessionLocal",
        TestSessionLocal,
    )

    monkeypatch.setattr(
        pipeline,
        "_backend_root",
        lambda: document_root,
    )

    monkeypatch.setattr(
        pipeline,
        "extract_document",
        lambda file_path, file_type: extracted_units,
    )


def create_test_file(document, tmp_path):
    """
    Create a temporary file at the path expected by the pipeline.
    """

    file_path = tmp_path / document.storage_path

    file_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    file_path.write_bytes(b"test document content")

    return file_path


def get_evidence_records(db_session, document_id):
    return (
        db_session.query(EvidenceRecord)
        .filter(
            EvidenceRecord.document_id == document_id
        )
        .order_by(EvidenceRecord.evidence_type.asc())
        .all()
    )


def test_reprocessing_preserves_evidence_ids_and_verification(
    monkeypatch,
    tmp_path,
    db_session,
    contract_api_data,
):
    document = contract_api_data["document_a"]

    configure_pipeline(
        monkeypatch,
        db_session,
        tmp_path,
        [
            {
                "unit_index": 0,
                "page_number": 1,
                "text": RENEWAL_TEXT,
            }
        ],
    )

    create_test_file(document, tmp_path)

    # First processing.
    pipeline.process_document_pipeline(document.id)

    db_session.expire_all()

    first_records = get_evidence_records(
        db_session,
        document.id,
    )

    print("\nEXTRACTED EVIDENCE:")

    for record in first_records:
        print({
        "type": record.evidence_type,
        "claim": record.claim,
        "text": record.evidence_text,
    })

    assert len(first_records) == 2

    original_ids = {
        record.evidence_type: record.id
        for record in first_records
    }

    # Assign different verification states.
    for record in first_records:
        if record.evidence_type == "renewal_period":
            record.verification_status = "verified"

        elif record.evidence_type == "renewal_notice":
            record.verification_status = "rejected"

    db_session.commit()

    # Process the same document again.
    pipeline.process_document_pipeline(document.id)

    db_session.expire_all()

    second_records = get_evidence_records(
        db_session,
        document.id,
    )

    assert len(second_records) == 2

    for record in second_records:
        assert record.id == original_ids[record.evidence_type]

    verification_states = {
        record.evidence_type: record.verification_status
        for record in second_records
    }

    assert verification_states["renewal_period"] == "verified"
    assert verification_states["renewal_notice"] == "rejected"

    refreshed_document = db_session.query(
        ContractDocument
    ).filter(
        ContractDocument.id == document.id
    ).one()

    assert refreshed_document.processing_status == "completed"


def test_reprocessing_removes_stale_evidence_and_links(
    monkeypatch,
    tmp_path,
    db_session,
    contract_api_data,
):
    document = contract_api_data["document_a"]
    contract = contract_api_data["contract_a"]

    configure_pipeline(
        monkeypatch,
        db_session,
        tmp_path,
        [
            {
                "unit_index": 0,
                "page_number": 1,
                "text": RENEWAL_TEXT,
            }
        ],
    )

    create_test_file(document, tmp_path)

    # First processing creates renewal evidence.
    pipeline.process_document_pipeline(document.id)

    db_session.expire_all()

    evidence_records = get_evidence_records(
        db_session,
        document.id,
    )

    assert len(evidence_records) == 2

    # Create an existing finding linked to the evidence.
    finding = RiskFinding(
        contract_id=contract.id,
        risk_type="renewal_exposure",
        title="Automatic Renewal Exposure",
        description="Test renewal risk.",
        severity="medium",
        status="open",
        assessment_status="confirmed",
        detection_method="rule_based",
        rule_id="RENEWAL-001",
        rule_version="1.0",
        deadline_date=date(2026, 12, 1),
    )

    db_session.add(finding)
    db_session.flush()

    db_session.add(
        RiskFindingEvidence(
            risk_finding_id=finding.id,
            evidence_record_id=evidence_records[0].id,
        )
    )

    db_session.commit()

    # Change the document so renewal evidence is no longer extracted.
    configure_pipeline(
        monkeypatch,
        db_session,
        tmp_path,
        [
            {
                "unit_index": 0,
                "page_number": 1,
                "text": SERVICES_TEXT,
            }
        ],
    )

    pipeline.process_document_pipeline(document.id)

    db_session.expire_all()

    remaining_evidence = get_evidence_records(
        db_session,
        document.id,
    )

    assert len(remaining_evidence) == 0

    remaining_links = db_session.query(
        RiskFindingEvidence
    ).filter(
        RiskFindingEvidence.risk_finding_id == finding.id
    ).count()

    assert remaining_links == 0

    db_session.refresh(finding)

    assert finding.status == "open"
    assert finding.assessment_status == "provisional"


def test_empty_extraction_preserves_existing_evidence(
    monkeypatch,
    tmp_path,
    db_session,
    contract_api_data,
):
    document = contract_api_data["document_a"]

    configure_pipeline(
        monkeypatch,
        db_session,
        tmp_path,
        [
            {
                "unit_index": 0,
                "page_number": 1,
                "text": RENEWAL_TEXT,
            }
        ],
    )

    create_test_file(document, tmp_path)

    # First processing.
    pipeline.process_document_pipeline(document.id)

    db_session.expire_all()

    original_records = get_evidence_records(
        db_session,
        document.id,
    )

    original_ids = {
        record.id
        for record in original_records
    }

    assert len(original_ids) == 2

    # Simulate a document that needs OCR.
    configure_pipeline(
        monkeypatch,
        db_session,
        tmp_path,
        [],
    )

    pipeline.process_document_pipeline(document.id)

    db_session.expire_all()

    remaining_records = get_evidence_records(
        db_session,
        document.id,
    )

    assert {
        record.id
        for record in remaining_records
    } == original_ids

    refreshed_document = db_session.query(
        ContractDocument
    ).filter(
        ContractDocument.id == document.id
    ).one()

    assert refreshed_document.processing_status == "needs_ocr"


def test_extraction_failure_preserves_existing_evidence(
    monkeypatch,
    tmp_path,
    db_session,
    contract_api_data,
):
    document = contract_api_data["document_a"]

    configure_pipeline(
        monkeypatch,
        db_session,
        tmp_path,
        [
            {
                "unit_index": 0,
                "page_number": 1,
                "text": RENEWAL_TEXT,
            }
        ],
    )

    create_test_file(document, tmp_path)

    # First processing.
    pipeline.process_document_pipeline(document.id)

    db_session.expire_all()

    original_records = get_evidence_records(
        db_session,
        document.id,
    )

    original_ids = {
        record.id
        for record in original_records
    }

    assert len(original_ids) == 2

    # Simulate parser failure.
    def failing_extractor(file_path, file_type):
        raise RuntimeError("Simulated extraction failure")

    monkeypatch.setattr(
        pipeline,
        "extract_document",
        failing_extractor,
    )

    pipeline.process_document_pipeline(document.id)

    db_session.expire_all()

    remaining_records = get_evidence_records(
        db_session,
        document.id,
    )

    assert {
        record.id
        for record in remaining_records
    } == original_ids

    refreshed_document = db_session.query(
        ContractDocument
    ).filter(
        ContractDocument.id == document.id
    ).one()

    assert refreshed_document.processing_status == "failed"