from sqlalchemy import select, func
import uuid
from app.models.portfolio_analysis_snapshot import (
    PortfolioAnalysisSnapshot,
    PortfolioAnalysisSnapshotFinding,
)
from app.models.portfolio_risk_finding import PortfolioRiskFinding

from app.services.portfolio_analysis_service import (
    run_organization_portfolio_analysis,
)

from app.services.portfolio_finding_service import (
    update_portfolio_finding_status,
)

from tests.test_portfolio_finding_service import (
    prepare_valid_data,
)
from uuid import UUID
from app.models.document import ContractDocument

from tests.test_portfolio_analysis_api import create_dependency_evidence

def prepare_dependency_data(db, data):
    document_a = data["document_a"]

    document_b = ContractDocument(
        contract_id=data["empty_contract"].id,
        original_filename="snapshot_dependency_b.pdf",
        stored_filename=f"{uuid.uuid4()}.pdf",
        storage_path="uploads/snapshot_dependency_b.pdf",
        file_type="application/pdf",
        file_size=1024,
        processing_status="processed",
    )

    db.add(document_b)
    db.flush()

    create_dependency_evidence(
        db,
        document_a,
        "Vendor shall notify Customer "
        "90 days before changing subprocessors.",
        1,
    )

    create_dependency_evidence(
        db,
        document_b,
        "Customer shall approve subprocessor changes "
        "30 days before implementation.",
        2,
    )

    db.flush()


def test_analysis_creates_snapshot_with_correct_counts(
    db_session,
    contract_api_data,
):
    data = contract_api_data

    prepare_dependency_data(db_session, data)

    result = run_organization_portfolio_analysis(
        db_session,
        data["organization_a"].id,
    )

    snapshot = db_session.scalar(
        select(PortfolioAnalysisSnapshot).where(
            PortfolioAnalysisSnapshot.organization_id
            == data["organization_a"].id
        )
    )

    assert snapshot is not None

    assert result["snapshot"]["id"] == str(snapshot.id)

    assert snapshot.total_contracts == 2
    assert snapshot.total_obligations == result["retrieval"][
        "normalized_obligations"
    ]
    assert snapshot.total_comparisons == result["intelligence"][
        "total_comparisons"
    ]

    assert snapshot.total_findings == result["persistence"][
        "created_count"
    ] + result["persistence"]["existing_count"]


def test_analysis_creates_snapshot_even_without_findings(
    db_session,
    contract_api_data,
):
    data = contract_api_data

    result = run_organization_portfolio_analysis(
        db_session,
        data["organization_a"].id,
    )

    assert result["snapshot"]["total_findings"] == 0

    snapshots = db_session.scalars(
        select(PortfolioAnalysisSnapshot).where(
            PortfolioAnalysisSnapshot.organization_id
            == data["organization_a"].id
        )
    ).all()

    assert len(snapshots) == 1


def test_repeated_analysis_creates_separate_snapshots_without_duplicate_findings(
    db_session,
    contract_api_data,
):
    data = contract_api_data

    prepare_dependency_data(db_session, data)

    first = run_organization_portfolio_analysis(
        db_session,
        data["organization_a"].id,
    )

    second = run_organization_portfolio_analysis(
        db_session,
        data["organization_a"].id,
    )

    assert first["snapshot"]["id"] != second["snapshot"]["id"]

    assert second["persistence"]["created_count"] == 0
    assert second["persistence"]["existing_count"] == 1

    snapshot_count = db_session.scalar(
        select(func.count(PortfolioAnalysisSnapshot.id)).where(
            PortfolioAnalysisSnapshot.organization_id
            == data["organization_a"].id
        )
    )

    finding_count = db_session.scalar(
        select(func.count(PortfolioRiskFinding.id)).where(
            PortfolioRiskFinding.organization_id
            == data["organization_a"].id
        )
    )

    assert snapshot_count == 2
    assert finding_count == 1


def test_historical_snapshot_is_unchanged_after_live_finding_update(
    db_session,
    contract_api_data,
):
    data = contract_api_data

    prepare_dependency_data(db_session, data)

    result = run_organization_portfolio_analysis(
        db_session,
        data["organization_a"].id,
    )

    snapshot_finding = db_session.scalar(
        select(PortfolioAnalysisSnapshotFinding).where(
            PortfolioAnalysisSnapshotFinding.snapshot_id
            == UUID(result["snapshot"]["id"])
        )
    )

    assert snapshot_finding is not None
    assert snapshot_finding.status == "open"
    snapshot_finding_id = snapshot_finding.id

    finding = db_session.scalar(
        select(PortfolioRiskFinding).where(
            PortfolioRiskFinding.id
            == snapshot_finding.portfolio_finding_id
        )
    )

    update_portfolio_finding_status(
        db_session,
        data["organization_a"].id,
        finding.id,
        "acknowledged",
    )

    db_session.expire_all()

    historical_finding = db_session.get(
        PortfolioAnalysisSnapshotFinding,
        snapshot_finding.id,
    )

    live_finding = db_session.get(
        PortfolioRiskFinding,
        finding.id,
    )

    assert live_finding.status == "acknowledged"
    assert historical_finding.status == "open"


def test_snapshot_failure_rolls_back_analysis_when_commit_enabled(
    db_session,
    contract_api_data,
    monkeypatch,
):
    data = contract_api_data

    prepare_valid_data(db_session, data)

    def fail_snapshot(*args, **kwargs):
        raise RuntimeError("Simulated snapshot persistence failure")

    monkeypatch.setattr(
        "app.services.portfolio_analysis_service.persist_portfolio_snapshot",
        fail_snapshot,
    )

    import pytest

    with pytest.raises(
        RuntimeError,
        match="Simulated snapshot persistence failure",
    ):
        run_organization_portfolio_analysis(
            db_session,
            data["organization_a"].id,
            commit=True,
        )


    db_session.expire_all()

    findings = db_session.scalars(
        select(PortfolioRiskFinding).where(
            PortfolioRiskFinding.organization_id
            == data["organization_a"].id
        )
    ).all()

    snapshots = db_session.scalars(
        select(PortfolioAnalysisSnapshot).where(
            PortfolioAnalysisSnapshot.organization_id
            == data["organization_a"].id
        )
    ).all()

    assert findings == []
    assert snapshots == []