from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.enums import EvidenceType, ExecutionStatus, ReviewStatus, TestCaseStatus, TestType
from app.models.execution_evidence import ExecutionEvidence
from app.models.test_case import TestCase
from app.models.test_execution import TestExecution
from app.services.execution_service import ExecutionService
from app.testing.contract import ErrorCategory, ExecutionOutcome, StepExecutionResult, TestCaseSnapshot
from app.testing.evidence_manager import (
    EvidenceManager,
    sanitize_log_text,
    sanitize_sensitive_data,
    sanitize_url_string,
)


def create_project(client: TestClient, name: str = "Results Test Project") -> dict:
    res = client.post("/api/v1/projects", json={"name": name, "description": "Phase 6 testing"})
    assert res.status_code == 201
    return res.json()


def create_requirement(client: TestClient, project_id: str, title: str = "Results Req") -> dict:
    res = client.post(
        f"/api/v1/projects/{project_id}/requirements",
        json={"title": title, "description": "Requirement for results testing", "acceptance_criteria": ["Criteria 1"]},
    )
    assert res.status_code == 201
    return res.json()


def create_and_approve_test_case(
    client: TestClient,
    project_id: str,
    requirement_id: str,
    title: str = "Search Feature TestCase",
    test_type: str = "manual",
    steps: list | None = None,
) -> dict:
    steps_data = steps or [
        {"action": "Navigate to search", "expected_result": "Search page is visible", "data": {}},
        {"action": "Type query 'laptop'", "expected_result": "Query appears in box", "data": {"text": "laptop"}},
        {"action": "Click submit", "expected_result": "Search results display", "data": {}},
    ]

    res = client.post(
        f"/api/v1/projects/{project_id}/test-cases",
        json={
            "requirement_id": requirement_id,
            "title": title,
            "expected_result": "All search steps complete successfully.",
            "test_type": test_type,
            "steps": steps_data,
        },
    )
    assert res.status_code == 201
    tc = res.json()

    # Approve test case
    res_approve = client.patch(
        f"/api/v1/projects/{project_id}/test-cases/{tc['id']}",
        json={"review_status": ReviewStatus.APPROVED.value, "status": TestCaseStatus.APPROVED.value},
    )
    assert res_approve.status_code == 200
    return res_approve.json()



def test_secret_redaction_in_evidence_manager(tmp_path: Path) -> None:
    settings = get_settings()
    manager = EvidenceManager(settings)

    sensitive_dict = {
        "authorization": "Bearer secret_jwt_token_12345",
        "api_key": "sk-secret-live-key",
        "password": "MySuperSecretPassword!",
        "safe_key": "public_data",
        "nested": {
            "token": "sensitive_nested_token",
            "normal": 42,
        },
    }

    sanitized = sanitize_sensitive_data(sensitive_dict)
    assert sanitized["authorization"] == "[REDACTED]"
    assert sanitized["api_key"] == "[REDACTED]"
    assert sanitized["password"] == "[REDACTED]"
    assert sanitized["safe_key"] == "public_data"
    assert sanitized["nested"]["token"] == "[REDACTED]"
    assert sanitized["nested"]["normal"] == 42


def test_evidence_checksum_and_containment(tmp_path: Path) -> None:
    settings = get_settings()
    manager = EvidenceManager(settings)

    execution_id = uuid4()
    content = b"Sample diagnostic execution log line 1\nLine 2"
    sha256 = hashlib.sha256(content).hexdigest()

    item = manager.save_log(execution_id, content.decode("utf-8"), label="Runner Log")
    assert item.uri.endswith(".log")
    assert item.metadata["size_bytes"] == len(content)
    assert item.metadata["sha256"] == sha256


