# PACTELLE Human Review Workflow

## Purpose

Human review is a persisted, organization-scoped decision checkpoint. It is used when an agent workflow needs an authorized person to inspect source evidence or a proposed interpretation before the result is relied upon.

## Request lifecycle

- `pending`: waiting for an authorized reviewer.
- `approved`: reviewer approved the submitted interpretation/action for the stated workflow context.
- `rejected`: reviewer rejected it.
- `clarification_requested`: reviewer needs more information; the request remains open for a subsequent reviewer decision.
- `cancelled`: reserved for a future requester/admin cancellation operation.

## Evidence provenance

A review request must reference at least one evidence record. Creation verifies that every evidence record belongs to the requested organization by traversing EvidenceRecord -> ContractDocument -> Contract. The service stores a JSON snapshot of the source excerpt, document and clause identifiers, page/character offsets, and verification status at request time. The snapshot preserves what the reviewer saw even if a later extraction changes the live evidence record.

A review decision does not modify evidence verification status and does not establish a legal conclusion. It records a human decision about the request context only.

## Authorization

- Any active organization member may create a review request and read the organization's review queue.
- Only organization owners/admins may decide a request.
- If a request is assigned, only that assigned reviewer may decide it.
- An assigned reviewer must be an owner/admin in the same organization.
- Organization scoping is enforced in every service query; inaccessible resources are not disclosed.

## Audit history

Creation and each decision append a `ReviewRequestAudit` row. The API exposes the audit history but provides no update/delete operation for audit rows.

## API

- `POST /api/v1/organizations/{organization_id}/reviews`
- `GET /api/v1/organizations/{organization_id}/reviews`
- `GET /api/v1/organizations/{organization_id}/reviews/{review_id}`
- `POST /api/v1/organizations/{organization_id}/reviews/{review_id}/decision`

## Execution integration boundary

A request may carry an `execution_id` so it can be correlated with an agent run. The existing Supervisor already stops at its verification gate and reports `review_required`; this milestone persists the human decision workflow around that checkpoint. Durable execution-state persistence and automatic Supervisor resume are separate follow-up work and must not be represented as complete until they are implemented and tested.
