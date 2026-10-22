from datetime import datetime, timezone
import os
from unittest.mock import MagicMock, patch
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.exceptions import ResourceConflictError, ResourceNotFoundError
from app.core.url_utils import is_blocked_host, resolve_navigation_url, validate_and_normalize_url
from app.models.enums import (
    DefectStatus,
    EvidenceType,
    ExecutionStatus,
    Priority,
    ReviewStatus,
    Severity,
    TestCaseStatus,
    TestType,
    WorkflowApprovalAction,
    WorkflowStatus,
)
from app.models.project import Project
from app.models.requirement import Requirement
from app.models.test_case import TestCase
from app.models.test_execution import TestExecution
from app.services.execution_service import ExecutionService
from app.testing.contract import ErrorCategory
from app.testing.evidence_manager import EvidenceManager
from app.testing.playwright_runner import PlaywrightWebRunner


# ==============================================================================
# SECTION 1: Unit Tests — URL Validation & SSRF Defenses (Part E1, K1)
# ==============================================================================


def test_url_validation_valid_http_https() -> None:
    """Verifies that standard HTTP and HTTPS URLs are valid and normalized."""
    assert validate_and_normalize_url("https://example.com/checkout") == "https://example.com/checkout"
    assert validate_and_normalize_url("http://127.0.0.1:8000/api/v1/demo/storefront") == "http://127.0.0.1:8000/api/v1/demo/storefront"
    assert validate_and_normalize_url("http://localhost:5173") == "http://localhost:5173/"


def test_url_validation_rejects_embedded_credentials() -> None:
    """Verifies that URLs with embedded user credentials (user:pass@host) are strictly rejected."""
    with pytest.raises(ValueError, match="embedded user credentials"):
        validate_and_normalize_url("https://admin:secret123@example.com/admin")

    with pytest.raises(ValueError, match="embedded user credentials"):
        validate_and_normalize_url("http://user@localhost:8000/api")


def test_url_validation_rejects_blocked_ssrf_hosts() -> None:
    """Verifies that cloud metadata and link-local addresses are rejected to prevent SSRF."""
    blocked_hosts = [
        "169.254.169.254",
        "metadata.google.internal",
        "instance-data",
        "0.0.0.0",
    ]
    for host in blocked_hosts:
        is_blocked, reason = is_blocked_host(host)
        assert is_blocked is True
        assert "prevent SSRF" in reason

        with pytest.raises(ValueError, match="prevent SSRF"):
            validate_and_normalize_url(f"http://{host}/latest/meta-data/")


def test_url_validation_rejects_invalid_schemes() -> None:
    """Verifies that non-HTTP(S) schemes like javascript:, file:, data: are rejected."""
    invalid_urls = [
        "javascript:alert(1)",
        "file:///etc/passwd",
        "gopher://example.com",
        "ftp://example.com/file",
    ]
    for url in invalid_urls:
        with pytest.raises(ValueError, match="Invalid URL scheme"):
            validate_and_normalize_url(url)


def test_resolve_navigation_url_relative_and_absolute() -> None:
    """Verifies relative URL resolution against the configured base target URL."""
    base = "http://127.0.0.1:8000/app"
    # Relative path
    assert resolve_navigation_url("/checkout", base) == "http://127.0.0.1:8000/checkout"
    assert resolve_navigation_url("cart", base) == "http://127.0.0.1:8000/app/cart"

    # Absolute URL overrides base
    assert resolve_navigation_url("http://localhost:3000/page", base) == "http://localhost:3000/page"

    # Relative navigation without base URL raises clear error
    with pytest.raises(ValueError, match="Target URL is missing or undefined"):
        resolve_navigation_url("/checkout", None)


# ==============================================================================
# SECTION 2: Unit Tests — Playwright Step Parsing & Accessible Locators (Part D2, K1)
# ==============================================================================


