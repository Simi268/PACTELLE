from pathlib import Path

import fitz
from docx import Document


def extract_pdf(file_path: Path):

    pages = []

    with fitz.open(file_path) as pdf:

        if pdf.is_encrypted:
            raise ValueError("Password-protected PDFs are not supported")

        if pdf.page_count == 0:
            raise ValueError("PDF contains no pages")

        for index, page in enumerate(pdf):

            text = page.get_text("text").strip()

            pages.append({
                "unit_index": index + 1,
                "page_number": index + 1,
                "text": text
            })

    return pages


def extract_docx(file_path: Path):

    document = Document(file_path)

    paragraphs = []

    for paragraph in document.paragraphs:

        text = paragraph.text.strip()

        if text:
            paragraphs.append(text)

    extracted_text = "\n".join(paragraphs)

    if not extracted_text.strip():
        raise ValueError("No extractable text found in DOCX")

    return [{
        "unit_index": 1,
        "page_number": None,
        "text": extracted_text
    }]


def extract_document(file_path: Path, file_type: str):

    extension = file_path.suffix.lower()

    if extension == ".pdf":
        return extract_pdf(file_path)

    if extension == ".docx":
        return extract_docx(file_path)

    raise ValueError("Unsupported document format")