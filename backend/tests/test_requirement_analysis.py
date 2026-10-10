from uuid import UUID
import json

import httpx
import pytest
from fastapi.testclient import TestClient

from app.api.routes.requirements import analyze_requirement
from app.core.analysis_exceptions import AnalysisConfigurationError, AnalysisInputError, AnalysisProviderError, InvalidAnalysisOutputError
from app.core.config import Settings
from app.models.requirement import Requirement
from app.schemas.requirement_analysis import RequirementAnalysis
from app.services.requirement_analysis_service import (
    GeminiGenerateContentProvider,
    OpenAIResponsesProvider,
    RequirementAnalysisService,
    get_requirement_analysis_service,
)
from tests.test_core_workflow import create_project, create_requirement


def analysis_payload() -> dict[str, object]:
    explicit = {"text": "The requirement describes checkout total calculation.", "source": "explicit"}
    unspecified = {"text": "Unspecified.", "source": "unspecified"}
    return {
        "summary": explicit,
        "requirement_type": {"classification": "functional", "rationale": explicit},
        "actors_and_entities": [{"text": "Checkout", "source": "explicit"}],
        "expected_behaviors": [explicit],
        "inputs": [unspecified],
        "outputs": [unspecified],
        "preconditions": [unspecified],
        "postconditions": [unspecified],
        "acceptance_criteria": [{"text": "Confirm how totals are calculated.", "source": "suggested"}],
        "ambiguities_and_missing_information": [{"text": "Tax rules are not stated.", "source": "explicit"}],
        "dependencies_and_constraints": [],
        "clarification_questions": [{"text": "Which tax rules apply?", "source": "suggested"}],
        "quality_assessment": {
            "clarity": "medium",
            "completeness": "low",
            "reasons": [{"text": "Tax rules are absent.", "source": "explicit"}],
            "limitation": "This assesses only the supplied requirement text, not implementation correctness.",
        },
    }


class FakeProvider:
    provider_name = "fake"
    model_name = "fake-model"

    def __init__(self, payload: object) -> None:
        self.payload = payload

    def analyze(self, _: Requirement) -> object:
        return self.payload


def test_analysis_service_returns_validated_result_without_mutating_requirement() -> None:
    requirement = Requirement(title="Checkout total", description="Calculate the checkout total.", acceptance_criteria=[])
    result = RequirementAnalysisService(FakeProvider(analysis_payload())).analyze(requirement)

    assert result.analysis.summary.source == "explicit"
    assert result.analysis.acceptance_criteria[0].source == "suggested"
    assert result.metadata.prompt_version == "requirement-analysis-v1"
    assert requirement.description == "Calculate the checkout total."


def test_analysis_service_rejects_malformed_provider_output() -> None:
    requirement = Requirement(title="Checkout total", description="Calculate the checkout total.", acceptance_criteria=[])
    with pytest.raises(InvalidAnalysisOutputError):
        RequirementAnalysisService(FakeProvider({"summary": "not structured"})).analyze(requirement)


def test_analysis_service_rejects_unusable_requirement_content() -> None:
    requirement = Requirement(title=" ", description=" ", acceptance_criteria=[])
    with pytest.raises(AnalysisInputError):
        RequirementAnalysisService(FakeProvider(analysis_payload())).analyze(requirement)


def test_openai_provider_requires_configuration() -> None:
    with pytest.raises(AnalysisConfigurationError):
        OpenAIResponsesProvider(Settings(openai_api_key=None))


def test_openai_provider_translates_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    provider = OpenAIResponsesProvider(Settings(openai_api_key="test-key"))
    monkeypatch.setattr(httpx, "post", lambda *_, **__: (_ for _ in ()).throw(httpx.TimeoutException("timeout")))
    requirement = Requirement(title="Checkout total", description="Calculate the checkout total.", acceptance_criteria=[])
    with pytest.raises(AnalysisProviderError):
        provider.analyze(requirement)