def test_playwright_runner_parse_structured_data() -> None:
    """Verifies parsing of pre-structured step data with accessible locators."""
    runner = PlaywrightWebRunner()

    step_role = {
        "action": "Click submit",
        "data": {"action": "click", "role": "button", "name": "Place Order"},
    }
    action, params = runner._parse_step(step_role)
    assert action == "click"
    assert params["role"] == "button"
    assert params["name"] == "Place Order"

    step_fill = {
        "action": "Fill card number",
        "data": {"action": "fill", "label": "Card Number", "value": "4242 4242 4242 4242"},
    }
    action, params = runner._parse_step(step_fill)
    assert action == "fill"
    assert params["label"] == "Card Number"
    assert params["value"] == "4242 4242 4242 4242"


def test_playwright_runner_parse_natural_language_actions() -> None:
    """Verifies regex extraction when steps are described in natural language."""
    runner = PlaywrightWebRunner()

    # Navigate
    act, p = runner._parse_step({"action": "Navigate to 'http://localhost:8000/demo/storefront'"})
    assert act == "navigate"
    assert "http://localhost:8000/demo/storefront" in p["url"]

    # Click button
    act, p = runner._parse_step({"action": "Click the 'Submit Order' button"})
    assert act == "click"
    assert p["name"] == "Submit Order"

    # Fill
    act, p = runner._parse_step({"action": "Fill 'Cardholder Name' with 'Alice Smith'"})
    assert act == "fill"
    assert p["label"] == "Cardholder Name"
    assert p["value"] == "Alice Smith"

    # Check
    act, p = runner._parse_step({"action": "Check 'I agree to terms'"})
    assert act == "check"
    assert p["label"] == "I agree to terms"

    # Assert Title
    act, p = runner._parse_step({"action": "Assert title contains 'Demo Storefront'"})
    assert act == "assert_title"
    assert p["title"] == "Demo Storefront"

    # Assert Text
    act, p = runner._parse_step({"action": "Assert text 'Order Confirmed!'"})
    assert act == "assert_text"
    assert p["text"] == "Order Confirmed!"


# ==============================================================================
# SECTION 3: Integration Tests — Execution Persistence & Safety (Part B5, K2)
# ==============================================================================


def create_sample_web_test_case(db: Session, target_url: str = "http://127.0.0.1:8000/api/v1/demo/storefront") -> tuple[Project, TestCase]:
    proj = Project(name=f"Browser Test Project {uuid4().hex[:6]}", description="Phase 10 Playwright tests")
    db.add(proj)
    db.commit()
    db.refresh(proj)

    req = Requirement(
        project_id=proj.id,
        title="E-Commerce Storefront Checkout Flow",
        description="Verify adding items to cart and placing an order securely.",
        acceptance_criteria=["User adds product to cart", "User submits payment", "Confirmation displayed"],
        target_url=target_url,
    )
    db.add(req)
    db.commit()
    db.refresh(req)

    tc = TestCase(
        requirement_id=req.id,
        title="E2E Checkout - Positive Purchase",
        description="Purchases Autonomous Test Runner Pro from local storefront.",
        test_type=TestType.WEB,
        priority=Priority.HIGH,
        status=TestCaseStatus.APPROVED,
        review_status=ReviewStatus.APPROVED,
        target_url=target_url,
        preconditions=["Storefront is online"],
        expected_result="Order Confirmed! message is displayed",
        steps=[
            {"action": "Navigate to storefront", "data": {"action": "navigate", "url": "/"}},
            {"action": "Click Add to Cart", "data": {"action": "click", "role": "button", "name": "Add to Cart"}},
            {"action": "Fill cardholder name", "data": {"action": "fill", "label": "Cardholder Name", "value": "Jane Tester"}},
            {"action": "Fill card number", "data": {"action": "fill", "label": "Card Number", "value": "4242 4242 4242 4242"}},
            {"action": "Submit order", "data": {"action": "click", "role": "button", "name": "Place Order"}},
            {"action": "Verify confirmation", "data": {"action": "assert_text", "text": "Order Confirmed!"}},
        ],
    )
    db.add(tc)
    db.commit()
    db.refresh(tc)
    return proj, tc


