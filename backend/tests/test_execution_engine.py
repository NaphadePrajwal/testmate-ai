from pathlib import Path
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.enums import ReviewStatus, TestCaseStatus, TestType
from app.models.requirement import Requirement
from app.models.test_case import TestCase
from app.models.test_execution import TestExecution
from app.testing.contract import ExecutionOutcome, StepExecutionResult
from app.testing.evidence_manager import EvidenceManager
from app.testing.httpx_runner import HttpxApiRunner
from app.testing.playwright_runner import PlaywrightWebRunner
from app.testing.pytest_runner import PytestRunner


def create_project(client: TestClient, name: str = "Execution Test Project") -> dict:
    res = client.post("/api/v1/projects", json={"name": name, "description": "Phase 5 testing"})
    assert res.status_code == 201
    return res.json()


def create_requirement(client: TestClient, project_id: str, title: str = "Test Execution Req") -> dict:
    res = client.post(
        f"/api/v1/projects/{project_id}/requirements",
        json={"title": title, "description": "Requirement for execution engine testing", "acceptance_criteria": ["Criteria 1"]},
    )
    assert res.status_code == 201
    return res.json()


def create_test_case(
    client: TestClient,
    project_id: str,
    requirement_id: str,
    title: str = "Sample TestCase",
    test_type: str = "manual",
    steps: list | None = None,
) -> dict:
    res = client.post(
        f"/api/v1/projects/{project_id}/test-cases",
        json={
            "requirement_id": requirement_id,
            "title": title,
            "expected_result": "Expected outcome verified.",
            "test_type": test_type,
            "steps": steps or [{"action": "Verify initial state", "expected_result": "Initial state is valid", "data": {}}],
        },
    )
    assert res.status_code == 201
    return res.json()


def test_approval_guard_rejects_pending_and_rejected_test_cases(client: TestClient) -> None:
    proj = create_project(client)
    req = create_requirement(client, proj["id"])
    tc = create_test_case(client, proj["id"], req["id"], title="Pending Test Case")

    # Initial state is pending/draft
    exec_res = client.post(f"/api/v1/projects/{proj['id']}/test-cases/{tc['id']}/execute")
    assert exec_res.status_code == 409
    assert "Only approved test cases are eligible for execution" in exec_res.json()["detail"]

    # Update to rejected
    patch_res = client.patch(
        f"/api/v1/projects/{proj['id']}/test-cases/{tc['id']}",
        json={"review_status": ReviewStatus.REJECTED.value},
    )
    assert patch_res.status_code == 200

    exec_res2 = client.post(f"/api/v1/projects/{proj['id']}/test-cases/{tc['id']}/execute")
    assert exec_res2.status_code == 409
    assert "Only approved test cases are eligible for execution" in exec_res2.json()["detail"]


def test_execution_of_approved_manual_test_case(client: TestClient) -> None:
    proj = create_project(client)
    req = create_requirement(client, proj["id"])
    tc = create_test_case(
        client,
        proj["id"],
        req["id"],
        title="Approved Manual Test",
        test_type="manual",
        steps=[
            {"action": "Check system health", "expected_result": "Health is OK", "data": {}},
            {"action": "Verify auth config", "expected_result": "Auth configured", "data": {}},
        ],
    )

    # Approve test case
    client.patch(
        f"/api/v1/projects/{proj['id']}/test-cases/{tc['id']}",
        json={"review_status": ReviewStatus.APPROVED.value, "status": TestCaseStatus.APPROVED.value},
    )

    # Trigger execution
    exec_res = client.post(f"/api/v1/projects/{proj['id']}/test-cases/{tc['id']}/execute")
    assert exec_res.status_code == 201
    data = exec_res.json()
    assert data["status"] == "passed"
    assert data["test_case_id"] == tc["id"]
    assert data["summary"]["total_steps"] == 2
    assert data["summary"]["passed_steps"] == 2
    assert data["summary"]["failed_steps"] == 0

    # Verify execution list
    list_res = client.get(f"/api/v1/projects/{proj['id']}/executions")
    assert list_res.status_code == 200
    assert list_res.json()["total"] >= 1


