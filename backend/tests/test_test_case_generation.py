import json
from typing import Any
from uuid import uuid4

import httpx
import pytest
from fastapi.testclient import TestClient

from app.core.analysis_exceptions import (
    AnalysisConfigurationError,
    AnalysisInputError,
    AnalysisProviderError,
    InvalidAnalysisOutputError,
)
from app.core.config import Settings
from app.models.enums import Priority, ReviewStatus, TestCaseStatus, TestType
from app.models.requirement import Requirement
from app.schemas.generated_test_case import (
    GeneratedStep,
    GeneratedTestCaseCollection,
    GeneratedTestCaseItem,
    TestCaseCategory,
)
from app.services.test_case_generation_service import (
    GeminiTestCaseProvider,
    OpenAITestCaseProvider,
    TestCaseGenerationService,
    get_test_case_generation_provider,
)


def sample_generated_collection() -> dict[str, Any]:
    return {
        "test_cases": [
            {
                "title": "Successful checkout with valid card",
                "description": "Verifies standard positive checkout flow.",
                "category": "positive",
                "test_type": "web",
                "priority": "high",
                "preconditions": ["User is logged in", "Cart contains items"],
                "steps": [
                    {
                        "action": "Navigate to checkout page",
                        "expected_result": "Checkout form is displayed",
                        "data": {},
                    },
                    {
                        "action": "Submit valid payment details",
                        "expected_result": "Order confirmation is shown",
                        "data": {"card_number": "4111111111111111", "cvv": "123"},
                    },
                ],
                "expected_result": "Order is placed and receipt is emailed.",
                "test_data": {"amount": 99.99},
                "assumptions": ["Payment gateway is available"],
            },
            {
                "title": "Checkout rejected with expired card",
                "description": "Verifies negative error handling on expired credit card.",
                "category": "negative",
                "test_type": "web",
                "priority": "medium",
                "preconditions": ["User is on checkout page"],
                "steps": [
                    {
                        "action": "Submit expired card",
                        "expected_result": "Inline error message appears",
                        "data": {"expiry": "01/20"},
                    }
                ],
                "expected_result": "Payment is rejected with 'Card expired' warning.",
                "test_data": {"expiry": "01/20"},
                "assumptions": [],
            },
            {
                "title": "Checkout with zero items in cart",
                "description": "Boundary edge case testing checkout attempt with empty cart.",
                "category": "boundary",
                "test_type": "web",
                "priority": "medium",
                "preconditions": ["Cart item count is 0"],
                "steps": [
                    {
                        "action": "Click proceed to checkout",
                        "expected_result": "Redirect to cart with message",
                        "data": {},
                    }
                ],
                "expected_result": "Checkout is blocked and 'Cart is empty' banner is shown.",
                "test_data": {"item_count": 0},
                "assumptions": [],
            },
        ],
        "requirement_coverage_summary": "Covers positive payment, negative expiry validation, and boundary empty cart conditions.",
        "assumptions": ["Standard currency is USD"],
    }


class FakeTestCaseProvider:
    provider_name = "fake"
    model_name = "fake-model"

    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload = payload

    def generate(self, requirement: Requirement) -> GeneratedTestCaseCollection:
        return GeneratedTestCaseCollection.model_validate(self.payload)


# Unit tests for AI provider adapters and validation
def test_openai_test_case_provider_requires_configuration() -> None:
    with pytest.raises(AnalysisConfigurationError):
        OpenAITestCaseProvider(Settings(ai_provider="openai", openai_api_key=None))


def test_openai_test_case_provider_translates_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    provider = OpenAITestCaseProvider(Settings(ai_provider="openai", openai_api_key="test-key"))
    monkeypatch.setattr(httpx, "post", lambda *_, **__: (_ for _ in ()).throw(httpx.TimeoutException("timeout")))
    requirement = Requirement(title="Checkout", description="Checkout flow", acceptance_criteria=[])
    with pytest.raises(AnalysisProviderError):
        provider.generate(requirement)


def test_gemini_test_case_provider_requires_configuration() -> None:
    with pytest.raises(AnalysisConfigurationError):
        GeminiTestCaseProvider(Settings(ai_provider="gemini", gemini_api_key=None))