def test_unapproved_test_case_execution_rejected(db_session: Session) -> None:
    """Verifies that an unapproved test case cannot be executed, raising ResourceConflictError."""
    proj, tc = create_sample_web_test_case(db_session)

    # Set to pending review
    tc.status = TestCaseStatus.DRAFT
    tc.review_status = ReviewStatus.PENDING
    db_session.commit()

    exec_svc = ExecutionService(db_session)
    with pytest.raises(ResourceConflictError, match="Only approved test cases are eligible"):
        exec_svc.execute_test_case(project_id=proj.id, test_case_id=tc.id)


def test_execution_persistence_and_detail(db_session: Session) -> None:
    """Verifies that test execution, step results, snapshot, and duration are persisted in PostgreSQL."""
    proj, tc = create_sample_web_test_case(db_session)
    exec_svc = ExecutionService(db_session)

    # Execute with mock runner to test database persistence layer deterministically
    mock_runner = MagicMock()
    mock_outcome = MagicMock()
    mock_outcome.status = ExecutionStatus.PASSED
    mock_outcome.completed_at = datetime.now(timezone.utc)
    mock_outcome.error_message = None
    mock_outcome.summary_dict = {
        "total_steps": 6,
        "passed_steps": 6,
        "failed_steps": 0,
        "duration_ms": 350.5,
        "error_category": None,
        "step_results": [{"step_index": 1, "action": "Navigate to storefront", "status": "passed"}],
    }
    mock_outcome.evidence_items = []
    mock_runner.execute.return_value = mock_outcome

    with patch("app.services.execution_service.PlaywrightWebRunner", return_value=mock_runner):
        execution = exec_svc.execute_test_case(project_id=proj.id, test_case_id=tc.id)

    assert execution.id is not None
    assert execution.status == ExecutionStatus.PASSED
    assert execution.test_case_id == tc.id
    assert execution.summary["passed_steps"] == 6

    # Verify retrieval via detail endpoint
    detail = exec_svc.get_execution_detail(project_id=proj.id, execution_id=execution.id)
    assert detail.id == execution.id
    assert detail.test_case_id == tc.id
    assert detail.status == ExecutionStatus.PASSED


def test_cross_project_execution_isolation(db_session: Session) -> None:
    """Verifies that execution records cannot be accessed across different projects."""
    proj1, tc1 = create_sample_web_test_case(db_session)

    proj2 = Project(name="Isolated Project B", description="Another tenant project")
    db_session.add(proj2)
    db_session.commit()
    db_session.refresh(proj2)

    # Create dummy execution in proj1
    execution = TestExecution(
        id=uuid4(),
        test_case_id=tc1.id,
        status=ExecutionStatus.PASSED,
        executor="playwright",
        summary={},
    )
    db_session.add(execution)
    db_session.commit()

    exec_svc = ExecutionService(db_session)

    # Query under proj1 -> succeeds
    assert exec_svc.get_execution(project_id=proj1.id, execution_id=execution.id) is not None

    # Query under proj2 -> raises ResourceNotFoundError
    with pytest.raises(ResourceNotFoundError):
        exec_svc.get_execution(project_id=proj2.id, execution_id=execution.id)


# ==============================================================================
# SECTION 4: Live Playwright Browser Tests Against Local Storefront (Part J, K5)
# ==============================================================================