def test_execution_failure_creates_defect_and_evidence(client: TestClient) -> None:
    proj = create_project(client)
    req = create_requirement(client, proj["id"])
    tc = create_test_case(
        client,
        proj["id"],
        req["id"],
        title="Failing Manual Test",
        test_type="manual",
        steps=[
            {"action": "Step 1", "expected_result": "Success", "data": {}},
            {"action": "Step 2", "expected_result": "Will fail", "data": {"simulate_failure": True, "error_message": "Network timeout simulated"}},
        ],
    )

    # Approve
    client.patch(
        f"/api/v1/projects/{proj['id']}/test-cases/{tc['id']}",
        json={"review_status": ReviewStatus.APPROVED.value, "status": TestCaseStatus.APPROVED.value},
    )

    exec_res = client.post(f"/api/v1/projects/{proj['id']}/test-cases/{tc['id']}/execute")
    assert exec_res.status_code == 201
    data = exec_res.json()
    assert data["status"] == "failed"
    assert data["error_message"] == "Network timeout simulated"
    assert data["summary"]["failed_steps"] == 1

    # Verify defect was logged
    defect_res = client.get(f"/api/v1/projects/{proj['id']}/defects")
    assert defect_res.status_code == 200
    defects = defect_res.json()["items"]
    assert len(defects) >= 1
    assert "Failing Manual Test" in defects[0]["title"]

    # Verify evidence (logs)
    evidence_res = client.get(f"/api/v1/projects/{proj['id']}/executions/{data['id']}/evidence")
    assert evidence_res.status_code == 200
    evidence_items = evidence_res.json()["items"]
    assert len(evidence_items) >= 1
    assert evidence_items[0]["evidence_type"] == "log"


def test_httpx_api_runner_success(client: TestClient) -> None:
    settings = get_settings()
    evidence_mgr = EvidenceManager(settings)
    runner = HttpxApiRunner(settings, evidence_mgr)

    tc = TestCase(
        title="Health Check Test",
        expected_result="HTTP 200 OK",
        test_type=TestType.API,
        steps=[
            {
                "action": "GET /api/v1/health",
                "expected_result": "Returns 200",
                "data": {"method": "GET", "url": f"{settings.target_api_url}/health", "expected_status": 200},
            }
        ],
    )

    # Mock the client request inside HttpxApiRunner to avoid requiring live dev server
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.reason_phrase = "OK"
    mock_response.headers = {"Content-Type": "application/json"}
    mock_response.json.return_value = {"status": "ok"}
    mock_response.request.headers = {"User-Agent": "TestMate-HTTPX"}

    with patch("httpx.Client.request", return_value=mock_response):
        outcome = runner.execute(tc, execution_id=uuid4())

    assert outcome.status.value == "passed"
    assert len(outcome.step_results) == 1
    assert outcome.step_results[0].status == "passed"
    assert len(outcome.evidence_items) == 1
    assert outcome.evidence_items[0].evidence_type.value == "request_response"


def test_httpx_api_runner_ssrf_protection() -> None:
    settings = get_settings()
    evidence_mgr = EvidenceManager(settings)
    runner = HttpxApiRunner(settings, evidence_mgr)

    tc = TestCase(
        title="SSRF Attack Case",
        expected_result="Blocked",
        test_type=TestType.API,
        steps=[
            {
                "action": "GET metadata service",
                "expected_result": "200",
                "data": {"method": "GET", "url": "http://169.254.169.254/latest/meta-data", "expected_status": 200},
            }
        ],
    )

    outcome = runner.execute(tc, execution_id=uuid4())
    assert outcome.status.value == "error"
    assert "SSRF" in outcome.error_message


