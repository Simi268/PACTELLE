import uuid
from pathlib import Path

from fastapi import UploadFile, HTTPException

UPLOAD_DIR = Path("uploads/contracts")

MAX_FILE_SIZE = 10 * 1024 * 1024

ALLOWED_TYPES = {
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
}


async def save_document(file: UploadFile):

    extension = Path(file.filename or "").suffix.lower()

    if extension not in ALLOWED_TYPES:
        raise HTTPException(
            status_code=400,
            detail="Only PDF and DOCX files are supported"
        )

    content = await file.read(MAX_FILE_SIZE + 1)

    if not content:
        raise HTTPException(
            status_code=400,
            detail="Empty files are not allowed"
        )

    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=413,
            detail="File exceeds 10 MB limit"
        )

    if extension == ".pdf" and not content.startswith(b"%PDF-"):
        raise HTTPException(
            status_code=400,
            detail="Invalid PDF file"
        )

    if extension == ".docx" and not content.startswith(b"PK"):
        raise HTTPException(
            status_code=400,
            detail="Invalid DOCX file"
        )

    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

    stored_filename = f"{uuid.uuid4()}{extension}"

    file_path = UPLOAD_DIR / stored_filename

    file_path.write_bytes(content)

    return {
        "original_filename": Path(file.filename).name,
        "stored_filename": stored_filename,
        "storage_path": str(file_path),
        "file_type": ALLOWED_TYPES[extension],
        "file_size": len(content)
    }