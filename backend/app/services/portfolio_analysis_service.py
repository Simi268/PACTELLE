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


def run_organization_portfolio_analysis(
    db: Session,
    organization_id: UUID,
    commit: bool = False,
) -> dict[str, Any]:
    """
    Execute the complete organization-level portfolio
    intelligence workflow.

    Pipeline:
        1. Retrieve organization obligations.
        2. Analyze cross-contract relationships.
        3. Generate portfolio finding candidates.
        4. Persist findings with duplicate protection.

    commit=False allows the caller to control the
    surrounding database transaction.
    """

    # STEP 1: Retrieve normalized obligations.
    retrieval_result = retrieve_organization_obligations(
        db=db,
        organization_id=organization_id,
    )

    obligations = retrieval_result["obligations"]

    # STEP 2: Run unified portfolio intelligence.
    intelligence_result = analyze_organization_portfolio(
        obligations=obligations,
    )

    # STEP 3: Generate structured finding candidates.
    generation_result = generate_portfolio_findings(
        intelligence_result=intelligence_result,
    )

    generated_findings = generation_result["findings"]

    # STEP 4: Persist findings.
    persistence_result = persist_portfolio_findings(
        db=db,
        organization_id=organization_id,
        generated_findings=generated_findings,
        commit=commit,
    )

    return {
        "organization_id": str(organization_id),

        "retrieval": retrieval_result["summary"],

        "intelligence": intelligence_result["summary"],

        "generation": generation_result["summary"],

        "persistence": {
            "created_count": persistence_result["created_count"],
            "existing_count": persistence_result["existing_count"],
        },

        "created_findings": persistence_result["created_findings"],

        "existing_findings": persistence_result["existing_findings"],

        "human_review_queue": intelligence_result[
            "human_review_queue"
        ],

        "status": "completed",
    }