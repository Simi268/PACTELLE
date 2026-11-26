from itertools import combinations
from typing import Any


def _duration_key(duration: dict | None):
    """
    Return a comparable duration representation.

    Months and days remain distinct because calendar
    months cannot safely be converted into fixed days.
    """

    if not duration:
        return None

    value = duration.get("value")
    unit = duration.get("unit")

    if not isinstance(value, int) or value <= 0:
        return None

    if unit not in {"days", "weeks", "months", "years"}:
        return None

    return value, unit


def _build_evidence_reference(
    obligation: dict[str, Any],
) -> dict[str, Any]:

    return {
        "evidence_id": obligation.get("evidence_id"),
        "contract_id": obligation.get("contract_id"),
        "contract_title": obligation.get("contract_title"),
        "obligation_type": obligation.get("obligation_type"),
        "claim": obligation.get("claim"),
        "original_text": obligation.get("original_text"),
        "duration": obligation.get("duration"),
        "verification_status": obligation.get(
            "verification_status"
        ),
        "provenance": obligation.get("provenance"),
    }


def _build_comparison(
    first: dict[str, Any],
    second: dict[str, Any],
) -> dict[str, Any] | None:

    if first.get("contract_id") == second.get("contract_id"):
        return None

    first_type = first.get("obligation_type")
    second_type = second.get("obligation_type")

    if not first_type or first_type != second_type:
        return None

    first_duration = _duration_key(first.get("duration"))
    second_duration = _duration_key(second.get("duration"))

    if first_duration is None or second_duration is None:
        comparison_type = "insufficient_data"
        explanation = (
            "The obligations are comparable by type, "
            "but their durations cannot be reliably compared."
        )

    elif first_duration == second_duration:
        comparison_type = "similar"
        explanation = (
            "Both contracts contain the same obligation type "
            "and normalized duration."
        )

    else:
        comparison_type = "term_variance"
        explanation = (
            "Both contracts contain the same obligation type, "
            "but their normalized durations differ. "
            "This is a contractual variation, not proof of conflict."
        )

    verification_statuses = {
        first.get("verification_status"),
        second.get("verification_status"),
    }

    provisional = (
        "unverified" in verification_statuses
        or "rejected" in verification_statuses
    )

    return {
        "comparison_type": comparison_type,

        "obligation_type": first_type,

        "obligation_family": first.get("obligation_family"),

        "assessment_status": (
            "provisional" if provisional else "confirmed"
        ),

        "explanation": explanation,

        "duration_comparison": {
            "first": first.get("duration"),
            "second": second.get("duration"),
            "matches": (
                first_duration == second_duration
                if first_duration is not None
                and second_duration is not None
                else None
            ),
        },

        "requires_review": (
            comparison_type != "similar" or provisional
        ),

        "evidence": [
            _build_evidence_reference(first),
            _build_evidence_reference(second),
        ],
    }


def compare_obligation_pair(
    first: dict[str, Any],
    second: dict[str, Any],
) -> dict[str, Any] | None:
    """
    Public interface for comparing two obligations.
    """

    if (
        first.get("analysis_eligible") is False
        or second.get("analysis_eligible") is False
    ):
        return None

    return _build_comparison(first, second)


def compare_cross_contract_obligations(
    obligations: list[dict[str, Any]],
) -> dict[str, Any]:
    """
    Compare normalized obligations across contracts.

    Only obligations with matching types are compared.

    Rejected evidence is excluded.

    Results distinguish:
        similar
        term_variance
        insufficient_data

    No result is automatically classified as a
    confirmed contractual conflict.
    """

    grouped = {}

    skipped_rejected = 0
    skipped_invalid = 0

    for obligation in obligations:

        if obligation.get("analysis_eligible") is False:
            skipped_rejected += 1
            continue

        if not obligation.get("contract_id"):
            skipped_invalid += 1
            continue

        obligation_type = obligation.get("obligation_type")

        if not obligation_type:
            skipped_invalid += 1
            continue

        grouped.setdefault(obligation_type, []).append(
            obligation
        )

    comparisons = []

    for obligation_type in sorted(grouped):

        records = grouped[obligation_type]

        for first, second in combinations(records, 2):

            comparison = compare_obligation_pair(
                first,
                second,
            )

            if comparison is not None:
                comparisons.append(comparison)

    counts = {
        "similar": 0,
        "term_variance": 0,
        "insufficient_data": 0,
    }

    for comparison in comparisons:
        counts[comparison["comparison_type"]] += 1

    return {
        "summary": {
            "total_obligations": len(obligations),
            "total_comparisons": len(comparisons),
            "similar": counts["similar"],
            "term_variance": counts["term_variance"],
            "insufficient_data": counts["insufficient_data"],
            "skipped_rejected": skipped_rejected,
            "skipped_invalid": skipped_invalid,
        },

        "comparisons": comparisons,
    }