def test_gemini_test_case_provider_successful_generation(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = Settings(ai_provider="gemini", gemini_api_key="test-key", gemini_model="gemini-3.5-flash-lite")
    provider = GeminiTestCaseProvider(settings)

    fake_response = {
        "candidates": [
            {
                "content": {
                    "parts": [{"text": json.dumps(sample_generated_collection())}],
                    "role": "model",
                },
                "finishReason": "STOP",
            }
        ]
    }

    class MockResponse:
        def raise_for_status(self) -> None:
            pass

        def json(self) -> dict[str, Any]:
            return fake_response

    monkeypatch.setattr(httpx, "post", lambda *_, **__: MockResponse())
    requirement = Requirement(title="Checkout flow", description="Test requirement", acceptance_criteria=["Must pay"])
    result = provider.generate(requirement)
    assert len(result.test_cases) == 3
    assert result.test_cases[0].category == TestCaseCategory.POSITIVE
    assert result.test_cases[1].category == TestCaseCategory.NEGATIVE
    assert result.test_cases[2].category == TestCaseCategory.BOUNDARY


def test_generation_service_rejects_empty_requirement(db_session: Any) -> None:
    provider = FakeTestCaseProvider(sample_generated_collection())
    service = TestCaseGenerationService(db_session, provider)
    # Using random project and requirement IDs
    with pytest.raises(Exception):  # ResourceNotFoundError or AnalysisInputError
        service.generate_for_requirement(uuid4(), uuid4())


# API integration tests using isolated PostgreSQL database
def test_full_test_case_generation_and_review_lifecycle(client: TestClient) -> None:
    # 1. Create project and requirement
    p_res = client.post("/api/v1/projects", json={"name": "E-Commerce App", "description": "Online shop"})
    assert p_res.status_code == 201
    project_id = p_res.json()["id"]

    r_res = client.post(
        f"/api/v1/projects/{project_id}/requirements",
        json={
            "title": "Payment Checkout",
            "description": "Users must be able to complete purchase using credit card.",
            "status": "approved",
            "acceptance_criteria": ["Support Visa and Mastercard", "Show error for expired cards"],
        },
    )
    assert r_res.status_code == 201
    requirement_id = r_res.json()["id"]

    # 2. Override AI provider dependency with FakeTestCaseProvider
    fake_provider = FakeTestCaseProvider(sample_generated_collection())
    client.app.dependency_overrides[get_test_case_generation_provider] = lambda: fake_provider

    # 3. Generate test cases
    gen_res = client.post(f"/api/v1/projects/{project_id}/requirements/{requirement_id}/test-cases/generate")
    assert gen_res.status_code == 201
    gen_data = gen_res.json()
    assert gen_data["total_generated"] == 3
    items = gen_data["items"]
    assert len(items) == 3

    for item in items:
        # Check that generated test cases begin in pending review status
        assert item["review_status"] == "pending"
        assert item["status"] == "draft"
        assert item["requirement_id"] == requirement_id
        assert len(item["steps"]) > 0

    tc1_id = items[0]["id"]
    tc2_id = items[1]["id"]
    tc3_id = items[2]["id"]

    # 4. List test cases for requirement
    list_res = client.get(f"/api/v1/projects/{project_id}/requirements/{requirement_id}/test-cases")
    assert list_res.status_code == 200
    assert list_res.json()["total"] == 3

    # Filter by review_status=pending
    pending_list = client.get(f"/api/v1/projects/{project_id}/requirements/{requirement_id}/test-cases?review_status=pending")
    assert pending_list.status_code == 200
    assert pending_list.json()["total"] == 3

    # 5. Edit pending test case (editing should keep review_status as pending, not auto-approve)
    patch_res = client.patch(
        f"/api/v1/projects/{project_id}/requirements/{requirement_id}/test-cases/{tc1_id}",
        json={"title": "Updated checkout title", "priority": "critical"},
    )
    assert patch_res.status_code == 200
    patched_data = patch_res.json()
    assert patched_data["title"] == "Updated checkout title"
    assert patched_data["priority"] == "critical"
    assert patched_data["review_status"] == "pending"
    assert patched_data["version"] == 2

    # 6. Approve test case
    appr_res = client.post(f"/api/v1/projects/{project_id}/requirements/{requirement_id}/test-cases/{tc1_id}/approve")
    assert appr_res.status_code == 200
    appr_data = appr_res.json()
    assert appr_data["review_status"] == "approved"
    assert appr_data["status"] == "approved"
    assert appr_data["version"] == 3

    # Attempting to re-approve an approved case should fail with 409 Conflict
    re_appr = client.post(f"/api/v1/projects/{project_id}/requirements/{requirement_id}/test-cases/{tc1_id}/approve")
    assert re_appr.status_code == 409

    # Attempting to reject an already approved case should fail with 409 Conflict
    appr_to_rej = client.post(f"/api/v1/projects/{project_id}/requirements/{requirement_id}/test-cases/{tc1_id}/reject")
    assert appr_to_rej.status_code == 409

    # 7. Reject another test case
    rej_res = client.post(f"/api/v1/projects/{project_id}/requirements/{requirement_id}/test-cases/{tc2_id}/reject")
    assert rej_res.status_code == 200
    rej_data = rej_res.json()
    assert rej_data["review_status"] == "rejected"
    assert rej_data["status"] == "retired"

    # Attempting to re-reject a rejected case should fail with 409 Conflict
    re_rej = client.post(f"/api/v1/projects/{project_id}/requirements/{requirement_id}/test-cases/{tc2_id}/reject")
    assert re_rej.status_code == 409

    # Attempting to approve a rejected case should fail with 409 Conflict
    rej_to_appr = client.post(f"/api/v1/projects/{project_id}/requirements/{requirement_id}/test-cases/{tc2_id}/approve")
    assert rej_to_appr.status_code == 409

    # 8. Check filtered counts
    appr_filter = client.get(f"/api/v1/projects/{project_id}/requirements/{requirement_id}/test-cases?review_status=approved")
    assert appr_filter.json()["total"] == 1

    rej_filter = client.get(f"/api/v1/projects/{project_id}/requirements/{requirement_id}/test-cases?review_status=rejected")
    assert rej_filter.json()["total"] == 1

    pend_filter = client.get(f"/api/v1/projects/{project_id}/requirements/{requirement_id}/test-cases?review_status=pending")
    assert pend_filter.json()["total"] == 1

    # 9. Scoping security: Trying to access test case under another random project returns 404
    other_proj_res = client.get(f"/api/v1/projects/{uuid4()}/requirements/{requirement_id}/test-cases/{tc1_id}")
    assert other_proj_res.status_code == 404

    # Cleanup dependency override
    client.app.dependency_overrides.pop(get_test_case_generation_provider, None)
