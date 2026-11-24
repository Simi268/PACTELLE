from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.document import ContractDocument
from app.models.clause import ContractClause
from app.models.evidence_record import EvidenceRecord

from app.services.evidence_extractor import (
    extract_evidence_from_clause
)

router = APIRouter(
    prefix="/documents",
    tags=["Evidence Intelligence"]
)


@router.post("/{document_id}/extract-evidence")
def extract_document_evidence(
    document_id: str,
    db: Session = Depends(get_db)
):

    document = db.query(ContractDocument).filter(
        ContractDocument.id == document_id
    ).first()

    if not document:
        raise HTTPException(
            status_code=404,
            detail="Document not found"
        )

    clauses = db.query(ContractClause).filter(
        ContractClause.document_id == document_id
    ).order_by(
        ContractClause.clause_number
    ).all()

    if not clauses:
        raise HTTPException(
            status_code=422,
            detail="No clauses found. Segment the document first."
        )

    try:
        # Make extraction repeatable without duplicate records.
        db.query(EvidenceRecord).filter(
            EvidenceRecord.document_id == document_id
        ).delete(synchronize_session=False)

        all_evidence = []

        for clause in clauses:

            extracted = extract_evidence_from_clause(clause)

            for item in extracted:

                evidence = EvidenceRecord(
                    document_id=document.id,
                    clause_id=clause.id,
                    **item
                )

                db.add(evidence)

                all_evidence.append({
                    "clause_number": clause.clause_number,
                    "claim": item["claim"],
                    "evidence_type": item["evidence_type"],
                    "page_number": item["page_number"],
                })

        db.commit()

        return {
            "document_id": str(document.id),
            "status": "completed",
            "clauses_processed": len(clauses),
            "evidence_records_created": len(all_evidence),
            "evidence": all_evidence
        }

    except Exception:
        db.rollback()
        raise