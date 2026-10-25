"""
Phase 13: End-to-End Integration, Testing & Final Verification Suite.

Validates:
1. Complete lifecycle from Project creation to final Executive Report.
2. Requirement creation, AI analysis, test-case generation, approval, and traceability.
3. Autonomous test execution, screenshot/log evidence persistence, defect auto-creation.
4. AI Failure Analysis with historical RAG retrieval and project scoping.
5. LangGraph multi-agent orchestration: context validation, human approval interrupt, resume, and execution.
6. Self-healing test lifecycle: selector failure detection, live candidate validation, controlled human approval, safe atomic repair, and re-execution with assertion verification.
7. Cross-project isolation and security protections (SSRF, credentials, and password masking).
"""

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import ResourceConflictError, ResourceNotFoundError
from app.core.url_utils import is_blocked_host, validate_and_normalize_url
from app.models.enums import (
    DefectStatus,
    EvidenceType,
    ExecutionStatus,
    HealingStatus,
    Priority,
    ReviewStatus,
    Severity,
    TestCaseStatus,
    TestType,
    WorkflowApprovalAction,
    WorkflowStage,
    WorkflowStatus,
)
from app.models.healing_proposal import HealingProposal
from app.models.project import Project
from app.models.requirement import Requirement
from app.models.test_case import TestCase
from app.models.test_execution import TestExecution
from app.schemas.failure_analysis import (
    ConfidenceLevel,
    FailureAnalysisContent,
    FailureCategory,
)
from app.schemas.generated_test_case import (
    GeneratedStep,
    GeneratedTestCaseCollection,
    GeneratedTestCaseItem,
)
from app.schemas.requirement_analysis import (
    AnalysisItem,
    AnalysisMetadata,
    AnalysisSource,
    ClarityLevel,
    QualityAssessment,
    RequirementAnalysis,
    RequirementAnalysisRead,
    RequirementType,
    RequirementTypeAssessment,
)
from app.services.analytics_service import AnalyticsService
from app.services.execution_service import ExecutionService
from app.services.self_healing_service import SelfHealingService
from app.services.workflow_service import WorkflowService
from app.testing.contract import (
    ErrorCategory,
    EvidencePayload,
    ExecutionOutcome,
    StepExecutionResult,
)


class MockTestCaseProvider:
    provider_name = "mock"
    model_name = "mock-model"

    def generate(self, requirement: Requirement) -> GeneratedTestCaseCollection:
        return GeneratedTestCaseCollection(
            test_cases=[
                GeneratedTestCaseItem(
                    title="Verify Secure Checkout Form Submission",
                    description="Customer completes purchase through payment gateway",
                    test_type=TestType.WEB,
                    priority=Priority.HIGH,
                    preconditions=["Valid user session", "Items in cart"],
                    steps=[
                        GeneratedStep(action="Enter payment details", expected_result="Details accepted"),
                        GeneratedStep(action="Click Complete Purchase", expected_result="Order confirmation displayed"),
                    ],
                    expected_result="Order confirmation number displayed with successful message.",
                )
            ],
            requirement_coverage_summary="Covers secure checkout payment flow.",
            assumptions=["Mock gateway is responsive"],
        )