def test_gemini_provider_requires_configuration() -> None:
    with pytest.raises(AnalysisConfigurationError):
        GeminiGenerateContentProvider(Settings(ai_provider="gemini", gemini_api_key=None))


def test_gemini_provider_successful_analysis(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = Settings(ai_provider="gemini", gemini_api_key="test-gemini-key", gemini_model="gemini-2.5-flash")
    provider = GeminiGenerateContentProvider(settings)

    gemini_response_data = {
        "candidates": [
            {
                "content": {
                    "parts": [{"text": json.dumps(analysis_payload())}],
                    "role": "model",
                },
                "finishReason": "STOP",
            }
        ]
    }

    captured_requests = []

    def mock_post(url: str, **kwargs: object) -> httpx.Response:
        captured_requests.append((url, kwargs))
        return httpx.Response(
            status_code=200, json=gemini_response_data, request=httpx.Request("POST", url)
        )

    monkeypatch.setattr(httpx, "post", mock_post)
    requirement = Requirement(title="Checkout total", description="Calculate checkout total.", acceptance_criteria=[])
    result = provider.analyze(requirement)

    assert result.summary.source == "explicit"
    assert provider.provider_name == "gemini"
    assert len(captured_requests) == 1
    req_url, req_kwargs = captured_requests[0]
    assert "gemini-2.5-flash:generateContent" in req_url
    assert req_kwargs["headers"]["x-goog-api-key"] == "test-gemini-key"


def test_gemini_provider_translates_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    provider = GeminiGenerateContentProvider(Settings(ai_provider="gemini", gemini_api_key="test-gemini-key"))
    monkeypatch.setattr(httpx, "post", lambda *_, **__: (_ for _ in ()).throw(httpx.TimeoutException("timeout")))
    requirement = Requirement(title="Checkout total", description="Calculate the checkout total.", acceptance_criteria=[])
    with pytest.raises(AnalysisProviderError):
        provider.analyze(requirement)


def test_gemini_provider_translates_rate_limit_and_error(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = Settings(ai_provider="gemini", gemini_api_key="test-gemini-key")
    provider = GeminiGenerateContentProvider(settings)
    requirement = Requirement(title="Checkout total", description="Calculate the checkout total.", acceptance_criteria=[])

    def mock_429(*_, **__):
        return httpx.Response(status_code=429, request=httpx.Request("POST", "https://api.test"))

    monkeypatch.setattr(httpx, "post", mock_429)
    with pytest.raises(AnalysisProviderError):
        provider.analyze(requirement)

    def mock_500(*_, **__):
        return httpx.Response(status_code=500, request=httpx.Request("POST", "https://api.test"))

    monkeypatch.setattr(httpx, "post", mock_500)
    with pytest.raises(AnalysisProviderError):
        provider.analyze(requirement)


def test_gemini_provider_handles_malformed_output(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = Settings(ai_provider="gemini", gemini_api_key="test-gemini-key")
    provider = GeminiGenerateContentProvider(settings)
    requirement = Requirement(title="Checkout total", description="Calculate the checkout total.", acceptance_criteria=[])

    dummy_request = httpx.Request("POST", "https://api.test")
    monkeypatch.setattr(
        httpx, "post", lambda *_, **__: httpx.Response(status_code=200, json={"candidates": []}, request=dummy_request)
    )
    with pytest.raises(InvalidAnalysisOutputError):
        provider.analyze(requirement)

    monkeypatch.setattr(
        httpx,
        "post",
        lambda *_, **__: httpx.Response(
            status_code=200,
            json={"candidates": [{"content": {"parts": [{"text": "not json"}]}}]},
            request=dummy_request,
        ),
    )
    with pytest.raises(InvalidAnalysisOutputError):
        provider.analyze(requirement)


def test_get_requirement_analysis_service_factory(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.services.requirement_analysis_service.get_settings",
        lambda: Settings(ai_provider="gemini", gemini_api_key="test-key"),
    )
    service = get_requirement_analysis_service()
    assert service.provider.provider_name == "gemini"

    monkeypatch.setattr(
        "app.services.requirement_analysis_service.get_settings",
        lambda: Settings(ai_provider="openai", openai_api_key="test-key"),
    )
    service = get_requirement_analysis_service()
    assert service.provider.provider_name == "openai"

    monkeypatch.setattr(
        "app.services.requirement_analysis_service.get_settings",
        lambda: Settings(ai_provider="unsupported"),
    )
    with pytest.raises(AnalysisConfigurationError):
        get_requirement_analysis_service()


def test_analysis_api_is_project_scoped_and_returns_structured_result(client: TestClient) -> None:
    project = create_project(client, "Analysis project")
    other_project = create_project(client, "Other analysis project")
    requirement = create_requirement(client, str(project["id"]), "Analyze this requirement")
    client.app.dependency_overrides[get_requirement_analysis_service] = lambda: RequirementAnalysisService(FakeProvider(analysis_payload()))
    try:
        response = client.post(f"/api/v1/projects/{project['id']}/requirements/{requirement['id']}/analysis")
        assert response.status_code == 200, response.text
        assert response.json()["analysis"]["summary"]["source"] == "explicit"
        assert response.json()["metadata"]["provider"] == "fake"
        assert client.post(f"/api/v1/projects/{other_project['id']}/requirements/{requirement['id']}/analysis").status_code == 404
        assert client.post(f"/api/v1/projects/{project['id']}/requirements/{UUID(int=0)}/analysis").status_code == 404
    finally:
        client.app.dependency_overrides.pop(get_requirement_analysis_service, None)


def test_analysis_api_hides_invalid_provider_details(client: TestClient) -> None:
    project = create_project(client, "Invalid analysis project")
    requirement = create_requirement(client, str(project["id"]), "Invalid output requirement")
    client.app.dependency_overrides[get_requirement_analysis_service] = lambda: RequirementAnalysisService(FakeProvider({}))
    try:
        response = client.post(f"/api/v1/projects/{project['id']}/requirements/{requirement['id']}/analysis")
        assert response.status_code == 502
        assert response.json() == {"detail": "Requirement analysis is temporarily unavailable. Please try again."}
    finally:
        client.app.dependency_overrides.pop(get_requirement_analysis_service, None)


def test_analysis_api_reports_missing_configuration_safely(client: TestClient) -> None:
    project = create_project(client, "Configuration analysis project")
    requirement = create_requirement(client, str(project["id"]), "Configuration requirement")

    def missing_configuration() -> RequirementAnalysisService:
        raise AnalysisConfigurationError("The actual provider setting must not be exposed.")

    client.app.dependency_overrides[get_requirement_analysis_service] = missing_configuration
    try:
        response = client.post(f"/api/v1/projects/{project['id']}/requirements/{requirement['id']}/analysis")
        assert response.status_code == 503
        assert response.json() == {"detail": "Requirement analysis is not configured. Set OPENAI_API_KEY and try again."}
    finally:
        client.app.dependency_overrides.pop(get_requirement_analysis_service, None)


def test_analysis_api_reports_missing_gemini_configuration_safely(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.core.errors.get_settings", lambda: Settings(ai_provider="gemini", gemini_api_key=None))
    project = create_project(client, "Gemini config project")
    requirement = create_requirement(client, str(project["id"]), "Gemini config requirement")

    def missing_gemini() -> RequirementAnalysisService:
        raise AnalysisConfigurationError("GEMINI_API_KEY is not configured.")

    client.app.dependency_overrides[get_requirement_analysis_service] = missing_gemini
    try:
        response = client.post(f"/api/v1/projects/{project['id']}/requirements/{requirement['id']}/analysis")
        assert response.status_code == 503
        assert response.json() == {"detail": "Requirement analysis is not configured. Set GEMINI_API_KEY and try again."}
    finally:
        client.app.dependency_overrides.pop(get_requirement_analysis_service, None)

