import re

from typing import Any


OBLIGATION_DEFINITIONS = {
    "renewal_period": {
        "family": "renewal",
        "description": "Contract renewal duration",
    },
    "renewal_notice": {
        "family": "renewal",
        "description": "Advance notice required for non-renewal",
    },
    "payment_deadline": {
        "family": "payment",
        "description": "Payment deadline",
    },
    "fee_increase_notice": {
        "family": "payment",
        "description": "Notice required before fee increases",
    },
    "breach_cure_period": {
        "family": "termination",
        "description": "Time allowed to cure a material breach",
    },
    "termination_notice": {
        "family": "termination",
        "description": "Notice required for termination",
    },
    "liability_cap": {
        "family": "liability",
        "description": "Liability limitation period",
    },
    "damages_exclusion": {
        "family": "liability",
        "description": "Exclusion of specified damages",
    },
    "data_security_safeguards": {
        "family": "data_protection",
        "description": "Data security obligations",
    },
    "security_incident_notification": {
        "family": "data_protection",
        "description": "Security incident notification",
    },
    "confidentiality_obligation": {
        "family": "confidentiality",
        "description": "Confidential information protection",
    },
    "confidential_information_use": {
        "family": "confidentiality",
        "description": "Permitted use of confidential information",
    },
    "subprocessor_change_notice": {
        "family": "subprocessors",
        "description": "Subprocessor change notification",
    },
    "intellectual_property_indemnity": {
        "family": "indemnification",
        "description": "Intellectual property indemnification",
    },
}


DURATION_PATTERN = re.compile(
    r"\b(\d+)\s*[- ]?"
    r"(days?|weeks?|months?|years?)\b",
    re.IGNORECASE,
)


def normalize_unit(unit: str) -> str:
    """
    Normalize duration units without converting
    calendar months or years into fixed day counts.
    """

    unit = unit.lower().strip()

    if unit.startswith("day"):
        return "days"

    if unit.startswith("week"):
        return "weeks"

    if unit.startswith("month"):
        return "months"

    if unit.startswith("year"):
        return "years"

    return unit


def extract_duration(text: str) -> dict[str, Any] | None:
    """
    Extract a numeric duration from a structured claim.

    Examples:
        90 days
        3 months
        12 weeks
    """

    if not text:
        return None

    match = DURATION_PATTERN.search(text)

    if not match:
        return None

    return {
        "value": int(match.group(1)),
        "unit": normalize_unit(match.group(2)),
    }


def get_obligation_definition(
    evidence_type: str,
) -> dict[str, str] | None:

    return OBLIGATION_DEFINITIONS.get(evidence_type)


def normalize_evidence_record(
    evidence,
    contract_id=None,
    contract_title=None,
) -> dict[str, Any] | None:
    """
    Convert an EvidenceRecord into a normalized
    cross-contract obligation representation.

    Original evidence and provenance are preserved.
    """

    definition = get_obligation_definition(
        evidence.evidence_type
    )

    if definition is None:
        return None

    duration = extract_duration(
        evidence.claim
    )

    return {
        "evidence_id": str(evidence.id),

        "contract_id": (
            str(contract_id)
            if contract_id is not None
            else None
        ),

        "contract_title": contract_title,

        "obligation_type": evidence.evidence_type,

        "obligation_family": definition["family"],

        "description": definition["description"],

        "claim": evidence.claim,

        "original_text": evidence.evidence_text,

        "duration": duration,

        "verification_status": evidence.verification_status,

        "confidence": evidence.confidence,

        "extraction_method": evidence.extraction_method,

        "provenance": {
            "document_id": str(evidence.document_id),
            "clause_id": str(evidence.clause_id),
            "page_number": evidence.page_number,
            "char_start": evidence.char_start,
            "char_end": evidence.char_end,
        },
    }


def normalize_evidence_records(
    evidence_records: list,
    contract_id=None,
    contract_title=None,
) -> list[dict[str, Any]]:
    """
    Normalize multiple evidence records.

    Unsupported evidence types are skipped.
    """

    normalized = []

    for evidence in evidence_records:

        obligation = normalize_evidence_record(
            evidence=evidence,
            contract_id=contract_id,
            contract_title=contract_title,
        )

        if obligation is not None:
            normalized.append(obligation)

    return normalized


def group_obligations_by_family(
    obligations: list[dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    """
    Group normalized obligations by business category.
    """

    grouped = {}

    for obligation in obligations:

        family = obligation["obligation_family"]

        grouped.setdefault(family, []).append(
            obligation
        )

    return grouped


def group_obligations_by_type(
    obligations: list[dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    """
    Group obligations by their specific obligation type.
    """

    grouped = {}

    for obligation in obligations:

        obligation_type = obligation["obligation_type"]

        grouped.setdefault(obligation_type, []).append(
            obligation
        )

    return grouped