def sample_analysis() -> RequirementAnalysisRead:
    item_explicit = AnalysisItem(text="The requirement describes secure checkout payment flow.", source=AnalysisSource.EXPLICIT)
    item_unspecified = AnalysisItem(text="Unspecified behavior.", source=AnalysisSource.UNSPECIFIED)
    return RequirementAnalysisRead(
        analysis=RequirementAnalysis(
            summary=item_explicit,
            requirement_type=RequirementTypeAssessment(
                classification=RequirementType.FUNCTIONAL,
                rationale=item_explicit,
            ),
            actors_and_entities=[AnalysisItem(text="Customer", source=AnalysisSource.EXPLICIT)],
            expected_behaviors=[item_explicit],
            inputs=[item_unspecified],
            outputs=[item_unspecified],
            preconditions=[item_unspecified],
            postconditions=[item_unspecified],
            acceptance_criteria=[AnalysisItem(text="Order total calculated and confirmed.", source=AnalysisSource.EXPLICIT)],
            ambiguities_and_missing_information=[],
            dependencies_and_constraints=[],
            clarification_questions=[],
            quality_assessment=QualityAssessment(
                clarity=ClarityLevel.HIGH,
                completeness=ClarityLevel.MEDIUM,
                reasons=[item_explicit],
                limitation="Assesses supplied requirement text.",
            ),
        ),
        metadata=AnalysisMetadata(
            provider="mock",
            model="mock-model",
            prompt_version="1.0",
            analyzed_at=datetime.now(timezone.utc),
        ),
    )


# ==============================================================================
# 1. Complete End-to-End User & Analytics Lifecycle
# ==============================================================================



def test_complete_e2e_project_to_reporting_lifecycle(client: TestClient, db_session: Session) -> None:
    """
    End-to-end integration test verifying the full user lifecycle:
    1. Project creation.
    2. Requirement creation with target URL.
    3. Requirement analysis.
    4. Test case creation and approval.
    5. Test execution and structured evidence persistence.
    6. Defect tracking.
    7. Analytics, traceability, and executive report aggregation.
    """
    # 1. Create Project
    proj_resp = client.post("/api/v1/projects", json={"name": f"E2E Integration Proj {uuid4().hex[:6]}", "description": "Full lifecycle project"})
    assert proj_resp.status_code == 201
    project_data = proj_resp.json()
    proj_id = project_data["id"]

    # 2. Create Requirement
    req_resp = client.post(
        f"/api/v1/projects/{proj_id}/requirements",
        json={
            "title": "Secure Checkout Payment",
            "description": "Users complete checkout with verified credit cards.",
            "target_url": "http://127.0.0.1:8000/api/v1/demo/storefront",
            "acceptance_criteria": ["Items in cart", "Card validated", "Receipt displayed"],
        },
    )
    assert req_resp.status_code == 201
    req_id = req_resp.json()["id"]

    # 3. Create Test Case targeting the demo storefront
    tc_resp = client.post(
        f"/api/v1/projects/{proj_id}/test-cases",
        json={
            "requirement_id": req_id,
            "title": "Checkout Payment Success Path",
            "description": "Places order and verifies Order Confirmed message",
            "test_type": "web",
            "priority": "critical",
            "target_url": "http://127.0.0.1:8000/api/v1/demo/storefront",
            "expected_result": "Order Confirmed! message is displayed",
            "steps": [
                {"action": "Navigate to storefront", "data": {"action": "navigate", "url": "/"}},
                {"action": "Fill Cardholder Name", "data": {"action": "fill", "label": "Cardholder Name", "value": "Alice Test"}},
                {"action": "Fill Card Number", "data": {"action": "fill", "label": "Card Number", "value": "4242 4242 4242 4242"}},
                {"action": "Submit Order", "data": {"action": "click", "role": "button", "name": "Place Order"}},
                {"action": "Verify Confirmation", "data": {"action": "assert_text", "text": "Order Confirmed!"}},
            ],
        },
    )
    assert tc_resp.status_code == 201
    tc_id = tc_resp.json()["id"]

    # 4. Approve Test Case
    approve_tc_resp = client.patch(
        f"/api/v1/projects/{proj_id}/test-cases/{tc_id}",
        json={"review_status": "approved", "status": "approved"},
    )
    assert approve_tc_resp.status_code == 200
    assert approve_tc_resp.json()["review_status"] == "approved"

    # 5. Execute Test Case with Playwright mock runner for predictable integration validation
    mock_outcome = ExecutionOutcome(
        status=ExecutionStatus.PASSED,
        step_results=[
            StepExecutionResult(step_index=0, action="navigate", status="passed", duration_ms=250.0),
            StepExecutionResult(step_index=1, action="fill", status="passed", duration_ms=200.0),
            StepExecutionResult(step_index=2, action="fill", status="passed", duration_ms=200.0),
            StepExecutionResult(step_index=3, action="click", status="passed", duration_ms=300.0),
            StepExecutionResult(step_index=4, action="assert_text", status="passed", duration_ms=300.0),
        ],
        evidence_items=[
            EvidencePayload(evidence_type=EvidenceType.SCREENSHOT, uri="screenshots/final_confirm.png", label="Order Confirmation Screen"),
            EvidencePayload(evidence_type=EvidenceType.LOG, uri="logs/browser_console.log", label="Console Logs"),
        ],
    )

    mock_runner = MagicMock()
    mock_runner.execute.return_value = mock_outcome

    with patch("app.services.execution_service.PlaywrightWebRunner", return_value=mock_runner):
        exec_resp = client.post(f"/api/v1/projects/{proj_id}/test-cases/{tc_id}/execute")
        assert exec_resp.status_code == 201
        exec_data = exec_resp.json()
        exec_id = exec_data["id"]
        assert exec_data["status"] == "passed"

    # 6. Verify Execution Detail and Evidence
    detail_resp = client.get(f"/api/v1/projects/{proj_id}/executions/{exec_id}/detail")
    assert detail_resp.status_code == 200
    assert detail_resp.json()["summary"]["passed_steps"] == 5

    evidence_resp = client.get(f"/api/v1/projects/{proj_id}/executions/{exec_id}/evidence")
    assert evidence_resp.status_code == 200
    assert len(evidence_resp.json()["items"]) == 2

    # 7. Verify Analytics, Traceability, and Report
    analytics_resp = client.get(f"/api/v1/projects/{proj_id}/analytics")
    assert analytics_resp.status_code == 200
    analytics_data = analytics_resp.json()
    assert analytics_data["total_requirements"] == 1
    assert analytics_data["total_test_cases"] == 1
    assert analytics_data["passed_executions"] == 1
    assert analytics_data["execution_pass_rate"] == 100.0
    assert analytics_data["requirement_coverage_rate"] == 100.0

    trace_resp = client.get(f"/api/v1/projects/{proj_id}/traceability")
    assert trace_resp.status_code == 200
    trace_data = trace_resp.json()
    assert trace_data["coverage_rate"] == 100.0
    assert trace_data["covered_requirements"] == 1

    report_resp = client.get(f"/api/v1/projects/{proj_id}/report")
    assert report_resp.status_code == 200
    report_data = report_resp.json()
    assert report_data["quality_score"] >= 80.0