def test_execution_snapshot_immutability(client: TestClient, db_session: Session) -> None:
    """Historical execution snapshot must preserve exact test case state even after subsequent edits."""
    proj = create_project(client, "Snapshot Project")
    req = create_requirement(client, proj["id"])
    tc = create_and_approve_test_case(client, proj["id"], req["id"], title="Original Title v1")
    original_version = tc["version"]

    # Run execution 1
    exec1_res = client.post(f"/api/v1/projects/{proj['id']}/test-cases/{tc['id']}/execute")
    assert exec1_res.status_code == 201
    exec1_id = exec1_res.json()["id"]

    # Verify detail response has snapshot
    detail1_res = client.get(f"/api/v1/projects/{proj['id']}/executions/{exec1_id}/detail")
    assert detail1_res.status_code == 200
    detail1 = detail1_res.json()
    assert detail1["test_case_snapshot"]["title"] == "Original Title v1"
    assert detail1["test_case_snapshot"]["version"] == original_version
    assert detail1["test_case_snapshot"]["expected_result"] == "All search steps complete successfully."

    # Direct mutation of test case in DB (simulating subsequent updates or versioning)
    tc_row = db_session.get(TestCase, tc["id"])
    assert tc_row is not None
    tc_row.title = "Directly Mutated Title"
    tc_row.expected_result = "Directly mutated expected result"
    tc_row.version = 99
    db_session.commit()

    # Re-verify that execution 1 snapshot remains UNCHANGED
    detail1_after_edit = client.get(f"/api/v1/projects/{proj['id']}/executions/{exec1_id}/detail").json()
    assert detail1_after_edit["test_case_snapshot"]["title"] == "Original Title v1"
    assert detail1_after_edit["test_case_snapshot"]["version"] == original_version
    assert detail1_after_edit["test_case_snapshot"]["expected_result"] == "All search steps complete successfully."



def test_execution_summary_and_step_results(client: TestClient) -> None:
    """Execution summary must accurately reflect step counts, status, and failure info."""
    proj = create_project(client, "Summary Project")
    req = create_requirement(client, proj["id"])
    tc = create_and_approve_test_case(client, proj["id"], req["id"], title="Step Verification Test")

    exec_res = client.post(f"/api/v1/projects/{proj['id']}/test-cases/{tc['id']}/execute")
    assert exec_res.status_code == 201
    exec_id = exec_res.json()["id"]

    detail_res = client.get(f"/api/v1/projects/{proj['id']}/executions/{exec_id}/detail")
    assert detail_res.status_code == 200
    detail = detail_res.json()

    assert detail["status"] == ExecutionStatus.PASSED.value
    assert detail["summary"]["total_steps"] == 3
    assert detail["summary"]["passed_steps"] == 3
    assert detail["summary"]["failed_steps"] == 0
    assert detail["summary"]["skipped_steps"] == 0
    assert detail["summary"]["failed_step_index"] is None

    # Step results
    assert len(detail["step_results"]) == 3
    for step in detail["step_results"]:
        assert step["status"] == "passed"
        assert step["expected_result"] != ""
        assert step["actual_result"] != ""


def test_failure_analysis_context_contract(client: TestClient) -> None:
    """Stable Phase 7 data contract returns all required fields for AI analysis."""
    proj = create_project(client, "Analysis Context Project")
    req = create_requirement(client, proj["id"])
    tc = create_and_approve_test_case(client, proj["id"], req["id"], title="Analysis Target TC")

    exec_res = client.post(f"/api/v1/projects/{proj['id']}/test-cases/{tc['id']}/execute")
    assert exec_res.status_code == 201
    exec_id = exec_res.json()["id"]

    context_res = client.get(f"/api/v1/projects/{proj['id']}/executions/{exec_id}/analysis-context")
    assert context_res.status_code == 200
    context = context_res.json()

    assert context["execution_id"] == exec_id
    assert context["test_case_id"] == tc["id"]
    assert context["project_id"] == proj["id"]
    assert context["requirement_id"] == req["id"]
    assert context["status"] == ExecutionStatus.PASSED.value
    assert context["test_case_snapshot"]["title"] == "Analysis Target TC"
    assert len(context["step_results"]) == 3
    assert isinstance(context["logs"], list)


