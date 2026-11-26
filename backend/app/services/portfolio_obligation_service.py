from uuid import UUID

from sqlalchemy.orm import joinedload

from app.models.contract import Contract
from app.models.document import ContractDocument
from app.models.evidence_record import EvidenceRecord

from app.services.obligation_normalizer import (
    normalize_evidence_record,
    group_obligations_by_family,
    group_obligations_by_type,
)


def retrieve_organization_obligations(
    db,
    organization_id: UUID,
) -> dict:
    """
    Retrieve current contractual obligations across
    all contracts belonging to an organization.

    Historical evidence is preserved but excluded
    from new portfolio analysis.

    Rejected current evidence is retained separately.
    """

    evidence_records = (
        db.query(EvidenceRecord)

        .join(
            ContractDocument,
            EvidenceRecord.document_id == ContractDocument.id,
        )

        .join(
            Contract,
            ContractDocument.contract_id == Contract.id,
        )

        .filter(
            Contract.organization_id == organization_id,
            EvidenceRecord.is_current.is_(True),
        )

        .options(
            joinedload(
                EvidenceRecord.document
            ).joinedload(
                ContractDocument.contract
            )
        )

        .order_by(
            Contract.title,
            EvidenceRecord.evidence_type,
            EvidenceRecord.created_at,
            EvidenceRecord.id,
        )

        .all()
    )

    eligible_obligations = []
    excluded_obligations = []

    unsupported_evidence_count = 0

    for evidence in evidence_records:

        document = evidence.document
        contract = document.contract

        obligation = normalize_evidence_record(
            evidence=evidence,
            contract_id=contract.id,
            contract_title=contract.title,
        )

        if obligation is None:

            unsupported_evidence_count += 1
            continue

        obligation["analysis_eligible"] = (
            evidence.verification_status != "rejected"
        )

        if evidence.verification_status == "rejected":

            excluded_obligations.append(obligation)

        else:

            eligible_obligations.append(obligation)

    grouped_by_family = group_obligations_by_family(
        eligible_obligations
    )

    grouped_by_type = group_obligations_by_type(
        eligible_obligations
    )

    contract_ids = {
        obligation["contract_id"]
        for obligation in eligible_obligations
    }

    return {
        "organization_id": str(organization_id),

        "summary": {
            "total_evidence_records": len(evidence_records),

            "normalized_obligations": len(
                eligible_obligations
            ),

            "excluded_rejected_evidence": len(
                excluded_obligations
            ),

            "unsupported_evidence": (
                unsupported_evidence_count
            ),

            "contracts_with_obligations": len(
                contract_ids
            ),
        },

        "obligations": eligible_obligations,

        "excluded_obligations": excluded_obligations,

        "grouped_by_family": grouped_by_family,

        "grouped_by_type": grouped_by_type,
    }