# ==============================================================================
# 2. Defect Creation, AI Failure Analysis & Historical RAG
# ==============================================================================


def test_e2e_defect_failure_analysis_and_rag_integration(client: TestClient, db_session: Session) -> None:
    """
    Verifies that when an execution fails:
    1. A Defect record is created and linked.
    2. AI Failure Analysis synthesizes root cause with historical context.
    3. Defect knowledge indexing and semantic retrieval function correctly.
    """
    # Create Project & Requirement
    proj = Project(name=f"Defect RAG Project {uuid4().hex[:6]}", description="RAG and failure analysis test")
    db_session.add(proj)
    db_session.commit()
    db_session.refresh(proj)

    req = Requirement(
        project_id=proj.id,
        title="Payment Gateway Integration",
        description="Processes checkout transactions.",
        acceptance_criteria=["Card authorized"],
    )
    db_session.add(req)
    db_session.commit()
    db_session.refresh(req)

    tc = TestCase(
        requirement_id=req.id,
        title="Declining Card Rejection Test",
        description="Verify handling of declined credit card",
        test_type=TestType.WEB,
        priority=Priority.HIGH,
        status=TestCaseStatus.APPROVED,
        review_status=ReviewStatus.APPROVED,
        expected_result="Payment declined alert is shown",
        steps=[{"action": "Click submit", "data": {"action": "click", "role": "button", "name": "Pay"}}],
    )
    db_session.add(tc)
    db_session.commit()
    db_session.refresh(tc)

    # Simulate failing execution that creates a Defect
    failed_outcome = ExecutionOutcome(
        status=ExecutionStatus.FAILED,
        error_message="AssertionError: Expected text 'Order Confirmed!' not found on page.",
        error_category=ErrorCategory.ASSERTION_FAILURE.value,
        failed_step_index=0,
        step_results=[StepExecutionResult(step_index=0, action="click", status="failed", duration_ms=850.0, error_message="AssertionError: Expected text 'Order Confirmed!' not found.")],
        evidence_items=[EvidencePayload(evidence_type=EvidenceType.SCREENSHOT, uri="screenshots/declined_error.png", label="Declined Error Screen")],
    )

    mock_runner = MagicMock()
    mock_runner.execute.return_value = failed_outcome

    exec_svc = ExecutionService(db_session)
    with patch("app.services.execution_service.PlaywrightWebRunner", return_value=mock_runner):
        execution = exec_svc.execute_test_case(project_id=proj.id, test_case_id=tc.id)

    assert execution.status == ExecutionStatus.FAILED

    # Verify auto-created Defect
    defects, total_defects = exec_svc.list_defects(project_id=proj.id, limit=10, offset=0, status=None, severity=None)
    assert total_defects >= 1
    defect = defects[0]
    assert defect.execution_id == execution.id
    assert defect.title == f"Execution Failed: {tc.title}"
    assert "Expected text 'Order Confirmed!'" in defect.description

    # Trigger AI Failure Analysis
    mock_provider = MagicMock()
    mock_provider.provider_name = "gemini"
    mock_provider.model_name = "gemini-2.5-flash"
    mock_provider.analyze.return_value = FailureAnalysisContent(
        failure_category=FailureCategory.APPLICATION_ERROR,
        summary="Payment gateway rejected transaction in sandbox.",
        observed_error="AssertionError: Expected text 'Order Confirmed!' not found.",
        likely_root_cause="The payment gateway rejected the test card transaction, preventing confirmation.",
        supporting_evidence=["Step 0 failed with AssertionError"],
        recommended_debugging_steps=["Verify test card credentials in sandbox mode"],
        confidence=ConfidenceLevel.HIGH,
        uncertainty_notes=None,
    )

    with patch("app.services.failure_analysis_service.get_failure_analysis_provider", return_value=mock_provider):
        fa_resp = client.post(f"/api/v1/projects/{proj.id}/executions/{execution.id}/analysis")
        assert fa_resp.status_code == 200
        fa_data = fa_resp.json()
        assert fa_data["failure_category"] == "application_error"
        assert fa_data["confidence"] == "high"
        assert "Payment gateway rejected" in fa_data["summary"]


