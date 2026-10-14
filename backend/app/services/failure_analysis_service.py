from datetime import datetime, timezone
from typing import Any, Protocol
from uuid import UUID, uuid4

import httpx
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.ai.failure_analysis_prompt import PROMPT_VERSION, SYSTEM_PROMPT, build_failure_analysis_prompt
from app.core.analysis_exceptions import (
    AnalysisConfigurationError,
    AnalysisProviderError,
    InvalidAnalysisOutputError,
)
from app.core.config import Settings, get_settings
from app.core.exceptions import ResourceConflictError, ResourceNotFoundError
from app.models.enums import ExecutionStatus
from app.models.execution_failure_analysis import ExecutionFailureAnalysis
from app.schemas.execution import ExecutionFailureContext
from app.schemas.failure_analysis import FailureAnalysisContent
from app.services.database import commit_or_rollback
from app.services.execution_service import ExecutionService
from app.services.project_service import ProjectService
from app.services.requirement_analysis_service import _clean_schema_for_gemini


class FailureAnalysisProvider(Protocol):
    provider_name: str
    model_name: str

    def analyze(self, context: ExecutionFailureContext) -> FailureAnalysisContent: ...


class OpenAIFailureAnalysisProvider:
    """Provider adapter using OpenAI Responses API structured output for failure diagnosis."""

    provider_name = "openai"

    def __init__(self, settings: Settings) -> None:
        if settings.ai_provider != "openai":
            raise AnalysisConfigurationError("Unsupported failure analysis provider.")
        if not settings.openai_api_key:
            raise AnalysisConfigurationError("OPENAI_API_KEY is not configured.")
        self.api_key = settings.openai_api_key
        self.model_name = settings.openai_model
        self.timeout_seconds = settings.analysis_timeout_seconds

    def analyze(self, context: ExecutionFailureContext) -> FailureAnalysisContent:
        request_body = {
            "model": self.model_name,
            "store": False,
            "input": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": build_failure_analysis_prompt(context)},
            ],
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "failure_analysis",
                    "strict": True,
                    "schema": FailureAnalysisContent.model_json_schema(),
                }
            },
        }
        try:
            response = httpx.post(
                "https://api.openai.com/v1/responses",
                headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
                json=request_body,
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
        except httpx.TimeoutException as exc:
            raise AnalysisProviderError("The analysis provider timed out.") from exc
        except httpx.HTTPStatusError as exc:
            raise AnalysisProviderError("The analysis provider rejected the request.") from exc
        except httpx.RequestError as exc:
            raise AnalysisProviderError("The analysis provider could not be reached.") from exc

        try:
            output_text = response.json()["output_text"]
            return FailureAnalysisContent.model_validate_json(output_text)
        except (KeyError, TypeError, ValueError, ValidationError) as exc:
            raise InvalidAnalysisOutputError("The analysis provider returned invalid structured output.") from exc


class GeminiFailureAnalysisProvider:
    """Provider adapter using Google Gemini generateContent structured output for failure diagnosis."""

    provider_name = "gemini"

    def __init__(self, settings: Settings) -> None:
        if settings.ai_provider != "gemini":
            raise AnalysisConfigurationError("Unsupported failure analysis provider.")
        if not settings.gemini_api_key:
            raise AnalysisConfigurationError("GEMINI_API_KEY is not configured.")
        self.api_key = settings.gemini_api_key
        self.model_name = settings.gemini_model
        self.timeout_seconds = settings.analysis_timeout_seconds

    def analyze(self, context: ExecutionFailureContext) -> FailureAnalysisContent:
        prompt_content = build_failure_analysis_prompt(context)
        request_body = {
            "system_instruction": {
                "parts": [{"text": SYSTEM_PROMPT}]
            },
            "contents": [
                {
                    "role": "user",
                    "parts": [{"text": prompt_content}],
                }
            ],
            "generationConfig": {
                "response_mime_type": "application/json",
                "response_schema": _clean_schema_for_gemini(FailureAnalysisContent.model_json_schema()),
            },
        }
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model_name}:generateContent"
        try:
            response = httpx.post(
                url,
                headers={
                    "x-goog-api-key": self.api_key,
                    "Content-Type": "application/json",
                },
                json=request_body,
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
        except httpx.TimeoutException as exc:
            raise AnalysisProviderError("The analysis provider timed out.") from exc
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 429:
                raise AnalysisProviderError("The analysis provider rate limit was exceeded. Please try again.") from exc
            raise AnalysisProviderError("The analysis provider rejected the request.") from exc
        except httpx.RequestError as exc:
            raise AnalysisProviderError("The analysis provider could not be reached.") from exc

        try:
            data = response.json()
            candidates = data.get("candidates", [])
            if not candidates:
                raise InvalidAnalysisOutputError("The analysis provider returned no candidates.")
            parts = candidates[0].get("content", {}).get("parts", [])
            if not parts or "text" not in parts[0]:
                raise InvalidAnalysisOutputError("The analysis provider returned empty output content.")
            output_text = parts[0]["text"]
            return FailureAnalysisContent.model_validate_json(output_text)
        except (KeyError, TypeError, ValueError, ValidationError) as exc:
            raise InvalidAnalysisOutputError("The analysis provider returned invalid structured output.") from exc


def get_failure_analysis_provider() -> FailureAnalysisProvider:
    settings = get_settings()
    if settings.ai_provider == "openai":
        return OpenAIFailureAnalysisProvider(settings)
    elif settings.ai_provider == "gemini":
        return GeminiFailureAnalysisProvider(settings)
    raise AnalysisConfigurationError(
        f"Unsupported failure analysis provider: '{settings.ai_provider}'. Must be 'openai' or 'gemini'."
    )


class FailureAnalysisService:
    """Service orchestrating execution failure diagnosis, provider dispatch, idempotency, and persistence."""

    def __init__(self, db: Session, provider: FailureAnalysisProvider | None = None) -> None:
        self.db = db
        self.provider = provider

    def get_or_create_analysis(
        self,
        project_id: UUID,
        execution_id: UUID,
        force_refresh: bool = False,
    ) -> ExecutionFailureAnalysis:
        """Run or return cached failure analysis for a completed failed/error execution."""
        execution = ExecutionService(self.db).get_execution(project_id, execution_id)

        # Execution must be terminal and non-successful
        if execution.status in (ExecutionStatus.QUEUED, ExecutionStatus.RUNNING):
            raise ResourceConflictError("Failure analysis cannot be performed while execution is in progress.")

        if execution.status == ExecutionStatus.PASSED:
            raise ResourceConflictError("Failure analysis is only available for failed or error executions.")

        # Check existing analysis for idempotency
        existing = self.db.scalar(
            select(ExecutionFailureAnalysis).where(
                ExecutionFailureAnalysis.execution_id == execution_id,
                ExecutionFailureAnalysis.project_id == project_id,
            )
        )
        if existing is not None and not force_refresh:
            return existing

        # Retrieve structured Phase 6 analysis context
        context = ExecutionService(self.db).get_execution_for_analysis(project_id, execution_id)

        # Resolve provider
        provider = self.provider or get_failure_analysis_provider()
        content = provider.analyze(context)

        metadata_dict = {
            "provider": provider.provider_name,
            "model": provider.model_name,
            "prompt_version": PROMPT_VERSION,
            "analyzed_at": datetime.now(timezone.utc).isoformat(),
        }

        if existing is not None:
            existing.failure_category = content.failure_category.value
            existing.summary = content.summary
            existing.observed_error = content.observed_error
            existing.likely_root_cause = content.likely_root_cause
            existing.supporting_evidence = content.supporting_evidence
            existing.recommended_debugging_steps = content.recommended_debugging_steps
            existing.confidence = content.confidence.value
            existing.uncertainty_notes = content.uncertainty_notes
            existing.metadata_ = metadata_dict
            commit_or_rollback(self.db)
            self.db.refresh(existing)
            return existing

        new_analysis = ExecutionFailureAnalysis(
            id=uuid4(),
            execution_id=execution_id,
            project_id=project_id,
            failure_category=content.failure_category.value,
            summary=content.summary,
            observed_error=content.observed_error,
            likely_root_cause=content.likely_root_cause,
            supporting_evidence=content.supporting_evidence,
            recommended_debugging_steps=content.recommended_debugging_steps,
            confidence=content.confidence.value,
            uncertainty_notes=content.uncertainty_notes,
            metadata_=metadata_dict,
        )
        self.db.add(new_analysis)
        commit_or_rollback(self.db)
        self.db.refresh(new_analysis)
        return new_analysis

    def get_analysis(self, project_id: UUID, execution_id: UUID) -> ExecutionFailureAnalysis:
        """Retrieve previously stored failure analysis for an execution."""
        # Ensure project and execution exist and belong to tenant
        ExecutionService(self.db).get_execution(project_id, execution_id)

        analysis = self.db.scalar(
            select(ExecutionFailureAnalysis).where(
                ExecutionFailureAnalysis.execution_id == execution_id,
                ExecutionFailureAnalysis.project_id == project_id,
            )
        )
        if analysis is None:
            raise ResourceNotFoundError("Failure analysis not found for this execution.")
        return analysis

    def list_analyses(
        self,
        project_id: UUID,
        limit: int,
        offset: int,
        failure_category: str | None = None,
    ) -> tuple[list[ExecutionFailureAnalysis], int]:
        """List failure analyses for a project with optional failure category filtering."""
        ProjectService(self.db).get_project(project_id)
        statement = select(ExecutionFailureAnalysis).where(ExecutionFailureAnalysis.project_id == project_id)
        if failure_category is not None:
            statement = statement.where(ExecutionFailureAnalysis.failure_category == failure_category)

        total = self.db.scalar(select(func.count()).select_from(statement.subquery())) or 0
        items = list(
            self.db.scalars(
                statement.order_by(ExecutionFailureAnalysis.created_at.desc()).offset(offset).limit(limit)
            )
        )
        return items, total
