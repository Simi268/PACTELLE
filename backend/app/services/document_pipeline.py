from pathlib import Path
import logging
from datetime import datetime, timezone
from uuid import UUID

from app.core.database import SessionLocal
from app.models.document import ContractDocument
from app.models.document_text import DocumentTextUnit
from app.models.clause import ContractClause
from app.models.evidence_record import EvidenceRecord
from app.services.document_parser import extract_document
from app.services.clause_segmenter import segment_clauses
from app.services.evidence_extractor import extract_evidence_from_clause
from app.services.risk_engine import (
    detect_automatic_renewal_risk,
    capture_risk_history_context,
)

logger = logging.getLogger(__name__)


class SupersededProcessingAttempt(Exception):
    """Raised when a worker no longer owns the document processing attempt."""


def _backend_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _evidence_key(item):
    fields = (
        "evidence_type", "claim", "evidence_text",
        "page_number", "char_start", "char_end",
    )

    def get_value(field):
        if isinstance(item, dict):
            return item.get(field)
        return getattr(item, field)

    return tuple(get_value(field) for field in fields)


def _get_existing_verifications(db, document_id):
    records = (
        db.query(EvidenceRecord)
        .filter(EvidenceRecord.document_id == document_id)
        .all()
    )
    return {
        _evidence_key(record): {
            "verification_status": record.verification_status,
            "record": record,
        }
        for record in records
    }


def _replace_text_units(db, document_id, extracted_units):
    db.query(DocumentTextUnit).filter(
        DocumentTextUnit.document_id == document_id
    ).delete(synchronize_session=False)

    for unit in extracted_units:
        text = unit["text"]
        db.add(DocumentTextUnit(
            document_id=document_id,
            unit_index=unit["unit_index"],
            page_number=unit.get("page_number"),
            extracted_text=text,
            character_count=len(text),
        ))
    db.flush()


def _replace_clauses(db, document_id):
    units = (
        db.query(DocumentTextUnit)
        .filter(DocumentTextUnit.document_id == document_id)
        .order_by(DocumentTextUnit.unit_index.asc())
        .all()
    )
    clause_data = []
    for unit in units:
        clause_data.extend(segment_clauses(
            text=unit.extracted_text,
            page_number=unit.page_number or 1,
        ))

    if not clause_data:
        raise ValueError("No contractual clauses could be identified.")

    existing_clauses = (
        db.query(ContractClause)
        .filter(ContractClause.document_id == document_id)
        .all()
    )
    existing_by_number = {
        clause.clause_number: clause for clause in existing_clauses
    }
    retained_ids = set()
    updated_clauses = []

    for item in clause_data:
        existing = existing_by_number.get(item["clause_number"])
        if existing:
            for key, value in item.items():
                setattr(existing, key, value)
            clause = existing
        else:
            clause = ContractClause(document_id=document_id, **item)
            db.add(clause)

        db.flush()
        retained_ids.add(clause.id)
        updated_clauses.append(clause)

    for clause in existing_clauses:
        if clause.id not in retained_ids:
            db.delete(clause)

    db.flush()
    return updated_clauses


def _replace_evidence(db, document_id, clauses, previous_evidence):
    created_records = []
    retained_ids = set()

    for clause in clauses:
        for item in extract_evidence_from_clause(clause):
            key = _evidence_key(item)
            previous = previous_evidence.get(key)

            if previous:
                record = previous["record"]
                previous_status = previous["verification_status"]
                record.clause_id = clause.id
                for field, value in item.items():
                    if field != "verification_status":
                        setattr(record, field, value)
                record.verification_status = previous_status
            else:
                record = EvidenceRecord(
                    document_id=document_id,
                    clause_id=clause.id,
                    **item,
                )
                db.add(record)

            db.flush()
            retained_ids.add(record.id)
            created_records.append(record)

    for previous in previous_evidence.values():
        record = previous["record"]
        if record.id not in retained_ids:
            db.delete(record)

    db.flush()
    return created_records


def _lock_owned_attempt(db, document_id, attempt_id):
    """
    Lock the document row and verify worker ownership.

    Holding this row lock through the intelligence transaction prevents
    recovery from invalidating the attempt between validation and commit.
    """
    document = (
        db.query(ContractDocument)
        .filter(ContractDocument.id == document_id)
        .with_for_update()
        .first()
    )
    if document is None:
        return None
    if document.processing_attempt_id != attempt_id:
        raise SupersededProcessingAttempt(
            f"Processing attempt for document {document_id} was superseded."
        )
    return document


