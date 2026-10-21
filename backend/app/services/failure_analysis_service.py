from datetime import datetime, timezone
import logging
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
from app.models.knowledge_indexing_job import IndexingJobAction
from app.schemas.execution import ExecutionFailureContext
from app.schemas.failure_analysis import FailureAnalysisContent
from app.schemas.knowledge import HistoricalCandidateItem, KnowledgeRecordType
from app.services.database import commit_or_rollback
from app.services.execution_service import ExecutionService
from app.services.knowledge_indexing_job_service import KnowledgeIndexingJobService
from app.services.knowledge_retrieval_service import KnowledgeRetrievalService
from app.services.project_service import ProjectService
from app.services.requirement_analysis_service import _clean_schema_for_gemini

logger = logging.getLogger(__name__)


def extract_failure_search_query(context: ExecutionFailureContext) -> str:
    """
    Extract a concise, bounded search query from an execution failure context
    to find semantically relevant historical defects, failure analyses, and test cases.
    """
    parts: list[str] = []

    # 1. Primary failure reason / error message
    if context.sanitized_failure_reason and context.sanitized_failure_reason.strip():
        parts.append(context.sanitized_failure_reason.strip())
    elif context.error_message and context.error_message.strip():
        parts.append(context.error_message.strip())

    # 2. Specific failed step details
    if context.failed_step:
        fs = context.failed_step
        fs_err = fs.error_message or fs.error_details
        if fs_err and fs_err.strip() and fs_err.strip() not in parts:
            parts.append(fs_err.strip())
        if fs.action and fs.action.strip():
            parts.append(f"Failed step: {fs.action.strip()}")

    # 3. Fallback to test case title if no error text is available
    if not parts and context.test_case_title:
        parts.append(f"Test failure in {context.test_case_title.strip()}")

    combined = " | ".join(parts).strip()
    if len(combined) > 500:
        combined = combined[:500]
    return combined or f"Execution failure in {context.test_case_title}"


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

    def __init__(
        self,
        db: Session,
        provider: FailureAnalysisProvider | None = None,
        retrieval_service: KnowledgeRetrievalService | None = None,
        job_service: KnowledgeIndexingJobService | None = None,
    ) -> None:
        self.db = db
        self.provider = provider
        self.retrieval_service = retrieval_service
        self.job_service = job_service

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

        # Retrieve relevant historical knowledge (RAG)
        candidates: list[HistoricalCandidateItem] = []
        retrieval_status = "not_attempted"
        retrieval_error = None

        try:
            query = extract_failure_search_query(context)
            retrieval_svc = self.retrieval_service or KnowledgeRetrievalService(db=self.db)
            retrieval_res = retrieval_svc.search_project_knowledge(
                project_id=project_id,
                query=query,
                limit=3,
            )
            candidates = retrieval_res.candidates or []
            retrieval_status = "success" if candidates else "no_matches"
        except Exception as exc:
            logger.warning(
                "Historical knowledge retrieval failed for execution %s (falling back to standard analysis): %s",
                execution_id,
                exc,
            )
            retrieval_status = "failed"
            retrieval_error = str(exc)
            candidates = []

        context.historical_candidates = candidates

        # Resolve provider
        provider = self.provider or get_failure_analysis_provider()
        content = provider.analyze(context)

        metadata_dict = {
            "provider": provider.provider_name,
            "model": provider.model_name,
            "prompt_version": PROMPT_VERSION,
            "analyzed_at": datetime.now(timezone.utc).isoformat(),
            "historical_retrieval_status": retrieval_status,
            "historical_candidates_count": len(candidates),
        }
        if retrieval_error:
            metadata_dict["historical_retrieval_error"] = retrieval_error

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
            self._trigger_auto_indexing(existing.project_id, KnowledgeRecordType.FAILURE_ANALYSIS, existing.id)
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
        self._trigger_auto_indexing(new_analysis.project_id, KnowledgeRecordType.FAILURE_ANALYSIS, new_analysis.id)
        return new_analysis

    def _trigger_auto_indexing(
        self,
        project_id: UUID,
        record_type: KnowledgeRecordType | str,
        source_id: UUID,
        action: IndexingJobAction | str = IndexingJobAction.UPSERT,
    ) -> None:
        """Enqueue durable outbox indexing job and attempt non-blocking immediate processing."""
        try:
            job_svc = self.job_service or KnowledgeIndexingJobService(db=self.db)
            job = job_svc.enqueue_job(
                project_id=project_id,
                record_type=record_type,
                source_id=source_id,
                action=action,
            )
            job_svc.process_job(job.id)
        except Exception as exc:
            logger.warning("Automatic indexing trigger failed for %s (%s): %s", record_type, source_id, exc)

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
