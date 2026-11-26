from typing import Any

from app.services.cross_contract_comparator import (
    compare_cross_contract_obligations,
)

from app.services.obligation_context_analyzer import (
    analyze_cross_contract_contexts,
)


def _pair_key(first_id, second_id):
    """
    Generate a stable key for an unordered evidence pair.
    """
    return tuple(sorted((str(first_id), str(second_id))))


def _classify_comparison(
    comparison: dict[str, Any],
    context: dict[str, Any] | None,
) -> dict[str, Any]:
    """
    Classify a comparison without treating contractual
    differences as automatically established conflicts.
    """

    comparison_type = comparison["comparison_type"]

    if comparison_type == "similar":
        classification = "similar_obligation"
        explanation = (
            "The obligations have matching types and durations. "
            "This indicates similarity, not necessarily identical "
            "legal effect."
        )

    elif comparison_type == "insufficient_data":
        classification = "insufficient_evidence"
        explanation = (
            "The obligations could not be reliably compared "
            "because duration information is incomplete."
        )

    else:
        classification = "contractual_variation"
        explanation = (
            "The obligations contain different normalized terms. "
            "This represents a contractual variation, not proof "
            "of a legal conflict."
        )

    operational_dependency_candidate = False

    if context:
        trigger_relationship = context.get(
            "trigger_relationship"
        )

        responsibility_relationship = context.get(
            "responsibility_relationship"
        )

        if (
            trigger_relationship == "shared_trigger"
            and responsibility_relationship
            == "different_responsible_parties"
        ):
            operational_dependency_candidate = True

            classification = "potential_operational_dependency"

            explanation = (
                "The obligations have different terms, share "
                "a detected trigger, and assign responsibility "
                "to different parties. This may represent an "
                "operational dependency requiring human review. "
                "It is not an established contractual conflict."
            )

    return {
        "classification": classification,
        "explanation": explanation,
        "operational_dependency_candidate": (
            operational_dependency_candidate
        ),
        "legal_conflict_established": False,
        "requires_human_review": (
            comparison_type != "similar"
            or operational_dependency_candidate
            or comparison["assessment_status"] == "provisional"
        ),
    }


def _index_context_comparisons(
    context_result: dict[str, Any],
) -> dict[tuple[str, str], dict[str, Any]]:

    indexed = {}

    for item in context_result["comparisons"]:
        key = _pair_key(
            item["first_evidence_id"],
            item["second_evidence_id"],
        )

        indexed[key] = item["context_comparison"]

    return indexed


def _enrich_comparison(
    comparison: dict[str, Any],
    context_index: dict,
) -> dict[str, Any]:

    evidence = comparison.get("evidence", [])

    first_id = evidence[0].get("evidence_id") if len(evidence) > 0 else None
    second_id = evidence[1].get("evidence_id") if len(evidence) > 1 else None

    context = None

    if first_id and second_id:
        context = context_index.get(
            _pair_key(first_id, second_id)
        )

    classification = _classify_comparison(
        comparison,
        context,
    )

    # Do not describe evidence verification as legal confirmation.
    evidence_status = (
        "provisional"
        if comparison["assessment_status"] == "provisional"
        else "verified_evidence"
    )

    return {
        **comparison,
        **classification,
        "evidence_assessment": evidence_status,
        "context_analysis": context,
    }


def analyze_organization_portfolio(
    obligations: list[dict[str, Any]],
) -> dict[str, Any]:
    """
    Unified organization-level portfolio intelligence.

    Combines:
        1. Cross-contract obligation comparison.
        2. Trigger analysis.
        3. Responsible-party analysis.
        4. Direction analysis.
        5. Evidence-backed classification.

    This engine does not establish legal conflicts.
    Human review is required for potential dependencies
    and contractual variations.
    """

    eligible_obligations = [
        obligation
        for obligation in obligations
        if obligation.get("analysis_eligible") is not False
    ]

    comparison_result = compare_cross_contract_obligations(
        eligible_obligations
    )

    context_result = analyze_cross_contract_contexts(
        eligible_obligations
    )

    context_index = _index_context_comparisons(
        context_result
    )

    enriched_comparisons = [
        _enrich_comparison(comparison, context_index)
        for comparison in comparison_result["comparisons"]
    ]

    classification_counts = {}

    for comparison in enriched_comparisons:
        classification = comparison["classification"]

        classification_counts[classification] = (
            classification_counts.get(classification, 0) + 1
        )

    review_required = [
        comparison
        for comparison in enriched_comparisons
        if comparison["requires_human_review"]
    ]

    return {
        "summary": {
            "total_obligations": len(obligations),
            "eligible_obligations": len(eligible_obligations),
            "excluded_obligations": (
                len(obligations) - len(eligible_obligations)
            ),
            "total_comparisons": len(enriched_comparisons),
            "classification_counts": classification_counts,
            "human_review_required": len(review_required),
            "legal_conflicts_established": 0,
        },
        "comparisons": enriched_comparisons,
        "human_review_queue": review_required,
        "context_summary": context_result["summary"],
        "comparison_summary": comparison_result["summary"],
    }