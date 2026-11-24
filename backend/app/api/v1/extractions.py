from pathlib import Path
import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import get_authorized_document

from app.models.document import ContractDocument
from app.models.document_text import DocumentTextUnit

from app.services.document_parser import extract_document


router = APIRouter(
    prefix="/documents",
    tags=["Document Extraction"]
)


@router.post("/{document_id}/extract")
def extract_uploaded_document(
    document: ContractDocument = Depends(get_authorized_document),
    db: Session = Depends(get_db)
):

    document_id = document.id

    backend_root = Path(__file__).resolve().parents[3]
    file_path = backend_root / document.storage_path

    if not file_path.is_file():
        raise HTTPException(
            status_code=404,
            detail="Stored document file not found"
        )

    document.processing_status = "processing"
    db.commit()

    try:

        extracted_units = extract_document(
            file_path,
            document.file_type
        )

        nonempty_units = [
            unit for unit in extracted_units
            if unit["text"].strip()
        ]

        if not nonempty_units:

            document.processing_status = "needs_ocr"
            db.commit()

            return {
                "message": "No selectable text found. OCR is required.",
                "status": "needs_ocr"
            }

        db.query(DocumentTextUnit).filter(
            DocumentTextUnit.document_id == document_id
        ).delete(synchronize_session=False)

        for unit in nonempty_units:

            text = unit["text"]

            record = DocumentTextUnit(
                document_id=document_id,
                unit_index=unit["unit_index"],
                page_number=unit["page_number"],
                extracted_text=text,
                character_count=len(text)
            )

            db.add(record)

        document.processing_status = "extracted"

        db.commit()

        return {
            "message": "Document text extracted successfully",
            "document_id": str(document_id),
            "status": "extracted",
            "units_extracted": len(nonempty_units),
            "total_characters": sum(
                len(unit["text"]) for unit in nonempty_units
            )
        }

    except Exception:

        db.rollback()

        document = db.query(ContractDocument).filter(
            ContractDocument.id == document_id
        ).first()

        if document:
            document.processing_status = "failed"
            db.commit()

        raise HTTPException(
            status_code=500,
            detail="Document extraction failed"
        )


@router.get("/{document_id}/text")
def get_extracted_text(
    document: ContractDocument = Depends(get_authorized_document),
    db: Session = Depends(get_db)
):

    document_id = document.id

    units = db.query(DocumentTextUnit).filter(
        DocumentTextUnit.document_id == document_id
    ).order_by(
        DocumentTextUnit.unit_index
    ).all()

    return {
        "document_id": str(document_id),
        "filename": document.original_filename,
        "status": document.processing_status,
        "total_units": len(units),
        "extracted_content": [
            {
                "unit_index": unit.unit_index,
                "page_number": unit.page_number,
                "character_count": unit.character_count,
                "text": unit.extracted_text
            }
            for unit in units
        ]
    }