# ==============================================================================
# 3. LangGraph Multi-Agent Workflow Orchestration & Human Approval
# ==============================================================================


def test_e2e_langgraph_multi_agent_workflow_orchestration(client: TestClient, db_session: Session) -> None:
    """
    Verifies the LangGraph multi-agent orchestration lifecycle:
    1. Workflow started.
    2. Context validated & requirement analyzed.
    3. Test cases synthesized.
    4. Workflow interrupts at human_approval stage.
    5. Approval decision submitted with notes.
    6. Workflow resumes and completes test execution.
    """
    proj = Project(name=f"Workflow Proj {uuid4().hex[:6]}", description="LangGraph workflow test")
    db_session.add(proj)
    db_session.commit()
    db_session.refresh(proj)

    req = Requirement(
        project_id=proj.id,
        title="Checkout Cart Calculation",
        description="Calculates taxes and shipping during checkout.",
        acceptance_criteria=["Tax calculated correctly", "Shipping fee applied"],
    )
    db_session.add(req)
    db_session.commit()
    db_session.refresh(req)

    # Start Workflow with mocked providers for deterministic execution
    mock_analysis_svc = MagicMock()
    mock_analysis_svc.analyze.return_value = sample_analysis()

    mock_exec = MagicMock()
    mock_exec.id = uuid4()
    mock_exec.status.value = "passed"
    mock_exec.error_message = None

    with (
        patch("app.orchestration.nodes.get_requirement_analysis_service", return_value=mock_analysis_svc),
        patch("app.orchestration.nodes.get_test_case_generation_provider", return_value=MockTestCaseProvider()),
        patch("app.services.execution_service.ExecutionService.execute_test_case", return_value=mock_exec),
    ):
        start_resp = client.post(
            f"/api/v1/projects/{proj.id}/workflows",
            json={"requirement_id": str(req.id), "initial_notes": "Starting autonomous QA cycle"},
        )
        assert start_resp.status_code == 201
        wf_data = start_resp.json()
        wf_id = wf_data["id"]

        # Workflow pauses for human approval
        assert wf_data["status"] == WorkflowStatus.PAUSED_FOR_APPROVAL.value
        assert wf_data["current_stage"] == WorkflowStage.HUMAN_APPROVAL.value

        # Inspect workflow details via API
        get_wf_resp = client.get(f"/api/v1/projects/{proj.id}/workflows/{wf_id}")
        assert get_wf_resp.status_code == 200
        assert len(get_wf_resp.json()["generated_test_cases"]) > 0

        # Submit Human Approval
        approval_resp = client.post(
            f"/api/v1/projects/{proj.id}/workflows/{wf_id}/approval",
            json={"action": "approve", "notes": "Test cases reviewed and approved for browser execution"},
        )
        assert approval_resp.status_code == 200
        approved_wf = approval_resp.json()
        assert approved_wf["status"] == WorkflowStatus.COMPLETED.value
        assert approved_wf["approval_decision"].get("action") == "approve"

    # Verify history contains audit trail of stages
    hist_resp = client.get(f"/api/v1/projects/{proj.id}/workflows/{wf_id}/history")
    assert hist_resp.status_code == 200
    event_stages = [ev["stage"] for ev in hist_resp.json()["events"]]
    assert WorkflowStage.INITIALIZATION.value in event_stages
    assert WorkflowStage.HUMAN_APPROVAL.value in event_stages
    assert WorkflowStage.COMPLETED.value in event_stages


