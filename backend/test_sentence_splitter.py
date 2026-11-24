from uuid import UUID

from app.core.database import SessionLocal
from app.models.clause import ContractClause
from app.services.evidence_extractor import split_sentences_with_offsets


DOCUMENT_ID = UUID("2e46963f-938a-464b-98dd-65241d63abbf")

db = SessionLocal()

try:
    clause = (
        db.query(ContractClause)
        .filter(
            ContractClause.document_id == DOCUMENT_ID,
            ContractClause.clause_number == "3"
        )
        .first()
    )

    if not clause:
        print("Clause 3 not found.")
    else:
        results = split_sentences_with_offsets(clause.source_text)

        print(f"\nTotal sentences: {len(results)}\n")

        for index, sentence in enumerate(results, start=1):
            extracted_text = sentence["text"]

            source_match = (
                clause.source_text[
                    sentence["start"]:sentence["end"]
                ] == extracted_text
            )

            print(f"Sentence {index}: {extracted_text}")
            print(f"Start: {sentence['start']}")
            print(f"End: {sentence['end']}")
            print(f"Source match: {source_match}")
            print("-" * 70)

finally:
    db.close()