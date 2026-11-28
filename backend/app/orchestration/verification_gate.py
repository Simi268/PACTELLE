"""Evidence verification gate for PACTELLE orchestration.

Only eligible evidence with approved verification status and valid
source provenance can pass this gate.

Rejected evidence remains excluded and does not independently block
otherwise eligible evidence.
"""

REQUIRED_PROVENANCE_CHECKS = {
    "document_exists",
    "clause_exists",
    "document_matches",
    "page_matches",
    "offsets_valid",
    "source_text_matches",
}


def evaluate_verification_gate(state) -> dict:
    obligation_result = state.results.get("obligation")
    verification_result = state.results.get("verification")

    if obligation_result is None:
        return _blocked("Obligation Agent result is missing.")

    if verification_result is None:
        return _blocked("Verification Agent result is missing.")

    if obligation_result.status.value != "completed":
        return _blocked("Obligation analysis did not complete.")

    if verification_result.status.value != "completed":
        return _blocked("Evidence verification did not complete.")

    obligations = obligation_result.data.get("obligations", [])

    if not isinstance(obligations, list):
        return _blocked("Eligible obligation collection is invalid.")

    eligible_ids = set()

    for obligation in obligations:
        if not isinstance(obligation, dict):
            return _blocked(
                "An eligible obligation has an invalid structure."
            )

        evidence_id = obligation.get("evidence_id")

        if not evidence_id:
            return _blocked(
                "An eligible obligation is missing its evidence identifier."
            )

        eligible_ids.add(str(evidence_id))

    if not eligible_ids:
        return _blocked(
            "No eligible evidence is available for intelligence analysis."
        )

    verification_data = verification_result.data
    verification_records = verification_data.get("results", [])

    if not isinstance(verification_records, list):
        return _blocked("Verification results have an invalid structure.")

    results_by_id = {}

    for record in verification_records:
        if not isinstance(record, dict):
            return _blocked(
                "A verification record has an invalid structure."
            )

        evidence_id = record.get("evidence_id")

        if evidence_id:
            results_by_id[str(evidence_id)] = record

    failures = []
    verified_evidence_ids = set()

    for evidence_id in sorted(eligible_ids):
        record = results_by_id.get(evidence_id)

        if record is None:
            failures.append(
                f"Evidence {evidence_id} has no verification result."
            )
            continue

        evidence_passed = True

        if record.get("outcome") != "verified":
            failures.append(
                f"Evidence {evidence_id} did not pass provenance verification."
            )
            evidence_passed = False

        if record.get("stored_verification_status") != "verified":
            failures.append(
                f"Evidence {evidence_id} has not been approved."
            )
            evidence_passed = False

        checks = record.get("checks")

        if not isinstance(checks, dict):
            failures.append(
                f"Evidence {evidence_id}: provenance checks are missing or invalid."
            )
            evidence_passed = False

        else:
            missing_checks = (
                REQUIRED_PROVENANCE_CHECKS - set(checks.keys())
            )

            if missing_checks:
                failures.append(
                    f"Evidence {evidence_id}: missing required provenance "
                    f"checks: {', '.join(sorted(missing_checks))}."
                )
                evidence_passed = False

            failed_checks = [
                check_name
                for check_name in REQUIRED_PROVENANCE_CHECKS
                if checks.get(check_name) is not True
            ]

            if failed_checks:
                failures.append(
                    f"Evidence {evidence_id}: provenance checks failed: "
                    f"{', '.join(sorted(failed_checks))}."
                )
                evidence_passed = False

        if evidence_passed:
            verified_evidence_ids.add(evidence_id)

    if failures:
        return {
            "passed": False,
            "decision": "blocked",
            "eligible_evidence_count": len(eligible_ids),
            "verified_evidence_count": len(verified_evidence_ids),
            "reasons": failures,
        }

    return {
        "passed": True,
        "decision": "approved",
        "eligible_evidence_count": len(eligible_ids),
        "verified_evidence_count": len(verified_evidence_ids),
        "reasons": [],
    }


def _blocked(reason: str) -> dict:
    return {
        "passed": False,
        "decision": "blocked",
        "eligible_evidence_count": 0,
        "verified_evidence_count": 0,
        "reasons": [reason],
    }