import hashlib
from typing import Any

GENERATOR_VERSION = "1.3"


def _build_rule_id(
    evidence_ids: list[str],
    classification: str = "operational_dependency",
) -> str:
    normalized_ids = sorted(str(item) for item in evidence_ids)
    fingerprint = classification + "|" + "|".join(normalized_ids)
    digest = hashlib.sha256(fingerprint.encode("utf-8")).hexdigest()[:24]
    return f"portfolio_{classification}_{digest}"


def _extract_contracts(comparison: dict[str, Any]) -> list[str]:
    return sorted({
        str(item["contract_id"])
        for item in comparison.get("evidence", [])
        if item.get("contract_id")
    })


def _extract_evidence_ids(comparison: dict[str, Any]) -> list[str]:
    return sorted({
        str(item["evidence_id"])
        for item in comparison.get("evidence", [])
        if item.get("evidence_id")
    })

def _build_liability_impact(comparison: dict[str, Any]) -> dict[str, Any]:
    """
    Generate an evidence-traceable and conservative business
    impact assessment using explicitly extracted liability attributes.
    """

    liability = comparison.get("liability_comparison") or {}

    first = liability.get("first") or {}
    second = liability.get("second") or {}

    first_period = first.get("reference_period")
    second_period = second.get("reference_period")

    differing = liability.get("differing_attributes") or []

    evidence = comparison.get("evidence") or []

    # Preserve source traceability.
    evidence_basis = []

    for item in evidence:
        provenance = item.get("provenance") or {}

        evidence_basis.append({
            "evidence_id": item.get("evidence_id"),
            "contract_id": item.get("contract_id"),
            "contract_title": item.get("contract_title"),
            "evidence_type": (
                item.get("evidence_type")
                or item.get("obligation_type")
            ),
            "claim": item.get("claim"),
            "source_excerpt": (
                item.get("original_text")
                or item.get("evidence_text")
                or item.get("claim")
            ),
            "verification_status": item.get("verification_status"),
            "provenance": {
                "document_id": (
                    item.get("document_id")
                    or provenance.get("document_id")
                ),
                "clause_id": (
                    item.get("clause_id")
                    or provenance.get("clause_id")
                ),
                "page_number": (
                    item.get("page_number")
                    or provenance.get("page_number")
                ),
                "char_start": (
                    item.get("char_start")
                    if item.get("char_start") is not None
                    else provenance.get("char_start")
                ),
                "char_end": (
                    item.get("char_end")
                    if item.get("char_end") is not None
                    else provenance.get("char_end")
                ),
            },
        })

    observed_facts = []

    fact_labels = {
        "reference_period": "The liability provisions have different reference periods.",
        "cap_multiplier": "The liability provisions use different explicit cap multipliers.",
        "cap_basis": "The liability provisions use different cap calculation bases.",
        "exceptions": "The liability provisions contain different detected exception categories.",
        "scope": "The liability provisions refer to different categories of claims.",
    }
    for attribute in differing:
        observed_facts.append(fact_labels.get(attribute, f"The liability provisions differ in: {attribute}."))

    comparison_result = None

    valid_periods = (
        isinstance(first_period, dict)
        and isinstance(second_period, dict)
        and first_period.get("unit") == second_period.get("unit")
        and isinstance(first_period.get("value"), (int, float))
        and isinstance(second_period.get("value"), (int, float))
        and first_period["value"] > 0
        and second_period["value"] > 0
    )

    if valid_periods:
        first_value = first_period["value"]
        second_value = second_period["value"]

        shorter_period = (
            "first_contract"
            if first_value < second_value
            else "second_contract"
            if second_value < first_value
            else None
        )

        comparison_result = {
            "first_contract_period": first_period,
            "second_contract_period": second_period,
            "shorter_period": shorter_period,
        }

        observed_facts.append(
            f"The first contract uses a {first_value}-"
            f"{first_period['unit']} reference period."
        )

        observed_facts.append(
            f"The second contract uses a {second_value}-"
            f"{second_period['unit']} reference period."
        )

    unknowns = [
        "Actual fees paid or payable during each reference period.",
        "The financial circumstances of the contracting parties.",
        "The complete contractual context and applicable exceptions.",
        "The practical financial consequences of the differing caps.",
    ]

    assessment = {
        "assessment_type": "contractual_liability_variation",

        "impact_level": "undetermined",

        "impact_level_rationale": (
            "A reliable impact level cannot be assigned without "
            "commercial and financial information. The detected "
            "contractual difference alone does not establish the "
            "magnitude of business exposure."
        ),

        "observed_facts": observed_facts,

        "business_impact": (
            "The contracts use different reference periods when "
            "calculating the aggregate liability cap. A shorter "
            "reference period may change the fees included in "
            "the cap calculation. The actual effect depends on "
            "the fees paid or payable during each period."
            if "reference_period" in differing
            else (
                "The contracts contain a difference in liability-cap "
                "terms. Its practical financial and contractual "
                "consequences require further review."
            )
        ),

        "potential_consequences": [
            "The amount available under the liability cap may differ "
            "between the agreements.",
            "The variation may affect financial risk allocation "
            "and contractual negotiation decisions.",
            "The actual impact depends on the fees paid or payable "
            "during the respective reference periods.",
        ],

        "assumptions": [],

        "unknowns": unknowns + [
            "Whether the compared passages are complete and whether related clauses modify them.",
            "Whether any exception category is subject to a separate cap or a different contractual mechanism.",
        ],

        "evidence_basis": evidence_basis,

        "recommended_action": (
            "Request legal and procurement review of the differing "
            "liability provisions. Obtain relevant fee information "
            "before assessing potential financial exposure."
        ),

        "financial_exposure": {
            "quantified": False,
            "amount": None,
            "currency": None,
            "reason": (
                "The available evidence does not contain sufficient "
                "financial information to calculate monetary exposure."
            ),
            "missing_inputs": [
                "Relevant fees paid or payable.",
                "Applicable fee calculation periods.",
                "Currency and financial reporting basis.",
            ],
        },

        "human_review_required": True,

        "legal_conclusion": None,

        "differing_attributes": differing,
    }

    if comparison_result is not None:
        assessment["comparison"] = comparison_result

    return assessment


