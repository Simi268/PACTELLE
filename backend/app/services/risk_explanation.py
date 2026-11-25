from app.models.risk_finding import RiskFinding


def _get_recommended_action(risk_type):
    recommendations = {
        "renewal_exposure": (
            "Verify the renewal and non-renewal notice provisions. "
            "Confirm the applicable deadline and prepare any required "
            "communication for human review."
        ),
        "payment_risk": (
            "Review the payment obligations, applicable dates and "
            "supporting contractual provisions."
        ),
    }

    return recommendations.get(
        risk_type,
        "Review the underlying contractual provisions and supporting "
        "evidence. Determine whether further investigation or action "
        "is required."
    )


def explain_risk_finding(finding: RiskFinding):
    supporting_evidence = []
    rejected_evidence = []
    uncertainties = []

    links = finding.evidence_links or []

    for link in links:
        evidence = link.evidence_record

        if evidence is None:
            uncertainties.append(
                "A linked evidence record is unavailable."
            )
            continue

        if evidence.verification_status == "rejected":
            rejected_evidence.append({
                "evidence_id": str(evidence.id),
                "evidence_type": evidence.evidence_type,
                "reason": "This evidence has been rejected.",
            })
            continue

        clause = evidence.clause
        document = evidence.document

        source = {
            "evidence_id": str(evidence.id),
            "claim": evidence.claim,
            "evidence_type": evidence.evidence_type,
            "evidence_text": evidence.evidence_text,
            "verification_status": evidence.verification_status,
            "confidence": evidence.confidence,
            "extraction_method": evidence.extraction_method,
            "document": (
                document.original_filename
                if document else None
            ),
            "page_number": evidence.page_number,
            "clause": None,
        }

        if clause is not None:
            source["clause"] = {
                "clause_number": clause.clause_number,
                "clause_title": clause.clause_title,
                "category": clause.category,
                "source_text": clause.source_text,
                "page_number": clause.page_number,
                "char_start": clause.char_start,
                "char_end": clause.char_end,
                "extraction_method": clause.extraction_method,
            }
        else:
            uncertainties.append(
                f"Clause provenance is unavailable for evidence "
                f"{evidence.id}."
            )

        if document is None:
            uncertainties.append(
                f"Document provenance is unavailable for evidence "
                f"{evidence.id}."
            )

        if evidence.verification_status == "unverified":
            uncertainties.append(
                f"Evidence {evidence.id} has not been verified."
            )

        if evidence.confidence is None:
            uncertainties.append(
                f"Evidence {evidence.id} has no recorded confidence."
            )

        supporting_evidence.append(source)

    if not supporting_evidence:
        uncertainties.append(
            "No usable supporting evidence is currently available."
        )

    if finding.assessment_status == "provisional":
        uncertainties.append(
            "This finding is provisional and requires further "
            "evidence review."
        )

    if finding.deadline_date is None:
        uncertainties.append(
            "No contractual deadline has been established."
        )

    return {
        "risk_finding_id": str(finding.id),

        "risk": {
            "title": finding.title,
            "risk_type": finding.risk_type,
            "description": finding.description,
            "severity": finding.severity,
            "status": finding.status,
            "assessment_status": finding.assessment_status,
            "deadline_date": (
                finding.deadline_date.isoformat()
                if finding.deadline_date else None
            ),
            "detection_method": finding.detection_method,
            "rule_id": finding.rule_id,
            "rule_version": finding.rule_version,
        },

        "why_it_matters": finding.description,

        "supporting_evidence": supporting_evidence,

        "rejected_evidence": rejected_evidence,

        "uncertainties": list(dict.fromkeys(uncertainties)),

        "evidence_summary": {
            "total_linked": len(links),
            "supporting": len(supporting_evidence),
            "rejected": len(rejected_evidence),
            "verified": sum(
                item["verification_status"] == "verified"
                for item in supporting_evidence
            ),
            "unverified": sum(
                item["verification_status"] == "unverified"
                for item in supporting_evidence
            ),
        },

        "recommended_action": _get_recommended_action(
            finding.risk_type
        ),

        "human_review_required": (
            finding.assessment_status == "provisional"
            or bool(uncertainties)
        ),
    }