def process_document_pipeline(document_id, attempt_id=None):
    """
    Execute a document pipeline only while its attempt token is current.

    attempt_id=None is retained for existing internal/test callers. The API
    processing path always supplies a UUID token.
    """
    db = SessionLocal()

    try:
        # Legacy/internal callers without an API token establish a local run.
        if attempt_id is None:
            document = (
                db.query(ContractDocument)
                .filter(ContractDocument.id == document_id)
                .with_for_update()
                .first()
            )
            if document is None:
                logger.error("Document %s not found.", document_id)
                return
            if document.processing_status == "processing":
                # A tokenless worker must never take over a token-owned run.
                if document.processing_attempt_id is not None:
                    return {"status": "superseded"}
            document.processing_status = "processing"
            document.processing_started_at = datetime.now(timezone.utc)
            db.commit()
        else:
            document = (
                db.query(ContractDocument)
                .filter(ContractDocument.id == document_id)
                .first()
            )
            if document is None:
                logger.error("Document %s not found.", document_id)
                return
            if (
                document.processing_status != "processing"
                or document.processing_attempt_id != attempt_id
            ):
                logger.info(
                    "Ignoring superseded processing attempt %s for document %s",
                    attempt_id,
                    document_id,
                )
                return {"status": "superseded"}

        file_path = _backend_root() / document.storage_path
        file_type = document.file_type

        if not file_path.is_file():
            raise FileNotFoundError("Stored document file not found.")

        # Extraction is read-only and can happen before taking the long DB lock.
        extracted_units = extract_document(file_path, file_type)
        extracted_units = [
            unit for unit in extracted_units
            if unit.get("text", "").strip()
        ]

        # Lock + token validation immediately before any intelligence writes.
        document = _lock_owned_attempt(db, document_id, attempt_id)

        if not extracted_units:
            document.processing_status = "needs_ocr"
            document.processing_started_at = None
            document.processing_attempt_id = None
            db.commit()
            logger.info("Document %s requires OCR.", document_id)
            return {"document_id": str(document_id), "status": "needs_ocr"}

        previous_evidence = _get_existing_verifications(db, document_id)
        previous_risk_state, previous_risk_evidence = (
    capture_risk_history_context(
        db,
        document.contract_id,
    )
)

        _replace_text_units(db, document_id, extracted_units)
        clauses = _replace_clauses(db, document_id)
        evidence_records = _replace_evidence(
            db, document_id, clauses, previous_evidence
        )

        risk_result = detect_automatic_renewal_risk(
    db,
    document.contract_id,
    commit=False,
    previous_state=previous_risk_state,
    previous_evidence=previous_risk_evidence,
    source="document_processing",
)

        document.processing_status = "completed"
        document.processing_started_at = None
        document.processing_attempt_id = None
        document.processed_at = datetime.now(timezone.utc)
        db.commit()

        logger.info("Document %s processed successfully.", document_id)
        return {
            "document_id": str(document_id),
            "status": "completed",
            "text_units": len(extracted_units),
            "clauses": len(clauses),
            "evidence_records": len(evidence_records),
            "risk_detection": risk_result,
        }

    except SupersededProcessingAttempt:
        db.rollback()
        logger.info(
            "Stopped superseded processing attempt for document %s",
            document_id,
        )
        return {"document_id": str(document_id), "status": "superseded"}

    except Exception:
        db.rollback()
        logger.exception("Document processing failed for %s.", document_id)

        # Failure is recorded only if this worker still owns the attempt.
        try:
            document = (
                db.query(ContractDocument)
                .filter(ContractDocument.id == document_id)
                .with_for_update()
                .first()
            )
            if (
                document is not None
                and document.processing_attempt_id == attempt_id
            ):
                document.processing_status = "failed"
                document.processing_started_at = None
                document.processing_attempt_id = None
                db.commit()
            else:
                db.rollback()
        except Exception:
            db.rollback()
            logger.exception(
                "Could not record processing failure for %s",
                document_id,
            )
    finally:
        db.close()
