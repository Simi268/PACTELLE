import uuid

from fastapi import APIRouter, UploadFile, File, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.contract import Contract
from app.models.document import ContractDocument
from app.services.document_storage import save_document


router = APIRouter(
    prefix="/documents",
    tags=["Documents"]
)


@router.post("/upload/{contract_id}")
async def upload_document(
    contract_id: uuid.UUID,
    file: UploadFile = File(...),
    db: Session = Depends(get_db)
):

    contract = db.query(Contract).filter(
        Contract.id == contract_id
    ).first()

    if not contract:
        raise HTTPException(
            status_code=404,
            detail="Contract not found"
        )

    file_data = await save_document(file)

    document = ContractDocument(
        contract_id=contract_id,
        original_filename=file_data["original_filename"],
        stored_filename=file_data["stored_filename"],
        storage_path=file_data["storage_path"],
        file_type=file_data["file_type"],
        file_size=file_data["file_size"],
        processing_status="uploaded"
    )

    try:
        db.add(document)
        db.commit()
        db.refresh(document)

    except Exception:
        db.rollback()

        from pathlib import Path
        Path(file_data["storage_path"]).unlink(missing_ok=True)

        raise HTTPException(
            status_code=500,
            detail="Document registration failed"
        )

    return {
        "message": "Document uploaded successfully",
        "document_id": str(document.id),
        "filename": document.original_filename,
        "status": document.processing_status
    }