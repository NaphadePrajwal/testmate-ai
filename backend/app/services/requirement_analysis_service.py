from datetime import datetime, timezone
from typing import Any, Protocol

import httpx
from pydantic import ValidationError

from app.ai.requirement_analysis_prompt import PROMPT_VERSION, SYSTEM_PROMPT, build_requirement_prompt
from app.core.analysis_exceptions import (
    AnalysisConfigurationError,
    AnalysisInputError,
    AnalysisProviderError,
    InvalidAnalysisOutputError,
)
from app.core.config import Settings, get_settings
from app.models.requirement import Requirement
from app.schemas.requirement_analysis import AnalysisMetadata, RequirementAnalysis, RequirementAnalysisRead


ALLOWED_GEMINI_SCHEMA_KEYS = {
    "type",
    "description",
    "properties",
    "required",
    "items",
    "enum",
    "format",
    "nullable",
}


def _clean_schema_for_gemini(schema: dict[str, Any]) -> dict[str, Any]:
    """Inline JSON Schema $defs and strip unsupported keywords for Gemini API compatibility."""
    defs = schema.get("$defs", {})

    def clean_node(node: Any) -> Any:
        if isinstance(node, dict):
            if "$ref" in node:
                ref_name = node["$ref"].split("/")[-1]
                return clean_node(defs.get(ref_name, {}))
            cleaned: dict[str, Any] = {}
            for k, v in node.items():
                if k == "properties" and isinstance(v, dict):
                    cleaned["properties"] = {p_name: clean_node(p_schema) for p_name, p_schema in v.items()}
                elif k in ALLOWED_GEMINI_SCHEMA_KEYS:
                    cleaned[k] = clean_node(v)
            return cleaned
        elif isinstance(node, list):
            return [clean_node(x) for x in node]
        return node

    return clean_node(schema)


class RequirementAnalysisProvider(Protocol):
    provider_name: str
    model_name: str

    def analyze(self, requirement: Requirement) -> RequirementAnalysis: ...


class OpenAIResponsesProvider:
    """Small provider adapter using strict Responses API structured output."""

    provider_name = "openai"

    def __init__(self, settings: Settings) -> None:
        if settings.ai_provider != "openai":
            raise AnalysisConfigurationError("Unsupported requirement analysis provider.")
        if not settings.openai_api_key:
            raise AnalysisConfigurationError("OPENAI_API_KEY is not configured.")
        self.api_key = settings.openai_api_key
        self.model_name = settings.openai_model
        self.timeout_seconds = settings.analysis_timeout_seconds

    def analyze(self, requirement: Requirement) -> RequirementAnalysis:
        request_body = {
            "model": self.model_name,
            "store": False,
            "input": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": build_requirement_prompt(
                        requirement.title, requirement.description, requirement.acceptance_criteria
                    ),
                },
            ],
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "requirement_analysis",
                    "strict": True,
                    "schema": RequirementAnalysis.model_json_schema(),
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
            return RequirementAnalysis.model_validate_json(output_text)
        except (KeyError, TypeError, ValueError, ValidationError) as exc:
            raise InvalidAnalysisOutputError("The analysis provider returned invalid structured output.") from exc


class GeminiGenerateContentProvider:
    """Provider adapter using Google Gemini API generateContent structured output."""

    provider_name = "gemini"

    def __init__(self, settings: Settings) -> None:
        if settings.ai_provider != "gemini":
            raise AnalysisConfigurationError("Unsupported requirement analysis provider.")
        if not settings.gemini_api_key:
            raise AnalysisConfigurationError("GEMINI_API_KEY is not configured.")
        self.api_key = settings.gemini_api_key
        self.model_name = settings.gemini_model
        self.timeout_seconds = settings.analysis_timeout_seconds

    def analyze(self, requirement: Requirement) -> RequirementAnalysis:
        prompt_content = build_requirement_prompt(
            requirement.title, requirement.description, requirement.acceptance_criteria
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
                "response_schema": _clean_schema_for_gemini(RequirementAnalysis.model_json_schema()),
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
            return RequirementAnalysis.model_validate_json(output_text)
        except (KeyError, TypeError, ValueError, ValidationError) as exc:
            raise InvalidAnalysisOutputError("The analysis provider returned invalid structured output.") from exc


class RequirementAnalysisService:
    def __init__(self, provider: RequirementAnalysisProvider) -> None:
        self.provider = provider

    def analyze(self, requirement: Requirement) -> RequirementAnalysisRead:
        if not requirement.title.strip() or not requirement.description.strip():
            raise AnalysisInputError("This requirement needs a non-empty title and description before it can be analyzed.")
        try:
            analysis = RequirementAnalysis.model_validate(self.provider.analyze(requirement))
        except ValidationError as exc:
            raise InvalidAnalysisOutputError("The analysis provider returned invalid structured output.") from exc
        return RequirementAnalysisRead(
            analysis=analysis,
            metadata=AnalysisMetadata(
                provider=self.provider.provider_name,
                model=self.provider.model_name,
                prompt_version=PROMPT_VERSION,
                analyzed_at=datetime.now(timezone.utc),
            ),
        )


def get_requirement_analysis_service() -> RequirementAnalysisService:
    settings = get_settings()
    if settings.ai_provider == "openai":
        return RequirementAnalysisService(OpenAIResponsesProvider(settings))
    elif settings.ai_provider == "gemini":
        return RequirementAnalysisService(GeminiGenerateContentProvider(settings))
    raise AnalysisConfigurationError(f"Unsupported requirement analysis provider: '{settings.ai_provider}'. Must be 'openai' or 'gemini'.")
