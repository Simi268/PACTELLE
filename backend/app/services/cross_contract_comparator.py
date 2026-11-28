from itertools import combinations
from typing import Any


def _duration_key(duration: dict | None):
    if not duration:
        return None
    value = duration.get("value")
    unit = duration.get("unit")
    if not isinstance(value, (int, float)) or value <= 0:
        return None
    if unit not in {"days", "weeks", "months", "years"}:
        return None
    return value, unit


def _build_evidence_reference(obligation: dict[str, Any]) -> dict[str, Any]:
    provenance = obligation.get("provenance") or {}
    return {
        "evidence_id": obligation.get("evidence_id"),
        "contract_id": obligation.get("contract_id"),
        "contract_title": obligation.get("contract_title"),
        "obligation_type": obligation.get("obligation_type"),
        "evidence_type": obligation.get("obligation_type"),
        "claim": obligation.get("claim"),
        "original_text": obligation.get("original_text"),
        "duration": obligation.get("duration"),
        "liability_attributes": obligation.get("liability_attributes"),
        "verification_status": obligation.get("verification_status"),
        "provenance": provenance,
        "document_id": provenance.get("document_id"),
        "clause_id": provenance.get("clause_id"),
        "page_number": provenance.get("page_number"),
        "char_start": provenance.get("char_start"),
        "char_end": provenance.get("char_end"),
    }


def _liability_comparison(first: dict, second: dict) -> dict[str, Any] | None:
    obligation_type = first.get("obligation_type")
    if obligation_type not in {"liability_cap", "liability_exceptions"}:
        return None
    a = first.get("liability_attributes") or {}
    b = second.get("liability_attributes") or {}
    if not a or not b:
        return {
            "comparison_type": "insufficient_data",
            "explanation": "Liability evidence exists, but one or both passages lack normalized attributes.",
            "liability_comparison": {"first": a, "second": b, "comparable_scope": False, "differing_attributes": []},
        }

    if obligation_type == "liability_exceptions":
        exceptions_a = set(a.get("exceptions") or [])
        exceptions_b = set(b.get("exceptions") or [])
        differing = sorted(exceptions_a.symmetric_difference(exceptions_b))
        unknown_exception_wording = bool(a.get("exception_language_detected") or b.get("exception_language_detected"))
        if differing or (unknown_exception_wording and exceptions_a != exceptions_b):
            return {
                "comparison_type": "liability_exception_variation",
                "explanation": "The agreements contain different detected liability exception or carve-out categories. The full clauses and their interaction with the caps require legal review.",
                "liability_comparison": {
                    "first": a, "second": b, "comparable_scope": True,
                    "scope_matches": True, "differing_attributes": ["exceptions"],
                    "exceptions_only_first": sorted(exceptions_a - exceptions_b),
                    "exceptions_only_second": sorted(exceptions_b - exceptions_a),
                    "exception_wording_requires_review": unknown_exception_wording,
                },
            }
        return {
            "comparison_type": "similar",
            "explanation": "The detected liability exception categories match; this does not establish identical legal effect.",
            "liability_comparison": {"first": a, "second": b, "comparable_scope": True, "scope_matches": True, "differing_attributes": []},
        }

    scope_a = sorted(a.get("scope") or ["unknown"])
    scope_b = sorted(b.get("scope") or ["unknown"])
    if scope_a != scope_b:
        # Different scopes are not like-for-like cap terms. Preserve the
        # evidence and scope delta, but do not generate a comparative risk
        # finding from non-equivalent provisions.
        return {
            "comparison_type": "scope_variation",
            "explanation": "The liability provisions cover different detected claim scopes and are not directly comparable. Review the complete clauses before drawing a portfolio-level conclusion.",
            "liability_comparison": {
                "first": a, "second": b, "scope_matches": False,
                "comparable_scope": False, "differing_attributes": ["scope"],
                "scope_only_first": sorted(set(scope_a) - set(scope_b)),
                "scope_only_second": sorted(set(scope_b) - set(scope_a)),
            },
        }

    fields = ("cap_multiplier", "reference_period", "cap_basis", "exceptions")
    differences = [field for field in fields if a.get(field) != b.get(field)]
    # Missing values are unknown, not affirmative differences. Only compare
    # a field when both agreements contain an explicit value, except where
    # one side explicitly supplies a value and the other does not.
    if differences:
        return {
            "comparison_type": "liability_variance",
            "explanation": "The agreements contain liability caps with matching detected scope but differing explicit cap attributes: " + ", ".join(differences) + ". This is a contractual variation, not proof of legal conflict.",
            "liability_comparison": {
                "first": a, "second": b, "scope_matches": True,
                "comparable_scope": True, "differing_attributes": differences,
                "cap_tier": "enhanced" if scope_a != ["general"] else "general",
            },
        }
    return {
        "comparison_type": "similar",
        "explanation": "The detected liability-cap scope and explicit cap attributes match.",
        "liability_comparison": {"first": a, "second": b, "scope_matches": True, "comparable_scope": True, "differing_attributes": []},
    }


