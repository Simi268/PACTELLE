import re
from typing import Any


PARTY_PATTERN = (
    r"(?:customer|client|vendor|supplier|provider|"
    r"processor|controller|company|contractor|"
    r"service provider)"
)

TRIGGER_PATTERNS = {
    "subprocessor_change": (
        "subprocessor",
        "sub-processor",
        "sub processor",
    ),
    "security_incident": (
        "security incident",
        "data breach",
        "personal data breach",
        "unauthorized access",
    ),
    "contract_renewal": (
        "renewal",
        "automatic renewal",
        "non-renewal",
    ),
    "payment_event": (
        "payment",
        "invoice",
        "billing",
        "amount due",
    ),
    "contract_termination": (
        "termination",
        "terminate",
        "expiration",
    ),
    "confidentiality_event": (
        "confidential information",
        "confidentiality",
        "disclosure of information",
    ),
    "data_processing_change": (
        "processing of personal data",
        "data processing",
        "personal data processing",
    ),
}


def _extract_text(obligation: dict[str, Any]) -> str:
    return " ".join(
        str(obligation.get(field) or "")
        for field in ("claim", "original_text")
    ).strip()


def extract_trigger(text: str) -> dict[str, Any]:
    normalized = text.lower()

    matches = []

    for trigger, keywords in TRIGGER_PATTERNS.items():
        if any(keyword in normalized for keyword in keywords):
            matches.append(trigger)

    if len(matches) == 1:
        return {
            "trigger_type": matches[0],
            "trigger_confidence": "rule_based",
        }

    if len(matches) > 1:
        return {
            "trigger_type": "multiple_or_ambiguous",
            "trigger_candidates": matches,
            "trigger_confidence": "ambiguous",
        }

    return {
        "trigger_type": "unspecified",
        "trigger_confidence": "unknown",
    }


def extract_responsible_party(text: str) -> dict[str, Any]:
    normalized = text.lower()

    pattern = (
        rf"\b({PARTY_PATTERN})\b"
        r"\s+(?:shall|must|will|is required to|agrees to)\b"
    )

    matches = re.findall(pattern, normalized)

    unique_parties = list(dict.fromkeys(matches))

    if len(unique_parties) == 1:
        return {
            "responsible_party": unique_parties[0],
            "party_confidence": "rule_based",
        }

    if len(unique_parties) > 1:
        return {
            "responsible_party": None,
            "party_candidates": unique_parties,
            "party_confidence": "ambiguous",
        }

    return {
        "responsible_party": None,
        "party_confidence": "unknown",
    }


def extract_recipient(
    text: str,
    responsible_party: str | None,
) -> dict[str, Any]:
    normalized = text.lower()

    pattern = (
        rf"\bnotify\s+(?:the\s+)?({PARTY_PATTERN})\b"
    )

    matches = re.findall(pattern, normalized)

    recipients = list(dict.fromkeys(matches))

    if len(recipients) == 1:
        return {
            "recipient_party": recipients[0],
            "direction": (
                f"{responsible_party}_to_{recipients[0]}"
                if responsible_party
                else "recipient_identified"
            ),
        }

    if len(recipients) > 1:
        return {
            "recipient_party": None,
            "recipient_candidates": recipients,
            "direction": "ambiguous",
        }

    return {
        "recipient_party": None,
        "direction": "unspecified",
    }


def analyze_obligation_context(
    obligation: dict[str, Any],
) -> dict[str, Any]:
    """
    Extract contextual information from a normalized obligation.

    This is heuristic analysis, not legal interpretation.
    """

    text = _extract_text(obligation)

    trigger = extract_trigger(text)

    party = extract_responsible_party(text)

    recipient = extract_recipient(
        text,
        party.get("responsible_party"),
    )

    return {
        "evidence_id": obligation.get("evidence_id"),
        "contract_id": obligation.get("contract_id"),
        "obligation_type": obligation.get("obligation_type"),
        "trigger": trigger,
        "responsibility": party,
        "recipient": recipient,
        "context_confidence": (
            "rule_based"
            if (
                trigger["trigger_confidence"] == "rule_based"
                and party["party_confidence"] == "rule_based"
            )
            else "partial_or_ambiguous"
        ),
    }


def compare_obligation_contexts(
    first: dict[str, Any],
    second: dict[str, Any],
) -> dict[str, Any]:
    """
    Compare trigger and responsibility context.

    Different responsible parties are not automatically conflicts.
    They may represent complementary contractual responsibilities.
    """

    first_trigger = first["trigger"]["trigger_type"]
    second_trigger = second["trigger"]["trigger_type"]

    first_party = first["responsibility"].get(
        "responsible_party"
    )
    second_party = second["responsibility"].get(
        "responsible_party"
    )

    first_direction = first["recipient"].get("direction")
    second_direction = second["recipient"].get("direction")

    if (
        first_trigger == "unspecified"
        or second_trigger == "unspecified"
        or first_trigger == "multiple_or_ambiguous"
        or second_trigger == "multiple_or_ambiguous"
    ):
        trigger_relationship = "insufficient_context"

    elif first_trigger == second_trigger:
        trigger_relationship = "shared_trigger"

    else:
        trigger_relationship = "different_triggers"

    if not first_party or not second_party:
        responsibility_relationship = "insufficient_context"

    elif first_party == second_party:
        responsibility_relationship = "same_responsible_party"

    else:
        responsibility_relationship = "different_responsible_parties"

    if (
        first_direction == "unspecified"
        or second_direction == "unspecified"
        or first_direction == "ambiguous"
        or second_direction == "ambiguous"
    ):
        direction_relationship = "insufficient_context"

    elif first_direction == second_direction:
        direction_relationship = "same_direction"

    else:
        direction_relationship = "different_directions"

    return {
        "trigger_relationship": trigger_relationship,
        "responsibility_relationship": responsibility_relationship,
        "direction_relationship": direction_relationship,
        "requires_review": (
            trigger_relationship != "shared_trigger"
            or responsibility_relationship
            == "insufficient_context"
            or direction_relationship == "insufficient_context"
        ),
        "legal_conflict_established": False,
    }


def analyze_cross_contract_contexts(
    obligations: list[dict[str, Any]],
) -> dict[str, Any]:
    """
    Analyze contextual relationships between obligations.

    Only obligations from different contracts are compared.
    """

    analyzed = [
        analyze_obligation_context(obligation)
        for obligation in obligations
        if obligation.get("analysis_eligible") is not False
        and obligation.get("contract_id")
    ]

    comparisons = []

    for index, first in enumerate(analyzed):
        for second in analyzed[index + 1:]:
            if first["contract_id"] == second["contract_id"]:
                continue

            comparisons.append({
                "first_evidence_id": first["evidence_id"],
                "second_evidence_id": second["evidence_id"],
                "context_comparison": compare_obligation_contexts(
                    first,
                    second,
                ),
            })

    return {
        "summary": {
            "analyzed_obligations": len(analyzed),
            "context_comparisons": len(comparisons),
        },
        "obligations": analyzed,
        "comparisons": comparisons,
    }
