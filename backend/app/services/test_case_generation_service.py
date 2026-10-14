from datetime import datetime, timezone
import json
from typing import Any, Protocol
from uuid import UUID

import httpx
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.test_case_generation_prompt import PROMPT_VERSION, SYSTEM_PROMPT, build_test_case_prompt
from app.core.analysis_exceptions import (
    AnalysisConfigurationError,
    AnalysisInputError,
    AnalysisProviderError,
    InvalidAnalysisOutputError,
)
from app.core.config import Settings, get_settings
from app.core.exceptions import ResourceNotFoundError
from app.models.enums import Priority, ReviewStatus, TestCaseStatus, TestType
from app.models.requirement import Requirement
from app.models.test_case import TestCase
from app.schemas.generated_test_case import (
    GeneratedTestCaseCollection,
    GeneratedTestCasesResponse,
    GenerationMetadata,
)
from app.schemas.test_case import TestCaseRead
from app.services.database import commit_or_rollback
from app.services.requirement_analysis_service import _clean_schema_for_gemini


class TestCaseGenerationProvider(Protocol):
    provider_name: str
    model_name: str

    def generate(self, requirement: Requirement) -> GeneratedTestCaseCollection: ...


class OpenAITestCaseProvider:
    provider_name = "openai"

    def __init__(self, settings: Settings) -> None:
        if settings.ai_provider != "openai":
            raise AnalysisConfigurationError("Unsupported test case generation provider.")
        if not settings.openai_api_key:
            raise AnalysisConfigurationError("OPENAI_API_KEY is not configured.")
        self.api_key = settings.openai_api_key
        self.model_name = settings.openai_model
        self.timeout_seconds = settings.analysis_timeout_seconds

    def generate(self, requirement: Requirement) -> GeneratedTestCaseCollection:
        request_body = {
            "model": self.model_name,
            "store": False,
            "input": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": build_test_case_prompt(
                        requirement.title,
                        requirement.description,
                        requirement.acceptance_criteria,
                        target_url=requirement.target_url,
                    ),
                },
            ],
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "test_case_generation",
                    "strict": True,
                    "schema": GeneratedTestCaseCollection.model_json_schema(),
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
            raise AnalysisProviderError("The test case generation provider timed out.") from exc
        except httpx.HTTPStatusError as exc:
            raise AnalysisProviderError("The test case generation provider rejected the request.") from exc
        except httpx.RequestError as exc:
            raise AnalysisProviderError("The test case generation provider could not be reached.") from exc

        try:
            output_text = response.json()["output_text"]
            return GeneratedTestCaseCollection.model_validate_json(output_text)
        except (KeyError, TypeError, ValueError, ValidationError) as exc:
            raise InvalidAnalysisOutputError("The test case generation provider returned invalid structured output.") from exc


class GeminiTestCaseProvider:
    provider_name = "gemini"

    def __init__(self, settings: Settings) -> None:
        if settings.ai_provider != "gemini":
            raise AnalysisConfigurationError("Unsupported test case generation provider.")
        if not settings.gemini_api_key:
            raise AnalysisConfigurationError("GEMINI_API_KEY is not configured.")
        self.api_key = settings.gemini_api_key
        self.model_name = settings.gemini_model
        self.timeout_seconds = settings.analysis_timeout_seconds

    def generate(self, requirement: Requirement) -> GeneratedTestCaseCollection:
        prompt_content = build_test_case_prompt(
            requirement.title,
            requirement.description,
            requirement.acceptance_criteria,
            target_url=requirement.target_url,
        )
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
                "response_schema": _clean_schema_for_gemini(GeneratedTestCaseCollection.model_json_schema()),
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
            raise AnalysisProviderError("The test case generation provider timed out.") from exc
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 429:
                raise AnalysisProviderError("The test case generation provider rate limit was exceeded. Please try again.") from exc
            raise AnalysisProviderError("The test case generation provider rejected the request.") from exc
        except httpx.RequestError as exc:
            raise AnalysisProviderError("The test case generation provider could not be reached.") from exc

        try:
            data = response.json()
            candidates = data.get("candidates", [])
            if not candidates:
                raise InvalidAnalysisOutputError("The test case generation provider returned no candidates.")
            parts = candidates[0].get("content", {}).get("parts", [])
            if not parts or "text" not in parts[0]:
                raise InvalidAnalysisOutputError("The test case generation provider returned empty output content.")
            output_text = parts[0]["text"]
            return GeneratedTestCaseCollection.model_validate_json(output_text)
        except (KeyError, TypeError, ValueError, ValidationError) as exc:
            raise InvalidAnalysisOutputError("The test case generation provider returned invalid structured output.") from exc