def test_evidence_download_security_and_containment(client: TestClient) -> None:
    """Evidence download enforces project scope, path containment, and 404 for missing files."""
    proj_a = create_project(client, "Project A")
    req_a = create_requirement(client, proj_a["id"])
    tc_a = create_and_approve_test_case(client, proj_a["id"], req_a["id"], title="TC A")

    proj_b = create_project(client, "Project B")

    # Execute TC in Project A
    exec_a = client.post(f"/api/v1/projects/{proj_a['id']}/test-cases/{tc_a['id']}/execute").json()

    # List evidence for exec_a
    ev_list_res = client.get(f"/api/v1/projects/{proj_a['id']}/executions/{exec_a['id']}/evidence")
    assert ev_list_res.status_code == 200
    evidence_items = ev_list_res.json()["items"]
    assert len(evidence_items) > 0
    ev_item = evidence_items[0]

    # Authorized download succeeds
    dl_res = client.get(f"/api/v1/projects/{proj_a['id']}/executions/{exec_a['id']}/evidence/{ev_item['id']}/download")
    assert dl_res.status_code == 200

    # Cross-project authorization check: requesting Project A's evidence from Project B fails with 404
    cross_res = client.get(f"/api/v1/projects/{proj_b['id']}/executions/{exec_a['id']}/evidence/{ev_item['id']}/download")
    assert cross_res.status_code == 404

    # Invalid execution ID fails with 404
    random_exec_id = str(uuid4())
    bad_exec_res = client.get(f"/api/v1/projects/{proj_a['id']}/executions/{random_exec_id}/evidence/{ev_item['id']}/download")
    assert bad_exec_res.status_code == 404

    # Invalid evidence ID fails with 404
    random_ev_id = str(uuid4())
    bad_ev_res = client.get(f"/api/v1/projects/{proj_a['id']}/executions/{exec_a['id']}/evidence/{random_ev_id}/download")
    assert bad_ev_res.status_code == 404


def test_test_case_history_endpoint_and_pagination(client: TestClient) -> None:
    """History endpoint returns all executions for a test case with proper pagination."""
    proj = create_project(client, "History Project")
    req = create_requirement(client, proj["id"])
    tc = create_and_approve_test_case(client, proj["id"], req["id"], title="Multi-Run TC")

    # Run twice
    exec1 = client.post(f"/api/v1/projects/{proj['id']}/test-cases/{tc['id']}/execute").json()
    exec2 = client.post(f"/api/v1/projects/{proj['id']}/test-cases/{tc['id']}/execute").json()

    # Query history
    hist_res = client.get(f"/api/v1/projects/{proj['id']}/test-cases/{tc['id']}/history?limit=10&offset=0")
    assert hist_res.status_code == 200
    hist = hist_res.json()
    assert hist["total"] == 2
    assert len(hist["items"]) == 2
    # Verify latest first
    assert hist["items"][0]["id"] == exec2["id"]
    assert hist["items"][1]["id"] == exec1["id"]

    # Test pagination
    paged_res = client.get(f"/api/v1/projects/{proj['id']}/test-cases/{tc['id']}/history?limit=1&offset=0")
    assert paged_res.status_code == 200
    assert len(paged_res.json()["items"]) == 1
    assert paged_res.json()["total"] == 2


def test_sensitive_url_query_parameters_redaction() -> None:
    # 1. Test URL string with multiple parameters including case variations and sensitive variants
    url = "https://api.example.com/v1/search?q=testmate&token=synth_token_123&API_KEY=synth_api_key_456&keyword=laptop&access_token=synth_access_789&page=1&secret=synth_secret_999"
    sanitized = sanitize_url_string(url)
    assert "synth_token_123" not in sanitized
    assert "synth_api_key_456" not in sanitized
    assert "synth_access_789" not in sanitized
    assert "synth_secret_999" not in sanitized
    # Non-sensitive parameters preserved
    assert "q=testmate" in sanitized
    assert "keyword=laptop" in sanitized
    assert "page=1" in sanitized
    assert "token=[REDACTED]" in sanitized
    assert "API_KEY=[REDACTED]" in sanitized

    # 2. Test userinfo in netloc
    url_userinfo = "https://admin:super_secret_pw@service.internal:8080/data?key=synth_key_abc"
    sanitized_userinfo = sanitize_url_string(url_userinfo)
    assert "super_secret_pw" not in sanitized_userinfo
    assert "synth_key_abc" not in sanitized_userinfo
    assert "admin:[REDACTED]@service.internal:8080" in sanitized_userinfo
    assert "key=[REDACTED]" in sanitized_userinfo

    # 3. Test nested in dictionaries and lists via sanitize_sensitive_data
    payload = {
        "endpoint": "https://api.example.com/items?credential=synth_cred&sort=desc",
        "redirect_history": [
            "https://auth.example.com/oauth?refresh_token=synth_refresh&state=xyz",
            "https://api.example.com/items?q=shoes",
        ],
        "safe_value": "https://example.com/docs",
    }
    sanitized_payload = sanitize_sensitive_data(payload)
    assert "synth_cred" not in sanitized_payload["endpoint"]
    assert "credential=[REDACTED]" in sanitized_payload["endpoint"]
    assert "sort=desc" in sanitized_payload["endpoint"]
    assert "synth_refresh" not in sanitized_payload["redirect_history"][0]
    assert "refresh_token=[REDACTED]" in sanitized_payload["redirect_history"][0]
    assert "state=xyz" in sanitized_payload["redirect_history"][0]
    assert sanitized_payload["redirect_history"][1] == "https://api.example.com/items?q=shoes"
    assert sanitized_payload["safe_value"] == "https://example.com/docs"


