"""Explicit execution status transitions."""

from app.agents.contracts import ExecutionStatus


ALLOWED_TRANSITIONS = {
    ExecutionStatus.PENDING: {
        ExecutionStatus.RUNNING,
        ExecutionStatus.CANCELLED,
    },

    ExecutionStatus.RUNNING: {
        ExecutionStatus.COMPLETED,
        ExecutionStatus.NEEDS_OCR,
        ExecutionStatus.SUPERSEDED,
        ExecutionStatus.FAILED,
        ExecutionStatus.REVIEW_REQUIRED,
        ExecutionStatus.CANCELLED,
    },

    ExecutionStatus.COMPLETED: set(),
    ExecutionStatus.NEEDS_OCR: set(),
    ExecutionStatus.SUPERSEDED: set(),
    ExecutionStatus.FAILED: set(),
    ExecutionStatus.REVIEW_REQUIRED: set(),
    ExecutionStatus.CANCELLED: set(),
}


def transition_status(
    current: ExecutionStatus,
    target: ExecutionStatus,
) -> ExecutionStatus:

    if target not in ALLOWED_TRANSITIONS[current]:
        raise ValueError(
            f"Invalid execution status transition: "
            f"{current.value} -> {target.value}"
        )

    return target