def _build_comparison(first: dict[str, Any], second: dict[str, Any]) -> dict[str, Any] | None:
    if first.get("contract_id") == second.get("contract_id"):
        return None
    first_type = first.get("obligation_type")
    if not first_type or first_type != second.get("obligation_type"):
        return None

    liability_result = _liability_comparison(first, second)
    first_duration = _duration_key(first.get("duration"))
    second_duration = _duration_key(second.get("duration"))
    if liability_result is not None:
        comparison_type = liability_result["comparison_type"]
        explanation = liability_result["explanation"]
    elif first_duration is None or second_duration is None:
        comparison_type = "insufficient_data"
        explanation = "The obligations are comparable by type, but their durations cannot be reliably compared."
    elif first_duration == second_duration:
        comparison_type = "similar"
        explanation = "Both contracts contain the same obligation type and normalized duration."
    else:
        comparison_type = "term_variance"
        explanation = "Both contracts contain the same obligation type, but their normalized durations differ. This is a contractual variation, not proof of conflict."

    statuses = {first.get("verification_status"), second.get("verification_status")}
    provisional = bool(statuses.intersection({"unverified", "rejected", None}))
    result = {
        "comparison_type": comparison_type,
        "obligation_type": first_type,
        "obligation_family": first.get("obligation_family"),
        "assessment_status": "provisional" if provisional else "confirmed",
        "explanation": explanation,
        "duration_comparison": {
            "first": first.get("duration"), "second": second.get("duration"),
            "matches": first_duration == second_duration if first_duration is not None and second_duration is not None else None,
        },
        "requires_review": comparison_type != "similar" or provisional,
        "legal_conflict_established": False,
        "evidence": [_build_evidence_reference(first), _build_evidence_reference(second)],
    }
    if liability_result is not None:
        result["liability_comparison"] = liability_result["liability_comparison"]
    return result


def compare_obligation_pair(first: dict[str, Any], second: dict[str, Any]) -> dict[str, Any] | None:
    if first.get("analysis_eligible") is False or second.get("analysis_eligible") is False:
        return None
    return _build_comparison(first, second)


def compare_cross_contract_obligations(obligations: list[dict[str, Any]]) -> dict[str, Any]:
    grouped = {}
    skipped_rejected = 0
    skipped_invalid = 0
    for obligation in obligations:
        if obligation.get("analysis_eligible") is False:
            skipped_rejected += 1
            continue
        if not obligation.get("contract_id") or not obligation.get("obligation_type"):
            skipped_invalid += 1
            continue
        grouped.setdefault(obligation["obligation_type"], []).append(obligation)

    comparisons = []
    for obligation_type in sorted(grouped):
        for first, second in combinations(grouped[obligation_type], 2):
            comparison = compare_obligation_pair(first, second)
            if comparison is not None:
                comparisons.append(comparison)

    keys = ("similar", "term_variance", "insufficient_data", "liability_variance", "scope_variation", "liability_exception_variation")
    counts = {key: 0 for key in keys}
    for comparison in comparisons:
        key = comparison["comparison_type"]
        counts[key] = counts.get(key, 0) + 1
    return {
        "summary": {"total_obligations": len(obligations), "total_comparisons": len(comparisons), **counts, "skipped_rejected": skipped_rejected, "skipped_invalid": skipped_invalid},
        "comparisons": comparisons,
    }