def test_playwright_runner_mock_flow() -> None:
    settings = get_settings()
    evidence_mgr = EvidenceManager(settings)
    runner = PlaywrightWebRunner(settings, evidence_mgr)

    tc = TestCase(
        title="Web Navigation Test",
        expected_result="Page loaded",
        test_type=TestType.WEB,
        target_url="http://localhost:5173",
        steps=[
            {"action": "Navigate to home", "expected_result": "Home displayed", "data": {"action": "navigate", "url": "/"}},
            {"action": "Check title visible", "expected_result": "Title is visible", "data": {"action": "assert_visible", "selector": "body"}},
        ],
    )

    # Verify execution outcome model formatting with mock
    mock_page = MagicMock()
    mock_page.url = "http://localhost:5173/"
    mock_page.content.return_value = "<html><body><h1>TestMate</h1></body></html>"
    mock_page.screenshot.return_value = b"\x89PNG\r\n\x1a\nfakeimagebytes"
    mock_locator = MagicMock()
    mock_locator.first.is_visible.return_value = True
    mock_page.locator.return_value = mock_locator

    mock_browser = MagicMock()
    mock_context = MagicMock()
    mock_context.new_page.return_value = mock_page
    mock_browser.new_context.return_value = mock_context

    mock_pw = MagicMock()
    mock_pw.chromium.launch.return_value = mock_browser

    with patch("app.testing.playwright_runner.sync_playwright") as mock_sync_pw:
        mock_sync_pw.return_value.__enter__.return_value = mock_pw
        outcome = runner.execute(tc, execution_id=uuid4())

    assert outcome.status.value == "passed"
    assert len(outcome.step_results) == 2
    assert len(outcome.evidence_items) >= 1
    assert outcome.evidence_items[0].evidence_type.value == "screenshot"


def test_evidence_download_endpoint(client: TestClient) -> None:
    proj = create_project(client)
    req = create_requirement(client, proj["id"])
    tc = create_test_case(client, proj["id"], req["id"], title="Evidence Download Test")

    # Approve
    client.patch(
        f"/api/v1/projects/{proj['id']}/test-cases/{tc['id']}",
        json={"review_status": ReviewStatus.APPROVED.value, "status": TestCaseStatus.APPROVED.value},
    )

    exec_res = client.post(f"/api/v1/projects/{proj['id']}/test-cases/{tc['id']}/execute")
    exec_id = exec_res.json()["id"]

    ev_list_res = client.get(f"/api/v1/projects/{proj['id']}/executions/{exec_id}/evidence")
    evidence_id = ev_list_res.json()["items"][0]["id"]

    download_res = client.get(f"/api/v1/projects/{proj['id']}/executions/{exec_id}/evidence/{evidence_id}/download")
    assert download_res.status_code == 200
    assert len(download_res.content) > 0


def test_cross_project_isolation(client: TestClient) -> None:
    proj1 = create_project(client, name="Project Alpha")
    proj2 = create_project(client, name="Project Beta")
    req = create_requirement(client, proj1["id"])
    tc = create_test_case(client, proj1["id"], req["id"], title="Isolated Case")

    # Approve
    client.patch(
        f"/api/v1/projects/{proj1['id']}/test-cases/{tc['id']}",
        json={"review_status": ReviewStatus.APPROVED.value, "status": TestCaseStatus.APPROVED.value},
    )

    # Attempt execute under proj2
    cross_res = client.post(f"/api/v1/projects/{proj2['id']}/test-cases/{tc['id']}/execute")
    assert cross_res.status_code == 404


def test_playwright_live_browser_execution() -> None:
    settings = get_settings()
    evidence_mgr = EvidenceManager(settings)
    runner = PlaywrightWebRunner(settings, evidence_mgr)

    html_content = "data:text/html,<html><body><h1 id='title'>TestMate Playwright Live</h1><button id='btn'>Click Me</button></body></html>"

    tc = TestCase(
        title="Live Playwright Web Test",
        expected_result="Button clicked",
        test_type=TestType.WEB,
        steps=[
            {
                "action": "Navigate to HTML page",
                "expected_result": "Page loaded",
                "data": {"action": "navigate", "url": html_content},
            },
            {
                "action": "Assert title visible",
                "expected_result": "Title is visible",
                "data": {"action": "assert_visible", "selector": "#title"},
            },
            {
                "action": "Click button",
                "expected_result": "Button clicked",
                "data": {"action": "click", "selector": "#btn"},
            },
        ],
    )

    outcome = runner.execute(tc, execution_id=uuid4())
    assert outcome.status.value == "passed"
    assert len(outcome.step_results) == 3
    assert all(s.status == "passed" for s in outcome.step_results)
    assert len(outcome.evidence_items) >= 1
    assert outcome.evidence_items[0].evidence_type.value == "screenshot"

