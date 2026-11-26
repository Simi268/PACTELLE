from uuid import UUID
from typing import Any

from sqlalchemy.orm import Session

from app.services.portfolio_obligation_service import (
    retrieve_organization_obligations,
)

from app.services.portfolio_intelligence_engine import (
    analyze_organization_portfolio,
)

from app.services.portfolio_finding_generator import (
    generate_portfolio_findings,
)

from app.services.portfolio_finding_service import (
    persist_portfolio_findings,
)

from app.services.portfolio_snapshot_service import (
    persist_portfolio_snapshot,
)


def run_organization_portfolio_analysis(
    db: Session,
    organization_id: UUID,
    commit: bool = False,
) -> dict[str, Any]:

    try:
        # STEP 1: Retrieve obligations.
        retrieval_result = retrieve_organization_obligations(
            db=db,
            organization_id=organization_id,
        )

        obligations = retrieval_result["obligations"]

        # STEP 2: Analyze portfolio.
        intelligence_result = analyze_organization_portfolio(
            obligations=obligations,
        )

        # STEP 3: Generate findings.
        generation_result = generate_portfolio_findings(
            intelligence_result=intelligence_result,
        )

        generated_findings = generation_result["findings"]

        # STEP 4: Persist findings without committing.
        persistence_result = persist_portfolio_findings(
            db=db,
            organization_id=organization_id,
            generated_findings=generated_findings,
            commit=False,
        )

        # STEP 5: Create historical snapshot.
        snapshot = persist_portfolio_snapshot(
            db=db,
            organization_id=organization_id,
            created_findings=persistence_result["created_findings"],
            existing_findings=persistence_result["existing_findings"],
            retrieval_summary=retrieval_result["summary"],
            intelligence_summary=intelligence_result["summary"],
            generation_summary=generation_result["summary"],
        )

        # STEP 6: Commit both operations together.
        if commit:
            db.commit()
            db.refresh(snapshot)

        return {
            "organization_id": str(organization_id),

            "retrieval": retrieval_result["summary"],

            "intelligence": intelligence_result["summary"],

            "generation": generation_result["summary"],

            "persistence": {
                "created_count": persistence_result["created_count"],
                "existing_count": persistence_result["existing_count"],
            },

            "snapshot": {
                "id": str(snapshot.id),
                "total_contracts": snapshot.total_contracts,
                "total_obligations": snapshot.total_obligations,
                "total_comparisons": snapshot.total_comparisons,
                "total_findings": snapshot.total_findings,
            },

            "created_findings": persistence_result["created_findings"],

            "existing_findings": persistence_result["existing_findings"],

            "human_review_queue": intelligence_result[
                "human_review_queue"
            ],

            "status": "completed",
        }

    except Exception:
        if commit:
            db.rollback()
        raise