def test_log_secret_redaction_and_disk_persistence(tmp_path: Path) -> None:
    settings = get_settings()
    manager = EvidenceManager(settings)
    execution_id = uuid4()

    synthetic_bearer = "synthetic_bearer_jwt_9876543210"
    synthetic_api_key = "sk_live_synthetic_api_key_abcdef"
    synthetic_password = "synthetic_raw_password_xyz123"
    synthetic_url_token = "synthetic_url_secret_token_555"

    log_content = (
        f"2026-10-13 10:00:00 [INFO] Starting test execution for TC_01\n"
        f"2026-10-13 10:00:01 [DEBUG] Request Headers: Authorization: Bearer {synthetic_bearer}\n"
        f"2026-10-13 10:00:02 [DEBUG] Initializing runner with api_key='{synthetic_api_key}' and password: \"{synthetic_password}\"\n"
        f"2026-10-13 10:00:03 [INFO] Sending GET request to https://api.service.internal/v2/users?token={synthetic_url_token}&limit=25\n"
        f"2026-10-13 10:00:04 [INFO] Step 1 passed with HTTP 200 OK\n"
    )

    evidence_item = manager.save_log(execution_id, log_content, label="Redacted Execution Log")
    assert evidence_item.uri.endswith(".log")

    # Read physical file from disk
    stored_path = Path(settings.evidence_storage_dir).resolve() / evidence_item.uri
    assert stored_path.is_file()
    stored_bytes = stored_path.read_bytes()
    stored_text = stored_bytes.decode("utf-8")

    # Verify that NONE of the raw synthetic secrets appear in the stored bytes
    assert synthetic_bearer not in stored_text
    assert synthetic_api_key not in stored_text
    assert synthetic_password not in stored_text
    assert synthetic_url_token not in stored_text

    # Verify that redactions occurred in place
    assert "Authorization: Bearer [REDACTED]" in stored_text
    assert "api_key=[REDACTED]" in stored_text
    assert "password: [REDACTED]" in stored_text
    assert "https://api.service.internal/v2/users?token=[REDACTED]&limit=25" in stored_text

    # Verify diagnostic text is preserved
    assert "Starting test execution for TC_01" in stored_text
    assert "Step 1 passed with HTTP 200 OK" in stored_text

    # Verify SHA-256 matches actual stored bytes
    expected_sha256 = hashlib.sha256(stored_bytes).hexdigest()
    assert evidence_item.metadata["sha256"] == expected_sha256
    assert evidence_item.metadata["size_bytes"] == len(stored_bytes)


