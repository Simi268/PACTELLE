from pathlib import Path
import logging

from sqlalchemy.orm import Session

from app.core.database import SessionLocal

from app.models.document import ContractDocument
from app.models.document_text import DocumentTextUnit
from app.models.clause import ContractClause
from app.models.evidence_record import EvidenceRecord

from app.services.document_parser import extract_document
from app.services.clause_segmenter import segment_clauses
from app.services.evidence_extractor import extract_evidence_from_clause
from app.services.risk_engine import detect_automatic_renewal_risk


logger = logging.getLogger(__name__)


def _backend_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _evidence_key(item):
    fields = (
        "evidence_type",
        "claim",
        "evidence_text",
        "page_number",
        "char_start",
        "char_end",
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

        db.add(
            DocumentTextUnit(
                document_id=document_id,
                unit_index=unit["unit_index"],
                page_number=unit.get("page_number"),
                extracted_text=text,
                character_count=len(text),
            )
        )

    db.flush()


def _replace_clauses(db, document_id):
    units = (
        db.query(DocumentTextUnit)
        .filter(
            DocumentTextUnit.document_id == document_id
        )
        .order_by(DocumentTextUnit.unit_index.asc())
        .all()
    )

    clause_data = []

    for unit in units:
        results = segment_clauses(
            text=unit.extracted_text,
            page_number=unit.page_number or 1,
        )

        clause_data.extend(results)

    if not clause_data:
        raise ValueError(
            "No contractual clauses could be identified."
        )

    existing_clauses = (
        db.query(ContractClause)
        .filter(
            ContractClause.document_id == document_id
        )
        .all()
    )

    existing_by_number = {
        clause.clause_number: clause
        for clause in existing_clauses
    }

    retained_ids = set()
    updated_clauses = []

    for item in clause_data:
        clause_number = item["clause_number"]

        existing = existing_by_number.get(clause_number)

        if existing:
            for key, value in item.items():
                setattr(existing, key, value)

            clause = existing
        else:
            clause = ContractClause(
                document_id=document_id,
                **item,
            )
            db.add(clause)

        db.flush()

        retained_ids.add(clause.id)
        updated_clauses.append(clause)

    # Delete only clauses no longer present.
    stale_clauses = [
        clause
        for clause in existing_clauses
        if clause.id not in retained_ids
    ]

    for clause in stale_clauses:
        db.delete(clause)

    db.flush()

    return updated_clauses


def _replace_evidence(
    db,
    document_id,
    clauses,
    previous_evidence,
):
    created_records = []
    retained_ids = set()

    for clause in clauses:
        extracted_items = extract_evidence_from_clause(clause)

        for item in extracted_items:
            key = _evidence_key({
                "evidence_type": item["evidence_type"],
                "claim": item["claim"],
                "evidence_text": item["evidence_text"],
                "page_number": item.get("page_number"),
                "char_start": item.get("char_start"),
                "char_end": item.get("char_end"),
            })

            previous = previous_evidence.get(key)

            if previous:
                record = previous["record"]

                previous_status = previous["verification_status"]

                record.clause_id = clause.id

                for field, value in item.items():
                    if field == "verification_status":
                        continue

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

    # Remove only evidence no longer extracted from the document.
    for previous in previous_evidence.values():
        record = previous["record"]

        if record.id not in retained_ids:
            db.delete(record)

    db.flush()

    return created_records


def process_document_pipeline(document_id):
    """
    Runs the full document intelligence pipeline.

    Uses its own session because it executes independently
    of the original HTTP request.
    """

    db = SessionLocal()

    try:
        document = (
            db.query(ContractDocument)
            .filter(
                ContractDocument.id == document_id
            )
            .first()
        )

        if document is None:
            logger.error(
                "Document %s not found.",
                document_id,
            )
            return

        document.processing_status = "processing"
        db.commit()

        file_path = _backend_root() / document.storage_path

        if not file_path.is_file():
            raise FileNotFoundError(
                "Stored document file not found."
            )

        previous_evidence = _get_existing_verifications(
            db,
            document_id,
        )

        # STEP 1: Extract text.
        extracted_units = extract_document(
            file_path,
            document.file_type,
        )

        extracted_units = [
            unit
            for unit in extracted_units
            if unit.get("text", "").strip()
        ]

        if not extracted_units:
            document.processing_status = "needs_ocr"
            db.commit()

            logger.info(
                "Document %s requires OCR.",
                document_id,
            )
            return

        _replace_text_units(
            db,
            document_id,
            extracted_units,
        )

        db.commit()

        # STEP 2: Update clauses.
        clauses = _replace_clauses(
            db,
            document_id,
        )

        db.commit()

        # STEP 3: Update evidence.
        evidence_records = _replace_evidence(
            db,
            document_id,
            clauses,
            previous_evidence,
        )

        db.commit()

        # STEP 4: Reconcile renewal risk.
        contract_id = document.contract_id

        risk_result = detect_automatic_renewal_risk(
            db,
            contract_id,
        )

        # STEP 5: Mark completed.
        document = (
            db.query(ContractDocument)
            .filter(
                ContractDocument.id == document_id
            )
            .first()
        )

        document.processing_status = "completed"
        db.commit()

        logger.info(
            "Document %s processed successfully.",
            document_id,
        )

        return {
            "document_id": str(document_id),
            "status": "completed",
            "text_units": len(extracted_units),
            "clauses": len(clauses),
            "evidence_records": len(evidence_records),
            "risk_detection": risk_result,
        }

    except Exception:
        db.rollback()

        logger.exception(
            "Document processing failed for %s.",
            document_id,
        )

        document = (
            db.query(ContractDocument)
            .filter(
                ContractDocument.id == document_id
            )
            .first()
        )

        if document is not None:
            document.processing_status = "failed"
            db.commit()

    finally:
        db.close()