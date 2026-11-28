from types import SimpleNamespace

from app.orchestration.verification_gate import (
    evaluate_verification_gate,
)


def make_state(
    obligations=None,
    verification_results=None,
):
    obligation_result = SimpleNamespace(
        status=SimpleNamespace(value="completed"),
        data={
            "obligations": obligations or [],
        },
    )

    verification_result = SimpleNamespace(
        status=SimpleNamespace(value="completed"),
        data={
            "results": verification_results or [],
        },
    )

    return SimpleNamespace(
        results={
            "obligation": obligation_result,
            "verification": verification_result,
        }
    )


def make_obligation(evidence_id="E1"):
    return {"evidence_id": evidence_id}


def make_verification(
    evidence_id="E1",
    outcome="verified",
    stored_status="verified",
    checks=None,
):
    return {
        "evidence_id": evidence_id,
        "outcome": outcome,
        "stored_verification_status": stored_status,
        "checks": checks or {
            "document_exists": True,
            "clause_exists": True,
            "document_matches": True,
            "page_matches": True,
            "offsets_valid": True,
            "source_text_matches": True,
        },
    }


def test_gate_passes_verified_evidence():
    state = make_state(
        obligations=[make_obligation()],
        verification_results=[make_verification()],
    )

    result = evaluate_verification_gate(state)

    assert result["passed"] is True
    assert result["decision"] == "approved"


def test_gate_blocks_unverified_evidence():
    state = make_state(
        obligations=[make_obligation()],
        verification_results=[
            make_verification(
                outcome="unverified",
                stored_status="unverified",
            )
        ],
    )

    result = evaluate_verification_gate(state)

    assert result["passed"] is False
    assert result["decision"] == "blocked"


def test_gate_blocks_invalid_provenance():
    checks = make_verification()["checks"]
    checks["source_text_matches"] = False

    state = make_state(
        obligations=[make_obligation()],
        verification_results=[
            make_verification(checks=checks)
        ],
    )

    result = evaluate_verification_gate(state)

    assert result["passed"] is False


def test_gate_blocks_missing_verification_record():
    state = make_state(
        obligations=[make_obligation("E1")],
        verification_results=[],
    )

    result = evaluate_verification_gate(state)

    assert result["passed"] is False


def test_gate_blocks_missing_obligation_result():
    state = SimpleNamespace(results={})

    result = evaluate_verification_gate(state)

    assert result["passed"] is False


def test_gate_blocks_empty_eligible_evidence():
    state = make_state(
        obligations=[],
        verification_results=[],
    )

    result = evaluate_verification_gate(state)

    assert result["passed"] is False


def test_gate_blocks_missing_approval():
    state = make_state(
        obligations=[make_obligation()],
        verification_results=[
            make_verification(
                outcome="unverified",
                stored_status="unverified",
            )
        ],
    )

    result = evaluate_verification_gate(state)

    assert result["passed"] is False

def test_gate_blocks_missing_provenance_checks():
    state = make_state(
        obligations=[make_obligation()],
        verification_results=[
            make_verification(
                checks={
                    "source_text_matches": True,
                }
            )
        ],
    )

    decision = evaluate_verification_gate(state)

    assert decision["passed"] is False
    assert decision["decision"] == "blocked"
    assert decision["verified_evidence_count"] == 0


def test_gate_blocks_false_provenance_check():
    checks = {
        "document_exists": True,
        "clause_exists": True,
        "document_matches": True,
        "page_matches": True,
        "offsets_valid": True,
        "source_text_matches": False,
    }

    state = make_state(
        obligations=[make_obligation()],
        verification_results=[
            make_verification(checks=checks)
        ],
    )

    decision = evaluate_verification_gate(state)

    assert decision["passed"] is False
    assert decision["decision"] == "blocked"
    assert decision["verified_evidence_count"] == 0