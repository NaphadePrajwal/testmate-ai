from datetime import datetime, timezone
from unittest.mock import MagicMock, patch
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.url_utils import (
    extract_target_url,
    is_blocked_host,
    resolve_navigation_url,
    validate_and_normalize_url,
)
from app.models.enums import ExecutionStatus, Priority, ReviewStatus, TestCaseStatus, TestType
from app.models.project import Project
from app.models.requirement import Requirement
from app.models.test_case import TestCase
from app.models.test_execution import TestExecution
from app.schemas.generated_test_case import (
    GeneratedStep,
    GeneratedTestCaseCollection,
    GeneratedTestCaseItem,
    TestCaseCategory,
)
from app.services.execution_service import ExecutionService
from app.services.test_case_generation_service import TestCaseGenerationService
from app.testing.contract import TestCaseSnapshot
from app.testing.evidence_manager import EvidenceManager
from app.testing.playwright_runner import PlaywrightWebRunner


def test_url_utils_validation_and_normalization() -> None:
    # Valid URLs
    assert validate_and_normalize_url("https://example.com/login") == "https://example.com/login"
    assert validate_and_normalize_url("http://app.internal:8080/") == "http://app.internal:8080/"
    assert validate_and_normalize_url("https://example.com") == "https://example.com/"

    # Scheme restrictions
    with pytest.raises(ValueError, match="Only HTTP and HTTPS"):
        validate_and_normalize_url("javascript:alert(1)")
    with pytest.raises(ValueError, match="Only HTTP and HTTPS"):
        validate_and_normalize_url("file:///etc/passwd")

    # SSRF Blocklist
    with pytest.raises(ValueError, match="SSRF"):
        validate_and_normalize_url("http://169.254.169.254/latest/meta-data")
    with pytest.raises(ValueError, match="SSRF"):
        validate_and_normalize_url("http://metadata.google.internal/computeMetadata/v1")
    with pytest.raises(ValueError, match="SSRF"):
        validate_and_normalize_url("http://169.254.10.20/secret")


def test_extract_target_url_from_text() -> None:
    text_with_url = "Please verify the login flow on https://example.com/portal/login with standard test user."
    assert extract_target_url(text_with_url) == "https://example.com/portal/login"

    text_without_url = "Verify button is clickable and validates username input."
    assert extract_target_url(text_without_url) is None


def test_resolve_navigation_url() -> None:
    base = "https://example.com/app"

    # Relative to root
    assert resolve_navigation_url("/", base_url=base) == "https://example.com/app"
    # Relative path
    assert resolve_navigation_url("/dashboard", base_url=base) == "https://example.com/dashboard"
    assert resolve_navigation_url("subpath", base_url=base) == "https://example.com/app/subpath"

    # Absolute URL ignores base
    assert resolve_navigation_url("https://other-domain.com/page", base_url=base) == "https://other-domain.com/page"

    # Missing base URL with relative step must raise clear error
    with pytest.raises(ValueError, match="Target URL is missing or undefined"):
        resolve_navigation_url("/", base_url=None)

    with pytest.raises(ValueError, match="Target URL is missing or undefined"):
        resolve_navigation_url("/login", base_url="")


def test_requirement_creation_persists_explicit_and_extracted_target_url(
    client: TestClient, db_session: Session
) -> None:
    # 1. Project creation
    proj_res = client.post("/api/v1/projects", json={"name": "URL Test Project"})
    assert proj_res.status_code == 201
    proj_id = proj_res.json()["id"]

    # 2. Explicit target_url
    req1_res = client.post(
        f"/api/v1/projects/{proj_id}/requirements",
        json={
            "title": "Req with explicit URL",
            "description": "User login portal",
            "target_url": "https://example.com/login",
            "acceptance_criteria": ["Login succeeds"],
        },
    )
    assert req1_res.status_code == 201
    assert req1_res.json()["target_url"] == "https://example.com/login"

    # 3. Extracted target_url from description
    req2_res = client.post(
        f"/api/v1/projects/{proj_id}/requirements",
        json={
            "title": "Req with embedded URL",
            "description": "Check application dashboard at https://dashboard.example.com/home page.",
            "acceptance_criteria": ["Dashboard loads"],
        },
    )
    assert req2_res.status_code == 201
    assert req2_res.json()["target_url"] == "https://dashboard.example.com/home"

    # 4. Invalid target_url (SSRF)
    bad_req = client.post(
        f"/api/v1/projects/{proj_id}/requirements",
        json={
            "title": "SSRF Req",
            "description": "Evil metadata access",
            "target_url": "http://169.254.169.254/latest",
        },
    )
    assert bad_req.status_code == 422