def test_live_playwright_e2e_positive_flow(client: TestClient, db_session: Session) -> None:
    """
    Executes a real headless Playwright browser test against the live demo storefront.
    Verifies:
    1. Navigation to storefront.
    2. Cart interaction ('Add to Cart' updates cart count).
    3. Input filling ('Cardholder Name', 'Card Number').
    4. Form submission.
    5. Success assertion ('Order Confirmed!').
    6. Screenshot evidence creation and persistence.
    """
    proj, tc = create_sample_web_test_case(db_session)
    exec_svc = ExecutionService(db_session)

    # Point to the live testclient URL for demo storefront
    # Notice: TestClient is in-process, but Playwright can reach the live backend on 127.0.0.1:8000
    tc.target_url = "http://127.0.0.1:8000/api/v1/demo/storefront"
    db_session.commit()

    # Execute test case with the real PlaywrightWebRunner
    execution = exec_svc.execute_test_case(project_id=proj.id, test_case_id=tc.id)

    assert execution.status == ExecutionStatus.PASSED
    assert execution.error_message is None
    summary = execution.summary
    assert summary["passed_steps"] == 6
    assert summary["failed_steps"] == 0
    assert summary["duration_ms"] > 0

    # Verify completion screenshot evidence was saved
    evidence_items = exec_svc.list_evidence(project_id=proj.id, execution_id=execution.id, limit=10, offset=0)[0]
    assert len(evidence_items) > 0
    screenshot_ev = next((ev for ev in evidence_items if ev.evidence_type == EvidenceType.SCREENSHOT), None)
    assert screenshot_ev is not None
    assert "screenshots/" in screenshot_ev.uri


def test_live_playwright_e2e_failure_and_defect_flow(db_session: Session) -> None:
    """
    Executes a deliberate failure scenario against the live demo storefront.
    Using card number '0000 0000 0000 0000' triggers payment failure.
    Verifies:
    1. Test execution reports FAILED.
    2. Error category is classified as 'assertion_failure'.
    3. Failure screenshot evidence is captured.
    4. A Defect record is automatically created in PostgreSQL.
    """
    proj, _ = create_sample_web_test_case(db_session)

    req = db_session.scalar(select(Requirement).where(Requirement.project_id == proj.id))

    # Create a test case that expects success, but provides a failing card
    failing_tc = TestCase(
        requirement_id=req.id,
        title="Deliberate Payment Failure Flow",
        description="Tests gateway rejection with declining card.",
        test_type=TestType.WEB,
        priority=Priority.HIGH,
        status=TestCaseStatus.APPROVED,
        review_status=ReviewStatus.APPROVED,
        target_url="http://127.0.0.1:8000/api/v1/demo/storefront",
        expected_result="Order Confirmed! message is displayed",
        steps=[
            {"action": "Navigate to storefront", "data": {"action": "navigate", "url": "/"}},
            {"action": "Fill cardholder name", "data": {"action": "fill", "label": "Cardholder Name", "value": "Declined User"}},
            {"action": "Fill failing card", "data": {"action": "fill", "label": "Card Number", "value": "0000 0000 0000 0000"}},
            {"action": "Submit order", "data": {"action": "click", "role": "button", "name": "Place Order"}},
            {"action": "Verify confirmation", "data": {"action": "assert_text", "text": "Order Confirmed!"}},
        ],
    )
    db_session.add(failing_tc)
    db_session.commit()
    db_session.refresh(failing_tc)

    exec_svc = ExecutionService(db_session)
    execution = exec_svc.execute_test_case(project_id=proj.id, test_case_id=failing_tc.id)

    assert execution.status == ExecutionStatus.FAILED
    assert "Expected text 'Order Confirmed!' not found" in (execution.error_message or "")
    assert execution.summary["error_category"] == ErrorCategory.ASSERTION_FAILURE.value
    assert execution.summary["failed_steps"] >= 1

    # Verify failure screenshot is attached
    evidence_items = exec_svc.list_evidence(project_id=proj.id, execution_id=execution.id, limit=10, offset=0)[0]
    assert any(ev.evidence_type == EvidenceType.SCREENSHOT for ev in evidence_items)

    # Verify Defect was automatically created
    defects = exec_svc.list_defects(project_id=proj.id, limit=10, offset=0, status=None, severity=None)[0]
    matching_defect = next((d for d in defects if d.execution_id == execution.id), None)
    assert matching_defect is not None
    assert matching_defect.status == DefectStatus.NEW
    assert matching_defect.severity == Severity.HIGH
    assert "Order Confirmed!" in matching_defect.description
