import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db

from app.models.document import ContractDocument
from app.models.document_text import DocumentTextUnit
from app.models.clause import ContractClause

from app.services.clause_segmenter import segment_clauses


router = APIRouter(
    prefix="/documents",
    tags=["Clause Intelligence"]
)


@router.post("/{document_id}/segment")
def segment_document_clauses(
    document_id: uuid.UUID,
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

    text_units = db.query(DocumentTextUnit).filter(
        DocumentTextUnit.document_id == document_id
    ).order_by(
        DocumentTextUnit.unit_index
    ).all()

    if not text_units:

        raise HTTPException(
            status_code=400,
            detail="Document has not been extracted"
        )

    all_clauses = []

    for unit in text_units:

        clauses = segment_clauses(
            text=unit.extracted_text,
            page_number=unit.page_number
        )

        all_clauses.extend(clauses)

    if not all_clauses:

        raise HTTPException(
            status_code=422,
            detail="No numbered clauses could be identified"
        )

    try:

        db.query(ContractClause).filter(
            ContractClause.document_id == document_id
        ).delete(synchronize_session=False)

        for clause_data in all_clauses:

            clause = ContractClause(
                document_id=document_id,
                **clause_data
            )

            db.add(clause)

        db.commit()

    except Exception:

        db.rollback()

        raise HTTPException(
            status_code=500,
            detail="Clause segmentation failed"
        )

    return {

        "message": "Clauses identified successfully",

        "document_id": str(document_id),

        "total_clauses": len(all_clauses),

        "clauses": [

            {
                "clause_number": clause["clause_number"],
                "clause_title": clause["clause_title"],
                "category": clause["category"],
                "page_number": clause["page_number"]
            }

            for clause in all_clauses

        ]

    }