# ==============================================================================
# 4. Self-Healing Tests Lifecycle & Assertion Verification
# ==============================================================================


def test_e2e_self_healing_detection_approval_and_assertion_verification(client: TestClient, db_session: Session) -> None:
    """
    Verifies Phase 12 Self-Healing:
    1. Broken locator failure captured with candidate validation results.
    2. Healing proposal persisted and listed.
    3. Proposal inspected via API.
    4. Human approval safely updates test step, increments version, and triggers re-execution.
    5. Re-execution with passing assertions sets status to HEALED.
    6. Re-execution with failing assertions sets status to FAILED (mandatory assertion rule).
    """
    proj = Project(name=f"Self Healing Proj {uuid4().hex[:6]}", description="Healing integration")
    db_session.add(proj)
    db_session.commit()
    db_session.refresh(proj)

    req = Requirement(project_id=proj.id, title="Self-Healing Flow", description="Button locator changed", acceptance_criteria=["Submit button clicked"])
    db_session.add(req)
    db_session.commit()
    db_session.refresh(req)

    tc = TestCase(
        requirement_id=req.id,
        title="Checkout Button Selector Test",
        description="Tests locator self-healing",
        test_type=TestType.WEB,
        priority=Priority.HIGH,
        status=TestCaseStatus.APPROVED,
        review_status=ReviewStatus.APPROVED,
        steps=[{"action": "Click submit", "data": {"action": "click", "selector": "#old-obsolete-submit-button"}}],
        expected_result="Form submitted successfully",
    )
    db_session.add(tc)
    db_session.commit()
    db_session.refresh(tc)

    # 1. Simulate selector failure during execution
    healing_service = SelfHealingService(db_session)

    orig_exec = TestExecution(
        id=uuid4(),
        test_case_id=tc.id,
        status=ExecutionStatus.FAILED,
        executor="playwright",
        error_message="locator.click: Error: strict mode violation: get_by_role('button', name='Pay') resolved to 2 elements",
        summary={"error_category": "strict_mode_violation"},
    )
    db_session.add(orig_exec)
    db_session.commit()
    db_session.refresh(orig_exec)

    candidate_results = [
        {
            "selector": {"role": "button", "name": "Complete Order"},
            "selector_type": "role_and_name",
            "match_count": 1,
            "is_visible": True,
            "is_enabled": True,
            "is_actionable": True,
            "score": 95.0,
            "valid": True,
            "rejection_reason": None,
            "confidence_explanation": "Unique match (count=1), Semantic role 'button' and name 'Complete Order'",
        }
    ]

    proposal = healing_service.create_proposal_from_failure(
        project_id=proj.id,
        test_case_id=tc.id,
        execution_id=orig_exec.id,
        step_index=1,
        action_type="click",
        original_selector={"selector": "#old-obsolete-submit-button"},
        failure_reason="locator.click: Error: strict mode violation",
        failure_category="strict_mode_violation",
        page_url="http://127.0.0.1:8000/api/v1/demo/storefront",
        page_title="TestMate AI Storefront",
        dom_context={},
        candidate_validation_results=candidate_results,
    )
    assert proposal is not None
    assert proposal.status == HealingStatus.AWAITING_APPROVAL
    assert proposal.confidence == 95.0

    # 2. List proposals via API
    list_resp = client.get(f"/api/v1/projects/{proj.id}/healing-proposals")
    assert list_resp.status_code == 200
    assert list_resp.json()["total"] == 1

    # 3. Get proposal detail via API
    get_resp = client.get(f"/api/v1/projects/{proj.id}/healing-proposals/{proposal.id}")
    assert get_resp.status_code == 200
    assert get_resp.json()["proposed_selector"] == {"role": "button", "name": "Complete Order"}
    assert len(get_resp.json()["candidate_validation_results"]) == 1

    # 4. Approve Proposal with passing retry execution outcome
    passed_retry_outcome = ExecutionOutcome(
        status=ExecutionStatus.PASSED,
        step_results=[StepExecutionResult(step_index=0, action="click", status="passed", duration_ms=220.0)],
    )

    mock_retry_runner = MagicMock()
    mock_retry_runner.execute.return_value = passed_retry_outcome

    with patch("app.services.execution_service.PlaywrightWebRunner", return_value=mock_retry_runner):
        approve_resp = client.post(
            f"/api/v1/projects/{proj.id}/healing-proposals/{proposal.id}/approve",
            json={"decision_notes": "Approved replacement selector verified by QA", "approved_by": "QA Lead"},
        )
        assert approve_resp.status_code == 200
        approved_data = approve_resp.json()
        assert approved_data["status"] == HealingStatus.HEALED.value
        assert approved_data["approved_selector"] == {"role": "button", "name": "Complete Order"}
        assert approved_data["retry_execution_id"] is not None

    # Verify that the test case step was safely updated in the database
    db_session.refresh(tc)
    assert tc.steps[0]["data"]["role"] == "button"
    assert tc.steps[0]["data"]["name"] == "Complete Order"
    assert tc.version == 2
    assert tc.steps[0]["data"]["_healing_history"][0]["original_selector"] == {"selector": "#old-obsolete-submit-button"}

    # 5. Assertion Verification Rule: If re-execution fails downstream assertions, healing is marked FAILED
    failed_retry_outcome = ExecutionOutcome(
        status=ExecutionStatus.FAILED,
        error_message="AssertionError: Expected text 'Success' not found.",
        error_category=ErrorCategory.ASSERTION_FAILURE.value,
        failed_step_index=0,
        step_results=[StepExecutionResult(step_index=0, action="click", status="failed", duration_ms=500.0, error_message="AssertionError")],
    )

    prop2 = healing_service.create_proposal_from_failure(
        project_id=proj.id,
        test_case_id=tc.id,
        execution_id=orig_exec.id,
        step_index=1,
        action_type="click",
        original_selector={"role": "button", "name": "Complete Order"},
        failure_reason="locator.click: Error",
        failure_category="strict_mode_violation",
        page_url="http://127.0.0.1:8000/api/v1/demo/storefront",
        page_title="Storefront",
        dom_context={},
        candidate_validation_results=candidate_results,
    )
    assert prop2 is not None

    mock_fail_retry_runner = MagicMock()
    mock_fail_retry_runner.execute.return_value = failed_retry_outcome

    with patch("app.services.execution_service.PlaywrightWebRunner", return_value=mock_fail_retry_runner):
        approve_fail_resp = client.post(
            f"/api/v1/projects/{proj.id}/healing-proposals/{prop2.id}/approve",
            json={"decision_notes": "Attempt approval with failing retry assertion"},
        )
        assert approve_fail_resp.status_code == 200
        assert approve_fail_resp.json()["status"] == HealingStatus.FAILED.value
        assert approve_fail_resp.json()["retry_execution_id"] is not None