def test_execution_summary_field_alignment_and_legacy_support(client: TestClient, db_session: Session) -> None:
    proj = create_project(client, "Alignment Project")
    req = create_requirement(client, proj["id"])
    tc = create_and_approve_test_case(client, proj["id"], req["id"], title="Alignment TC")

    # 1. Live execution run
    exec_res = client.post(f"/api/v1/projects/{proj['id']}/test-cases/{tc['id']}/execute")
    assert exec_res.status_code == 201
    exec_id = exec_res.json()["id"]

    detail_res = client.get(f"/api/v1/projects/{proj['id']}/executions/{exec_id}/detail")
    assert detail_res.status_code == 200
    detail = detail_res.json()

    context_res = client.get(f"/api/v1/projects/{proj['id']}/executions/{exec_id}/analysis-context")
    assert context_res.status_code == 200
    context = context_res.json()

    # Detail and Analysis Context must agree
    assert detail["summary"]["duration_ms"] == context["duration_ms"]
    assert detail["summary"]["total_duration_ms"] == detail["summary"]["duration_ms"]
    assert detail["summary"]["sanitized_failure_reason"] == context["sanitized_failure_reason"]
    assert detail["summary"]["error_category"] == context["error_category"]

    # 2. Legacy execution summary record in database (only containing legacy keys total_duration_ms and failure_explanation)
    legacy_exec_id = uuid4()
    legacy_exec = TestExecution(
        id=legacy_exec_id,
        test_case_id=tc["id"],
        status=ExecutionStatus.FAILED,
        executor="httpx",
        run_reference="legacy_run_01",
        started_at=datetime.now(timezone.utc),
        completed_at=datetime.now(timezone.utc),
        summary={
            "total_steps": 2,
            "passed_steps": 1,
            "failed_steps": 1,
            "error_steps": 0,
            "skipped_steps": 0,
            "total_duration_ms": 250.75,
            "error_category": "assertion_failure",
            "failed_step_index": 2,
            "failure_explanation": "Expected HTTP 200, got HTTP 500",
            "step_results": [
                {"step_index": 1, "action": "GET /api/v1/health", "status": "passed", "duration_ms": 50.0},
                {"step_index": 2, "action": "POST /api/v1/login", "status": "failed", "duration_ms": 200.75, "error_details": "HTTP 500"},
            ],
        },
        error_message="Expected HTTP 200, got HTTP 500",
    )
    db_session.add(legacy_exec)
    db_session.commit()

    # Verify detail endpoint loads legacy summary without missing keys
    legacy_detail_res = client.get(f"/api/v1/projects/{proj['id']}/executions/{legacy_exec_id}/detail")
    assert legacy_detail_res.status_code == 200
    legacy_detail = legacy_detail_res.json()
    assert legacy_detail["summary"]["duration_ms"] == 250.75
    assert legacy_detail["summary"]["total_duration_ms"] == 250.75
    assert legacy_detail["summary"]["sanitized_failure_reason"] == "Expected HTTP 200, got HTTP 500"
    assert legacy_detail["summary"]["failure_explanation"] == "Expected HTTP 200, got HTTP 500"

    # Verify analysis-context endpoint consumes legacy summary accurately
    legacy_ctx_res = client.get(f"/api/v1/projects/{proj['id']}/executions/{legacy_exec_id}/analysis-context")
    assert legacy_ctx_res.status_code == 200
    legacy_ctx = legacy_ctx_res.json()
    assert legacy_ctx["duration_ms"] == 250.75
    assert legacy_ctx["sanitized_failure_reason"] == "Expected HTTP 200, got HTTP 500"
    assert legacy_ctx["failed_step_index"] == 2
    assert legacy_ctx["failed_step"] is not None
    assert legacy_ctx["failed_step"]["step_index"] == 2


def test_nonexistent_test_case_history_isolation(client: TestClient) -> None:
    proj_a = create_project(client, "History Iso A")
    req_a = create_requirement(client, proj_a["id"])
    tc_a = create_and_approve_test_case(client, proj_a["id"], req_a["id"], title="TC A")

    proj_b = create_project(client, "History Iso B")

    random_id = str(uuid4())

    # 1. Nonexistent project returns 404
    res_bad_proj = client.get(f"/api/v1/projects/{random_id}/test-cases/{tc_a['id']}/history")
    assert res_bad_proj.status_code == 404

    # 2. Existing project, nonexistent test case returns 404
    res_bad_tc = client.get(f"/api/v1/projects/{proj_a['id']}/test-cases/{random_id}/history")
    assert res_bad_tc.status_code == 404

    # 3. Cross-project test case returns 404 (TC A requested under Project B)
    res_cross = client.get(f"/api/v1/projects/{proj_b['id']}/test-cases/{tc_a['id']}/history")
    assert res_cross.status_code == 404

    # 4. Existing test case with 0 executions returns 200 with empty list
    res_empty = client.get(f"/api/v1/projects/{proj_a['id']}/test-cases/{tc_a['id']}/history")
    assert res_empty.status_code == 200
    empty_data = res_empty.json()
    assert empty_data["items"] == []
    assert empty_data["total"] == 0
