"""Document Agent for PACTELLE.

Coordinates the existing document processing pipeline.
Does not independently extract, modify or persist evidence.
"""

from uuid import UUID
from typing import Callable, Dict, Any

from app.agents.contracts import (
    AgentError,
    AgentName,
    AgentResult,
    AgentStatus,
)

from app.agents.state import AgentState

from app.services.document_pipeline import process_document_pipeline


class DocumentAgent:
    """Coordinates existing document processing functionality."""

    agent_name = AgentName.DOCUMENT

    def __init__(
        self,
        pipeline: Callable = process_document_pipeline,
    ):
        self.pipeline = pipeline

    def __call__(self, state: AgentState) -> AgentResult:

        document_id = state.task.input_data.get("document_id")
        attempt_id = state.task.input_data.get("attempt_id")

        # Validate task input.
        if not document_id or not attempt_id:
            return self._failure(
                code="INVALID_DOCUMENT_TASK",
                message="Document ID and attempt ID are required.",
            )

        try:
            document_uuid = UUID(str(document_id))
            attempt_uuid = UUID(str(attempt_id))

        except (ValueError, TypeError, AttributeError):
            return self._failure(
                code="INVALID_DOCUMENT_IDENTIFIER",
                message="Document ID or attempt ID is not a valid UUID.",
            )

        # Delegate to the existing deterministic pipeline.
        result = self.pipeline(
            document_uuid,
            attempt_uuid,
        )

        # The existing pipeline can return None after an internally
        # handled processing failure. Never interpret None as success.
        if result is None:
            return self._failure(
                code="DOCUMENT_PIPELINE_NO_RESULT",
                message=(
                    "Document pipeline returned no result. "
                    "Processing completion could not be confirmed."
                ),
            )

        if not isinstance(result, dict):
            return self._failure(
                code="INVALID_PIPELINE_RESPONSE",
                message="Document pipeline returned an invalid response.",
            )

        pipeline_status = result.get("status")

        if pipeline_status == "completed":
            return AgentResult(
                agent=self.agent_name,
                status=AgentStatus.COMPLETED,
                summary="Document processing completed.",
                data=result,
            )

        if pipeline_status == "needs_ocr":
            return AgentResult(
                agent=self.agent_name,
                status=AgentStatus.NEEDS_OCR,
                summary="Document requires OCR before further processing.",
                data=result,
                unresolved_questions=[
                    "Document text extraction requires OCR."
                ],
                human_review_required=True,
            )

        if pipeline_status == "superseded":
            return AgentResult(
                agent=self.agent_name,
                status=AgentStatus.SUPERSEDED,
                summary="Document processing attempt was superseded.",
                data=result,
            )

        return self._failure(
            code="UNKNOWN_PIPELINE_OUTCOME",
            message=(
                "Document pipeline returned an unrecognized processing "
                "outcome. No successful completion is assumed."
            ),
            data=result,
        )

    def _failure(
        self,
        code: str,
        message: str,
        data: Dict[str, Any] = None,
    ) -> AgentResult:

        return AgentResult(
            agent=self.agent_name,
            status=AgentStatus.FAILED,
            summary="Document processing did not complete successfully.",
            data=data or {},
            error=AgentError(
                agent=self.agent_name,
                code=code,
                message=message,
                retryable=False,
            ),
        )