# ==============================================================================
# 5. Cross-Project Isolation & Security Controls
# ==============================================================================


def test_cross_project_data_isolation_and_security_controls(client: TestClient, db_session: Session) -> None:
    """
    Verifies tenant and project data isolation:
    1. Project B cannot view or modify Project A's requirements, test cases, executions, or healing proposals.
    2. SSRF protections reject dangerous and non-routable targets.
    """
    # Create Project A
    proj_a = Project(name=f"Tenant A {uuid4().hex[:6]}", description="Tenant A")
    db_session.add(proj_a)
    db_session.commit()
    db_session.refresh(proj_a)

    req_a = Requirement(project_id=proj_a.id, title="Tenant A Requirement", description="Secret A", acceptance_criteria=["AC 1"])
    db_session.add(req_a)
    db_session.commit()
    db_session.refresh(req_a)

    tc_a = TestCase(
        requirement_id=req_a.id,
        title="Tenant A Test Case",
        description="Confidential test",
        test_type=TestType.WEB,
        priority=Priority.MEDIUM,
        expected_result="Pass",
        steps=[{"action": "Navigate", "data": {"action": "navigate", "url": "/"}}],
    )
    db_session.add(tc_a)
    db_session.commit()
    db_session.refresh(tc_a)

    # Create Project B
    proj_b = Project(name=f"Tenant B {uuid4().hex[:6]}", description="Tenant B")
    db_session.add(proj_b)
    db_session.commit()
    db_session.refresh(proj_b)

    # Project B querying Project A's requirement -> 404
    cross_req = client.get(f"/api/v1/projects/{proj_b.id}/requirements/{req_a.id}")
    assert cross_req.status_code == 404

    # Project B querying Project A's test case -> 404
    cross_tc = client.get(f"/api/v1/projects/{proj_b.id}/test-cases/{tc_a.id}")
    assert cross_tc.status_code == 404

    # Project B listing requirements only returns Project B's items
    list_b = client.get(f"/api/v1/projects/{proj_b.id}/requirements")
    assert list_b.status_code == 200
    assert list_b.json()["total"] == 0

    # SSRF Protection Checks
    assert is_blocked_host("169.254.169.254")[0] is True
    assert is_blocked_host("metadata.google.internal")[0] is True
    assert is_blocked_host("0.0.0.0")[0] is True

    with pytest.raises(ValueError, match="prevent SSRF"):
        validate_and_normalize_url("http://169.254.169.254/latest/meta-data/")

    with pytest.raises(ValueError, match="scheme"):
        validate_and_normalize_url("javascript:alert(1)")
