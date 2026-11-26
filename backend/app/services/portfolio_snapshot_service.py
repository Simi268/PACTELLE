from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.contract import Contract
from app.models.portfolio_risk_finding import PortfolioRiskFinding
from app.models.portfolio_analysis_snapshot import (
    PortfolioAnalysisSnapshot,
    PortfolioAnalysisSnapshotFinding,
)


def persist_portfolio_snapshot(
    db: Session,
    organization_id: UUID,
    created_findings: list[PortfolioRiskFinding],
    existing_findings: list[PortfolioRiskFinding],
    retrieval_summary: dict,
    intelligence_summary: dict,
    generation_summary: dict,
) -> PortfolioAnalysisSnapshot:

    findings_by_rule = {
        finding.rule_id: finding
        for finding in created_findings + existing_findings
    }

    findings = list(findings_by_rule.values())

    total_contracts = db.scalar(
        select(func.count(Contract.id)).where(
            Contract.organization_id == organization_id
        )
    ) or 0

    snapshot = PortfolioAnalysisSnapshot(
        organization_id=organization_id,
        analysis_version="1.0",
        total_contracts=total_contracts,
        total_obligations=retrieval_summary["normalized_obligations"],
        total_comparisons=intelligence_summary["total_comparisons"],
        total_findings=len(findings),
        summary={
            "retrieval": retrieval_summary,
            "intelligence": intelligence_summary,
            "generation": generation_summary,
        },
    )

    db.add(snapshot)
    db.flush()

    for finding in findings:
        snapshot_finding = PortfolioAnalysisSnapshotFinding(
            snapshot_id=snapshot.id,
            portfolio_finding_id=finding.id,
            rule_id=finding.rule_id,
            finding_type=finding.finding_type,
            title=finding.title,
            description=finding.description,
            severity=finding.severity,
            status=finding.status,
            assessment_status=finding.assessment_status,
            details=finding.details,
            contract_ids=sorted(
                str(link.contract_id)
                for link in finding.contract_links
            ),
            evidence_ids=sorted(
                str(link.evidence_record_id)
                for link in finding.evidence_links
            ),
        )

        db.add(snapshot_finding)

    db.flush()

    return snapshot