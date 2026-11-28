"""Evidence Verification Agent for PACTELLE.

Validates evidence provenance against persisted source documents.
Read-only: never modifies evidence or establishes legal conclusions.
"""

import logging
from typing import Callable, Optional
from uuid import UUID

from sqlalchemy.orm import joinedload

from app.agents.contracts import (
    AgentError,
    AgentName,
    AgentResult,
    AgentStatus,
    EvidenceReference,
)
from app.agents.state import AgentState
from app.core.database import SessionLocal
from app.models.contract import Contract
from app.models.document import ContractDocument
from app.models.evidence_record import EvidenceRecord

logger = logging.getLogger(__name__)


class VerificationAgent:
    agent_name = AgentName.VERIFICATION

    def __init__(
        self,
        session_factory: Optional[Callable] = None,
    ):
        self.session_factory = session_factory

    def __call__(self, state: AgentState) -> AgentResult:
        db = None

        try:
            obligation_result = state.results.get("obligation")

            if obligation_result is None:
                return self._failure(
                    "MISSING_OBLIGATION_RESULT",
                    "Verification requires a completed Obligation Agent result.",
                )

            if obligation_result.status != AgentStatus.COMPLETED:
                return self._failure(
                    "INVALID_OBLIGATION_RESULT",
                    "The Obligation Agent did not complete successfully.",
                )

            obligations = obligation_result.data.get("obligations", [])
            excluded = obligation_result.data.get(
                "excluded_obligations", []
            )

            if not isinstance(obligations, list) or not isinstance(excluded, list):
                return self._failure(
                    "INVALID_OBLIGATION_COLLECTION",
                    "The obligation collections have an invalid structure.",
                )

            evidence_ids = []

            for item in obligations + excluded:
                if not isinstance(item, dict):
                    continue

                evidence_id = item.get("evidence_id")

                if evidence_id:
                    evidence_ids.append(str(evidence_id))

            evidence_ids = list(dict.fromkeys(evidence_ids))

            if not evidence_ids:
                return AgentResult(
                    agent=self.agent_name,
                    status=AgentStatus.COMPLETED,
                    summary="No evidence records were available for verification.",
                    data={
                        "total": 0,
                        "verified": 0,
                        "unverified": 0,
                        "review_required": 0,
                        "results": [],
                    },
                    unresolved_questions=[
                        "No evidence identifiers were supplied for verification."
                    ],
                    human_review_required=True,
                )

            parsed_ids = []

            for evidence_id in evidence_ids:
                try:
                    parsed_ids.append(UUID(evidence_id))
                except (ValueError, TypeError):
                    return self._failure(
                        "INVALID_EVIDENCE_ID",
                        "An evidence identifier is not a valid UUID.",
                    )

            session_factory = self.session_factory or SessionLocal
            db = session_factory()

            records = (
                db.query(EvidenceRecord)
                .join(
                    ContractDocument,
                    EvidenceRecord.document_id == ContractDocument.id,
                )
                .join(
                    Contract,
                    ContractDocument.contract_id == Contract.id,
                )
                .options(
                    joinedload(EvidenceRecord.document),
                    joinedload(EvidenceRecord.clause),
                )
                .filter(
                    EvidenceRecord.id.in_(parsed_ids),
                    Contract.organization_id == state.organization_id,
                )
                .all()
            )

            records_by_id = {
                str(record.id): record
                for record in records
            }

            results = []
            references = []
            unresolved = []

            for evidence_id in evidence_ids:
                record = records_by_id.get(evidence_id)

                if record is None:
                    results.append({
                        "evidence_id": evidence_id,
                        "outcome": "review_required",
                        "checks": {},
                        "issues": [
                            "Evidence record was not found within the requested organization."
                        ],
                    })

                    unresolved.append(
                        f"Evidence {evidence_id} could not be located or accessed."
                    )
                    continue

                result = self._verify_record(record)

                results.append(result)

                references.append(
                    EvidenceReference(
                        evidence_id=str(record.id),
                        document_id=str(record.document_id),
                        contract_id=str(record.document.contract_id),
                        clause_id=str(record.clause_id),
                        page_number=record.page_number,
                        char_start=record.char_start,
                        char_end=record.char_end,
                        excerpt=record.evidence_text,
                        verification_status=record.verification_status,
                    )
                )

                if result["outcome"] != "verified":
                    unresolved.extend(
                        f"Evidence {evidence_id}: {issue}"
                        for issue in result["issues"]
                    )

            counts = {
                "verified": 0,
                "unverified": 0,
                "review_required": 0,
            }

            for result in results:
                counts[result["outcome"]] += 1

            unresolved = list(dict.fromkeys(unresolved))

            return AgentResult(
                agent=self.agent_name,
                status=AgentStatus.COMPLETED,
                summary=(
                    f"Checked {len(results)} evidence records: "
                    f"{counts['verified']} verified, "
                    f"{counts['unverified']} unverified, "
                    f"{counts['review_required']} requiring review."
                ),
                data={
                    "total": len(results),
                    **counts,
                    "results": results,
                    "legal_conclusions_established": False,
                    "semantic_claim_verification_performed": False,
                },
                evidence_references=references,
                unresolved_questions=unresolved,
                human_review_required=(
                    counts["unverified"] > 0
                    or counts["review_required"] > 0
                ),
            )

        except Exception:
            logger.exception(
                "Verification Agent failed for organization %s",
                state.organization_id,
            )

            return self._failure(
                "EVIDENCE_VERIFICATION_FAILED",
                "Evidence verification failed. No successful verification is assumed.",
            )

        finally:
            if db is not None:
                db.close()

    @staticmethod
    def _verify_record(record: EvidenceRecord) -> dict:
        issues = []

        document = record.document
        clause = record.clause

        checks = {
            "document_exists": document is not None,
            "clause_exists": clause is not None,
            "document_matches": False,
            "page_matches": False,
            "offsets_valid": False,
            "source_text_matches": False,
        }

        if document is None:
            issues.append("Referenced document is missing.")

        if clause is None:
            issues.append("Referenced clause is missing.")

        if document is not None and clause is not None:
            checks["document_matches"] = (
                record.document_id == clause.document_id
                and clause.document_id == document.id
            )

            if not checks["document_matches"]:
                issues.append(
                    "Evidence, document and clause references do not match."
                )

            checks["page_matches"] = (
                record.page_number is not None
                and record.page_number == clause.page_number
            )

            if not checks["page_matches"]:
                issues.append(
                    "Evidence page number is missing or differs from the clause."
                )

            offsets_present = (
                record.char_start is not None
                and record.char_end is not None
                and clause.char_start is not None
                and clause.char_end is not None
            )

            if offsets_present:
                checks["offsets_valid"] = (
                    record.char_start >= clause.char_start
                    and record.char_end <= clause.char_end
                    and record.char_end >= record.char_start
                    and record.char_end - record.char_start
                    == len(record.evidence_text or "")
                )

            if not checks["offsets_valid"]:
                issues.append(
                    "Evidence character offsets are missing or outside clause boundaries."
                )

            if checks["offsets_valid"] and checks["document_matches"]:
                relative_start = (
                    record.char_start - clause.char_start
                )

                relative_end = (
                    record.char_end - clause.char_start
                )

                source_excerpt = clause.source_text[
                    relative_start:relative_end
                ]

                checks["source_text_matches"] = (
                    source_excerpt == record.evidence_text
                )

            if not checks["source_text_matches"]:
                issues.append(
                    "Evidence text does not exactly match its referenced source passage."
                )

        status = record.verification_status

        if status == "rejected":
            issues.append(
                "Evidence has been rejected and cannot be automatically accepted."
            )

        if status not in {"verified", "unverified", "rejected"}:
            issues.append("Evidence has an unsupported verification status.")

        provenance_valid = all([
            checks["document_exists"],
            checks["clause_exists"],
            checks["document_matches"],
            checks["page_matches"],
            checks["offsets_valid"],
            checks["source_text_matches"],
        ])

        if not provenance_valid or status == "rejected":
            outcome = "review_required"

        elif status == "unverified":
            outcome = "unverified"

            issues.append(
                "Source provenance matches, but evidence has not been independently approved."
            )

        elif status == "verified":
            outcome = "verified"

        else:
            outcome = "review_required"

        return {
            "evidence_id": str(record.id),
            "outcome": outcome,
            "stored_verification_status": status,
            "checks": checks,
            "issues": issues,
        }

    def _failure(self, code: str, message: str) -> AgentResult:
        return AgentResult(
            agent=self.agent_name,
            status=AgentStatus.FAILED,
            summary="Evidence verification did not complete successfully.",
            error=AgentError(
                agent=self.agent_name,
                code=code,
                message=message,
                retryable=False,
            ),
        )