class MockGenerationProvider:
    provider_name = "mock"
    model_name = "mock-model"

    def generate(self, requirement: Requirement) -> GeneratedTestCaseCollection:
        return GeneratedTestCaseCollection(
            test_cases=[
                GeneratedTestCaseItem(
                    title="Positive Login Flow",
                    description="Verify user can log into the target portal.",
                    category=TestCaseCategory.POSITIVE,
                    test_type=TestType.WEB,
                    priority=Priority.HIGH,
                    preconditions=["Target site is reachable"],
                    steps=[
                        GeneratedStep(action="Navigate to login", data={"action": "navigate", "url": "/login"}),
                        GeneratedStep(action="Click submit", data={"action": "click", "selector": "#submit"}),
                    ],
                    expected_result="User is logged in",
                )
            ],
            requirement_coverage_summary="Covered positive login flow",
            assumptions=["Target site is online"],
        )


def test_test_case_generation_persists_target_url_from_requirement(
    db_session: Session,
) -> None:
    project = Project(id=uuid4(), name="Generation Target URL Project")
    db_session.add(project)
    db_session.commit()

    requirement = Requirement(
        id=uuid4(),
        project_id=project.id,
        title="Web Requirement",
        description="Portal auth",
        target_url="https://auth.example.com",
        acceptance_criteria=["Auth works"],
    )
    db_session.add(requirement)
    db_session.commit()

    service = TestCaseGenerationService(db=db_session, provider=MockGenerationProvider())
    response = service.generate_for_requirement(project.id, requirement.id)

    assert response.total_generated == 1
    assert len(response.items) == 1
    generated_tc = response.items[0]
    assert generated_tc.target_url == "https://auth.example.com"

    # Verify database persistence
    tc_row = db_session.get(TestCase, generated_tc.id)
    assert tc_row is not None
    assert tc_row.target_url == "https://auth.example.com"


def test_playwright_navigates_to_intended_target_url_not_localhost() -> None:
    settings = get_settings()
    evidence_mgr = EvidenceManager(settings)
    runner = PlaywrightWebRunner(settings=settings, evidence_manager=evidence_mgr)

    tc = TestCase(
        id=uuid4(),
        title="Live Target URL Test",
        expected_result="Page loaded",
        test_type=TestType.WEB,
        target_url="https://example.com/checkout",
        steps=[
            {"action": "Navigate to checkout", "expected_result": "Checkout loaded", "data": {"action": "navigate", "url": "/checkout"}},
        ],
    )

    mock_page = MagicMock()
    mock_page.url = "https://example.com/checkout"
    mock_page.screenshot.return_value = b"\x89PNG\r\n\x1a\nfakeimage"
    mock_browser = MagicMock()
    mock_context = MagicMock()
    mock_context.new_page.return_value = mock_page
    mock_browser.new_context.return_value = mock_context

    mock_pw = MagicMock()
    mock_pw.chromium.launch.return_value = mock_browser

    with patch("app.testing.playwright_runner.sync_playwright") as mock_sync_pw:
        mock_sync_pw.return_value.__enter__.return_value = mock_pw
        outcome = runner.execute(tc, execution_id=uuid4())

    assert outcome.status == ExecutionStatus.PASSED
    # Verify page.goto was called with intended URL, NOT http://localhost:5173/
    called_url = mock_page.goto.call_args[0][0]
    assert called_url == "https://example.com/checkout"
    assert "localhost:5173" not in called_url


def test_missing_target_url_produces_clear_error_instead_of_silent_localhost_navigation() -> None:
    settings = get_settings()
    evidence_mgr = EvidenceManager(settings)
    runner = PlaywrightWebRunner(settings=settings, evidence_manager=evidence_mgr)

    tc = TestCase(
        id=uuid4(),
        title="Unspecified Target URL Test",
        expected_result="Should fail clearly",
        test_type=TestType.WEB,
        target_url=None,  # No target URL configured
        steps=[
            {"action": "Navigate to home", "expected_result": "Home loaded", "data": {"action": "navigate", "url": "/"}},
        ],
    )

    mock_page = MagicMock()
    mock_page.screenshot.return_value = b"\x89PNG\r\n\x1a\nfakeimage"
    mock_browser = MagicMock()
    mock_context = MagicMock()
    mock_context.new_page.return_value = mock_page
    mock_browser.new_context.return_value = mock_context

    mock_pw = MagicMock()
    mock_pw.chromium.launch.return_value = mock_browser

    with patch("app.testing.playwright_runner.sync_playwright") as mock_sync_pw:
        mock_sync_pw.return_value.__enter__.return_value = mock_pw
        outcome = runner.execute(tc, execution_id=uuid4())

    assert outcome.status == ExecutionStatus.FAILED
    assert outcome.error_message is not None
    assert "Target URL is missing or undefined" in outcome.error_message
    # Verify Playwright never attempted to navigate to localhost:5173
    mock_page.goto.assert_not_called()