class TestCaseGenerationService:
    def __init__(self, db: Session, provider: TestCaseGenerationProvider) -> None:
        self.db = db
        self.provider = provider

    def generate_for_requirement(self, project_id: UUID, requirement_id: UUID) -> GeneratedTestCasesResponse:
        requirement = self.db.scalar(
            select(Requirement).where(Requirement.id == requirement_id, Requirement.project_id == project_id)
        )
        if requirement is None:
            raise ResourceNotFoundError("Requirement not found for this project.")

        if not requirement.title.strip() or not requirement.description.strip():
            raise AnalysisInputError("This requirement needs a non-empty title and description before test cases can be generated.")

        generated_collection = self.provider.generate(requirement)

        # Retrieve existing titles to prevent unique constraint conflicts
        existing_titles = set(
            self.db.scalars(select(TestCase.title).where(TestCase.requirement_id == requirement.id)).all()
        )

        persisted_cases: list[TestCase] = []
        for index, item in enumerate(generated_collection.test_cases, start=1):
            title = item.title.strip()
            # If title collision occurs, append unique suffix
            if title in existing_titles:
                candidate_title = f"{title} (v{index})"
                suffix = 2
                while candidate_title in existing_titles:
                    candidate_title = f"{title} (v{index}-{suffix})"
                    suffix += 1
                title = candidate_title
            existing_titles.add(title)

            steps_data = [
                {
                    "action": step.action,
                    "expected_result": step.expected_result,
                    "data": step.data,
                }
                for step in item.steps
            ]

            tc_target_url = item.target_url or requirement.target_url

            test_case = TestCase(
                requirement_id=requirement.id,
                title=title,
                description=item.description,
                target_url=tc_target_url,
                preconditions=item.preconditions,
                steps=steps_data,
                expected_result=item.expected_result,
                test_type=item.test_type,
                priority=item.priority,
                status=TestCaseStatus.DRAFT,
                review_status=ReviewStatus.PENDING,
                version=1,
            )
            self.db.add(test_case)
            persisted_cases.append(test_case)

        commit_or_rollback(self.db)
        for tc in persisted_cases:
            self.db.refresh(tc)

        return GeneratedTestCasesResponse(
            items=[TestCaseRead.model_validate(tc) for tc in persisted_cases],
            total_generated=len(persisted_cases),
            requirement_coverage_summary=generated_collection.requirement_coverage_summary,
            assumptions=generated_collection.assumptions,
            metadata=GenerationMetadata(
                provider=self.provider.provider_name,
                model=self.provider.model_name,
                prompt_version=PROMPT_VERSION,
                generated_at=datetime.now(timezone.utc),
            ),
        )


def get_test_case_generation_provider() -> TestCaseGenerationProvider:
    settings = get_settings()
    if settings.ai_provider == "openai":
        return OpenAITestCaseProvider(settings)
    elif settings.ai_provider == "gemini":
        return GeminiTestCaseProvider(settings)
    raise AnalysisConfigurationError(
        f"Unsupported test case generation provider: '{settings.ai_provider}'. Must be 'openai' or 'gemini'."
    )