def _build_operational_impact(comparison: dict[str, Any]) -> dict[str, Any]:
    context = comparison.get("context_analysis") or {}

    return {
        "assessment_type": "operational_dependency",
        "impact_level": "undetermined",
        "business_impact": (
            "The detected contractual obligations may create an "
            "operational dependency between the agreements."
        ),
        "potential_consequences": [
            "A delay or failure involving one obligation may affect "
            "the execution of another obligation.",
            "Different responsibilities or trigger conditions may "
            "create coordination requirements."
        ],
        "recommended_action": (
            "Review the linked obligations, responsible parties, "
            "and triggering conditions. Assign an owner if coordinated "
            "action is required."
        ),
        "trigger_relationship": context.get("trigger_relationship"),
        "responsibility_relationship": context.get(
            "responsibility_relationship"
        ),
        "direction_relationship": context.get("direction_relationship"),
        "human_review_required": True,
    }


def _build_finding(comparison: dict[str, Any]) -> dict[str, Any] | None:
    classification = comparison.get("classification")

    operational = (
        classification == "potential_operational_dependency"
        and comparison.get("operational_dependency_candidate")
    )

    liability_comparison_type = comparison.get("comparison_type")
    liability_variation = (
        classification in {
            "material_liability_variation",
            "liability_exception_variation",
        }
        and liability_comparison_type in {
            "liability_variance",
            "liability_exception_variation",
        }
    )

    if not (operational or liability_variation):
        return None

    contracts = _extract_contracts(comparison)
    evidence_ids = _extract_evidence_ids(comparison)

    if len(contracts) < 2 or len(evidence_ids) < 2:
        return None

    rule_kind = (
        classification
        if liability_variation
        else "operational_dependency"
    )

    rule_id = _build_rule_id(evidence_ids, rule_kind)
    obligation_type = comparison.get("obligation_type")

    if liability_variation:
        title_by_classification = {
            "material_liability_variation": "Material liability-cap variation across contracts",
            "liability_exception_variation": "Liability exceptions vary across contracts",
        }
        title = title_by_classification.get(
            classification, "Liability variation across contracts"
        )

        impact_assessment = _build_liability_impact(comparison)

        details = {
            "classification": classification,
            "obligation_type": obligation_type,
            "comparison_type": comparison.get("comparison_type"),
            "liability_comparison": comparison.get("liability_comparison"),
            "impact_assessment": impact_assessment,
            "requires_human_review": True,
            "legal_conflict_established": False,
            "generator_version": GENERATOR_VERSION,
        }

    else:
        title = f"Potential operational dependency: {obligation_type}"

        impact_assessment = _build_operational_impact(comparison)

        details = {
            "classification": classification,
            "obligation_type": obligation_type,
            "comparison_type": comparison.get("comparison_type"),
            "impact_assessment": impact_assessment,
            "requires_human_review": True,
            "legal_conflict_established": False,
            "generator_version": GENERATOR_VERSION,
        }

    return {
        "finding_type": "potential_conflict",
        "title": title,
        "description": comparison.get("explanation"),
        "severity": "medium",
        "status": "open",
        "assessment_status": "provisional",
        "detection_method": "rule_based",
        "rule_id": rule_id,
        "rule_version": GENERATOR_VERSION,
        "confidence": None,
        "details": details,
        "contract_ids": contracts,
        "evidence_ids": evidence_ids,
    }


def generate_portfolio_findings(
    intelligence_result: dict[str, Any],
) -> dict[str, Any]:

    comparisons = intelligence_result.get("comparisons", [])

    findings = []
    skipped_comparisons = 0
    seen_rule_ids = set()

    for comparison in comparisons:
        finding = _build_finding(comparison)

        if finding is None:
            skipped_comparisons += 1
            continue

        if finding["rule_id"] in seen_rule_ids:
            skipped_comparisons += 1
            continue

        seen_rule_ids.add(finding["rule_id"])
        findings.append(finding)

    return {
        "summary": {
            "total_comparisons": len(comparisons),
            "generated_findings": len(findings),
            "skipped_comparisons": skipped_comparisons,
            "provisional_findings": sum(
                item["assessment_status"] == "provisional"
                for item in findings
            ),
            "human_review_required": len(findings),
        },
        "findings": findings,
    }