def test_end_to_end_execution_flow_with_target_url(
    client: TestClient, db_session: Session
) -> None:
    proj = client.post("/api/v1/projects", json={"name": "E2E URL Target Project"}).json()
    req = client.post(
        f"/api/v1/projects/{proj['id']}/requirements",
        json={
            "title": "E2E Req",
            "description": "Target web app testing",
            "target_url": "https://app.targetsite.com/portal",
        },
    ).json()

    tc = client.post(
        f"/api/v1/projects/{proj['id']}/test-cases",
        json={
            "requirement_id": req["id"],
            "title": "Target Site Web Case",
            "expected_result": "Page loaded",
            "test_type": "web",
            "target_url": req["target_url"],
            "steps": [{"action": "Navigate", "expected_result": "Loaded", "data": {"action": "navigate", "url": "/portal"}}],
        },
    ).json()

    # Approve test case
    client.patch(
        f"/api/v1/projects/{proj['id']}/test-cases/{tc['id']}",
        json={"review_status": ReviewStatus.APPROVED.value, "status": TestCaseStatus.APPROVED.value},
    )

    mock_page = MagicMock()
    mock_page.url = "https://app.targetsite.com/portal"
    mock_page.screenshot.return_value = b"\x89PNG\r\n\x1a\nfakeimage"
    mock_browser = MagicMock()
    mock_context = MagicMock()
    mock_context.new_page.return_value = mock_page
    mock_browser.new_context.return_value = mock_context
    mock_pw = MagicMock()
    mock_pw.chromium.launch.return_value = mock_browser

    with patch("app.testing.playwright_runner.sync_playwright") as mock_sync_pw:
        mock_sync_pw.return_value.__enter__.return_value = mock_pw
        exec_res = client.post(f"/api/v1/projects/{proj['id']}/test-cases/{tc['id']}/execute")

    assert exec_res.status_code == 201
    exec_id = exec_res.json()["id"]

    # Verify execution detail snapshot includes target_url
    detail_res = client.get(f"/api/v1/projects/{proj['id']}/executions/{exec_id}/detail")
    assert detail_res.status_code == 200
    snapshot = detail_res.json()["test_case_snapshot"]
    assert snapshot["target_url"] == "https://app.targetsite.com/portal"
    assert "localhost:5173" not in snapshot["target_url"]


def test_ssrf_ipv6_and_redirect_interception() -> None:
    # IPv6 Cloud Metadata
    blocked, reason = is_blocked_host("fd00:ec2::254")
    assert blocked is True
    assert "SSRF" in reason

    # IPv6 Link-Local
    blocked, reason = is_blocked_host("fe80::1")
    assert blocked is True
    assert "link-local" in reason

    # Zero address
    blocked, _ = is_blocked_host("0.0.0.0")
    assert blocked is True

    # Cloud IPv4 metadata
    blocked, _ = is_blocked_host("169.254.169.254")
    assert blocked is True

    # Legitimate domains and authorized local test destinations remain allowed
    blocked, _ = is_blocked_host("example.com")
    assert blocked is False
    blocked, _ = is_blocked_host("localhost")
    assert blocked is False
    blocked, _ = is_blocked_host("127.0.0.1")
    assert blocked is False

    # Verify Playwright context installs route guard
    settings = get_settings()
    evidence_mgr = EvidenceManager(settings)
    runner = PlaywrightWebRunner(settings=settings, evidence_manager=evidence_mgr)

    tc = TestCase(
        id=uuid4(),
        title="SSRF Route Guard Test",
        expected_result="Aborted",
        test_type=TestType.WEB,
        target_url="https://example.com",
        steps=[{"action": "Navigate", "expected_result": "Loaded", "data": {"action": "navigate", "url": "/"}}],
    )

    mock_page = MagicMock()
    mock_browser = MagicMock()
    mock_context = MagicMock()
    mock_context.new_page.return_value = mock_page
    mock_browser.new_context.return_value = mock_context
    mock_pw = MagicMock()
    mock_pw.chromium.launch.return_value = mock_browser

    with patch("app.testing.playwright_runner.sync_playwright") as mock_sync_pw:
        mock_sync_pw.return_value.__enter__.return_value = mock_pw
        runner.execute(tc, execution_id=uuid4())

    # Ensure context.route was called with "**/*"
    mock_context.route.assert_called_once()
    route_pattern, interceptor = mock_context.route.call_args[0]
    assert route_pattern == "**/*"

    # Test that interceptor aborts blocked destinations
    mock_route_blocked = MagicMock()
    mock_route_blocked.request.url = "http://169.254.169.254/latest/meta-data"
    interceptor(mock_route_blocked)
    mock_route_blocked.abort.assert_called_once_with("blockedbyclient")

    # Test that interceptor permits safe destinations
    mock_route_safe = MagicMock()
    mock_route_safe.request.url = "https://example.com/assets/app.js"
    interceptor(mock_route_safe)
    mock_route_safe.continue_.assert_called_once()

