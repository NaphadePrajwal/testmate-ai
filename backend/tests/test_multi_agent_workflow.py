from datetime import datetime, timezone
from unittest.mock import MagicMock, patch
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from langgraph.checkpoint.memory import MemorySaver
from sqlalchemy.orm import Session

from pydantic import ValidationError
from app.core.exceptions import ResourceConflictError, ResourceNotFoundError
from app.models.enums import (
    ExecutionStatus,
    Priority,
    ReviewStatus,
    TestCaseStatus,
    TestType,
    WorkflowApprovalAction,
    WorkflowStage,
    WorkflowStatus,
)
from app.models.execution_failure_analysis import ExecutionFailureAnalysis
from app.models.project import Project
from app.models.requirement import Requirement
from app.models.test_case import TestCase
from app.models.test_execution import TestExecution
from app.models.workflow_execution import WorkflowEvent, WorkflowExecution
from app.orchestration.graph import (
    build_workflow_graph,
    compile_workflow_graph,
    route_approval,
    route_execution_outcome,
)
from app.orchestration.state import WorkflowGraphState
from app.schemas.failure_analysis import FailureCategory
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
from app.schemas.workflow import WorkflowApprovalRequest
from app.services.workflow_service import WorkflowService


# Helper fixtures
def create_test_project_and_requirement(db: Session) -> tuple[Project, Requirement]:
    proj = Project(name=f"Workflow Test Project {uuid4().hex[:6]}", description="Testing LangGraph orchestration")
    db.add(proj)
    db.commit()
    db.refresh(proj)

    req = Requirement(
        project_id=proj.id,
        title="Checkout Payment Flow",
        description="As a customer, I want to complete a purchase securely so I receive confirmation.",
        acceptance_criteria=["Order total calculated", "Payment processed", "Confirmation email sent"],
        target_url="http://127.0.0.1:8088/checkout.html",
    )
    db.add(req)
    db.commit()
    db.refresh(req)
    return proj, req


def sample_requirement_analysis() -> RequirementAnalysisRead:
    item_explicit = AnalysisItem(text="The requirement describes secure checkout payment flow.", source=AnalysisSource.EXPLICIT)
    item_unspecified = AnalysisItem(text="Unspecified behavior.", source=AnalysisSource.UNSPECIFIED)

    analysis = RequirementAnalysis(
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
    )
    return RequirementAnalysisRead(
        analysis=analysis,
        metadata=AnalysisMetadata(
            provider="mock",
            model="mock-model",
            prompt_version="1.0",
            analyzed_at=datetime.now(timezone.utc),
        ),
    )


def sample_test_case_collection() -> GeneratedTestCaseCollection:
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


class MockTestCaseProvider:
    provider_name = "mock"
    model_name = "mock-model"

    def generate(self, requirement: Requirement) -> GeneratedTestCaseCollection:
        return sample_test_case_collection()


# ==============================================================================
# SECTION A: Graph Structure and Conditional Routing Tests
# ==============================================================================


def test_graph_compiles_with_all_required_nodes() -> None:
    """Verifies that build_workflow_graph registers all required agent nodes and compiles cleanly."""
    graph_builder = build_workflow_graph()
    assert graph_builder is not None

    expected_nodes = {
        "validate_context",
        "requirement_analysis",
        "test_case_generation",
        "human_approval",
        "apply_revision",
        "record_rejection",
        "validate_approval",
        "test_execution",
        "record_success",
        "historical_rag",
        "failure_analysis",
        "handle_error",
    }
    actual_nodes = set(graph_builder.nodes.keys())
    assert expected_nodes.issubset(actual_nodes), f"Missing nodes: {expected_nodes - actual_nodes}"

    # Compiles with MemorySaver
    checkpointer = MemorySaver()
    compiled = compile_workflow_graph(checkpointer=checkpointer)
    assert compiled is not None


def test_conditional_routing_approval_decisions() -> None:
    """Tests routing behavior from human approval checkpoint for all decision actions."""
    # 1. Approve -> validate_approval
    state_approve: WorkflowGraphState = {"approval_status": WorkflowApprovalAction.APPROVE.value}
    assert route_approval(state_approve) == "validate_approval"

    # 2. Reject -> record_rejection
    state_reject: WorkflowGraphState = {"approval_status": WorkflowApprovalAction.REJECT.value}
    assert route_approval(state_reject) == "record_rejection"

    # 3. Request Revision -> apply_revision
    state_revision: WorkflowGraphState = {"approval_status": WorkflowApprovalAction.REQUEST_REVISION.value}
    assert route_approval(state_revision) == "apply_revision"

    # 4. Unknown/malformed -> handle_error
    state_unknown: WorkflowGraphState = {"approval_status": "invalid_action"}
    assert route_approval(state_unknown) == "handle_error"


def test_conditional_routing_execution_outcomes() -> None:
    """
    Tests routing behavior following test execution:
    - Zero failures/errors routes to record_success (skipping RAG & failure analysis).
    - Failures or errors route through historical RAG and failure analysis.
    """
    # 1. All passed -> record_success
    state_all_passed: WorkflowGraphState = {"passed_count": 3, "failed_count": 0, "error_count": 0}
    assert route_execution_outcome(state_all_passed) == "record_success"

    # 2. One or more failed -> historical_rag
    state_failed: WorkflowGraphState = {"passed_count": 2, "failed_count": 1, "error_count": 0}
    assert route_execution_outcome(state_failed) == "historical_rag"

    # 3. Error occurred -> historical_rag
    state_error: WorkflowGraphState = {"passed_count": 0, "failed_count": 0, "error_count": 1}
    assert route_execution_outcome(state_error) == "historical_rag"


# ==============================================================================
# SECTION B: Human Approval Checkpoint & Execution Routing Tests
# ==============================================================================


def test_human_approval_pause_and_rejection_workflow(db_session: Session) -> None:
    """
    Verifies that the workflow:
    1. Runs through analysis and generation.
    2. Genuinely pauses at the human approval checkpoint.
    3. Rejection terminates without executing any test cases.
    """
    proj, req = create_test_project_and_requirement(db_session)
    checkpointer = MemorySaver()
    wf_service = WorkflowService(db=db_session, checkpointer=checkpointer)

    with (
        patch("app.orchestration.nodes.get_db", return_value=db_session),
        patch("app.orchestration.nodes.get_requirement_analysis_service") as mock_get_analysis_svc,
        patch("app.orchestration.nodes.get_test_case_generation_provider", return_value=MockTestCaseProvider()),
        patch.object(wf_service, "_get_checkpointer", return_value=checkpointer),
    ):
        mock_svc = MagicMock()
        mock_svc.analyze.return_value = sample_requirement_analysis()
        mock_get_analysis_svc.return_value = mock_svc

        # 1. Start workflow
        wf = wf_service.start_workflow(project_id=proj.id, requirement_id=req.id)
        wf_id = wf.id

        assert wf.status == WorkflowStatus.PAUSED_FOR_APPROVAL
        assert wf.current_stage == WorkflowStage.HUMAN_APPROVAL.value
        assert len(wf.generated_test_case_ids) > 0

        # Verify no execution has started before approval
        assert len(wf.execution_ids) == 0

        # 2. Submit REJECTION
        rejected_wf = wf_service.submit_approval(
            project_id=proj.id,
            workflow_id=wf_id,
            action=WorkflowApprovalAction.REJECT,
            notes="Scope of tests does not cover edge cases.",
        )

        assert rejected_wf.status == WorkflowStatus.REJECTED
        assert rejected_wf.current_stage == "rejected"
        assert len(rejected_wf.execution_ids) == 0  # Still zero executions!


def test_human_approval_revision_loop_and_reapproval(db_session: Session) -> None:
    """
    Verifies that requesting a revision loops back to test generation and pauses
    for human review again.
    """
    proj, req = create_test_project_and_requirement(db_session)
    checkpointer = MemorySaver()
    wf_service = WorkflowService(db=db_session, checkpointer=checkpointer)

    with (
        patch("app.orchestration.nodes.get_db", return_value=db_session),
        patch("app.orchestration.nodes.get_requirement_analysis_service") as mock_get_analysis_svc,
        patch("app.orchestration.nodes.get_test_case_generation_provider", return_value=MockTestCaseProvider()),
        patch.object(wf_service, "_get_checkpointer", return_value=checkpointer),
    ):
        mock_svc = MagicMock()
        mock_svc.analyze.return_value = sample_requirement_analysis()
        mock_get_analysis_svc.return_value = mock_svc

        # Start workflow
        wf = wf_service.start_workflow(project_id=proj.id, requirement_id=req.id)
        wf_id = wf.id
        assert wf.status == WorkflowStatus.PAUSED_FOR_APPROVAL

        # Request revision
        resumed_wf = wf_service.submit_approval(
            project_id=proj.id,
            workflow_id=wf_id,
            action=WorkflowApprovalAction.REQUEST_REVISION,
            notes="Please add CVV validation tests.",
            revision_instructions="Ensure CVV validation is tested.",
        )

        # Must pause at approval again!
        assert resumed_wf.status == WorkflowStatus.PAUSED_FOR_APPROVAL
        assert resumed_wf.current_stage == WorkflowStage.HUMAN_APPROVAL.value


def test_execution_all_pass_skips_rag_and_failure_analysis(db_session: Session) -> None:
    """
    Verifies that when all test cases pass during execution, the workflow completes
    directly without invoking historical RAG or Failure Analysis.
    """
    proj, req = create_test_project_and_requirement(db_session)
    checkpointer = MemorySaver()
    wf_service = WorkflowService(db=db_session, checkpointer=checkpointer)

    mock_execution = MagicMock()
    mock_execution.id = uuid4()
    mock_execution.status.value = "passed"
    mock_execution.error_message = None

    with (
        patch("app.orchestration.nodes.get_db", return_value=db_session),
        patch("app.orchestration.nodes.get_requirement_analysis_service") as mock_get_analysis_svc,
        patch("app.orchestration.nodes.get_test_case_generation_provider", return_value=MockTestCaseProvider()),
        patch.object(wf_service, "_get_checkpointer", return_value=checkpointer),
        patch("app.services.execution_service.ExecutionService.execute_test_case", return_value=mock_execution),
        patch("app.services.failure_analysis_service.FailureAnalysisService.get_or_create_analysis") as mock_fa,
    ):
        mock_svc = MagicMock()
        mock_svc.analyze.return_value = sample_requirement_analysis()
        mock_get_analysis_svc.return_value = mock_svc

        # 1. Start workflow
        wf = wf_service.start_workflow(project_id=proj.id, requirement_id=req.id)
        wf_id = wf.id
        assert wf.status == WorkflowStatus.PAUSED_FOR_APPROVAL

        # 2. Approve
        completed_wf = wf_service.submit_approval(
            project_id=proj.id,
            workflow_id=wf_id,
            action=WorkflowApprovalAction.APPROVE,
            notes="Looks great, proceed with execution.",
        )

        assert completed_wf.status == WorkflowStatus.COMPLETED
        assert completed_wf.current_stage == WorkflowStage.COMPLETED.value
        assert completed_wf.failure_analysis_id is None
        mock_fa.assert_not_called()  # Failure analysis was NOT called!


def test_execution_failure_triggers_rag_and_failure_analysis(db_session: Session) -> None:
    """
    Verifies that when a test execution fails, the workflow conditionally routes through
    historical RAG and the Failure Analysis Agent to diagnose the root cause.
    """
    proj, req = create_test_project_and_requirement(db_session)
    checkpointer = MemorySaver()
    wf_service = WorkflowService(db=db_session, checkpointer=checkpointer)

    failed_exec_id = uuid4()
    mock_failed_execution = MagicMock()
    mock_failed_execution.id = failed_exec_id
    mock_failed_execution.status.value = "failed"
    mock_failed_execution.error_message = "Payment gateway timed out after 30s"

    mock_analysis_record = MagicMock()
    analysis_id = uuid4()
    mock_analysis_record.id = analysis_id
    mock_analysis_record.failure_category = FailureCategory.INFRASTRUCTURE_ERROR.value
    mock_analysis_record.summary = "Gateway gateway timeout diagnosed."
    mock_analysis_record.likely_root_cause = "Third-party payment mock service was unresponsive."
    mock_analysis_record.confidence = "high"
    mock_analysis_record.recommended_debugging_steps = ["Check payment gateway mock status."]

    with (
        patch("app.orchestration.nodes.get_db", return_value=db_session),
        patch("app.orchestration.nodes.get_requirement_analysis_service") as mock_get_analysis_svc,
        patch("app.orchestration.nodes.get_test_case_generation_provider", return_value=MockTestCaseProvider()),
        patch.object(wf_service, "_get_checkpointer", return_value=checkpointer),
        patch("app.services.execution_service.ExecutionService.execute_test_case", return_value=mock_failed_execution),
        patch("app.services.failure_analysis_service.FailureAnalysisService.get_or_create_analysis", return_value=mock_analysis_record) as mock_fa,
    ):
        mock_svc = MagicMock()
        mock_svc.analyze.return_value = sample_requirement_analysis()
        mock_get_analysis_svc.return_value = mock_svc

        # 1. Start workflow
        wf = wf_service.start_workflow(project_id=proj.id, requirement_id=req.id)
        wf_id = wf.id
        assert wf.status == WorkflowStatus.PAUSED_FOR_APPROVAL
        case_id = UUID(wf.generated_test_case_ids[0])

        # Create real TestExecution and ExecutionFailureAnalysis records so DB foreign key is satisfied
        test_exec = TestExecution(
            id=failed_exec_id,
            test_case_id=case_id,
            status=ExecutionStatus.FAILED,
            error_message="Payment gateway timed out after 30s",
        )
        db_session.add(test_exec)
        db_session.flush()

        fa_record = ExecutionFailureAnalysis(
            id=analysis_id,
            execution_id=failed_exec_id,
            project_id=proj.id,
            failure_category=FailureCategory.INFRASTRUCTURE_ERROR.value,
            summary="Gateway gateway timeout diagnosed.",
            observed_error="Payment gateway timed out after 30s",
            likely_root_cause="Third-party payment mock service was unresponsive.",
            confidence="high",
        )
        db_session.add(fa_record)
        db_session.commit()

        # 2. Approve
        completed_wf = wf_service.submit_approval(
            project_id=proj.id,
            workflow_id=wf_id,
            action=WorkflowApprovalAction.APPROVE,
            notes="Run the tests.",
        )

        assert completed_wf.status == WorkflowStatus.COMPLETED
        assert completed_wf.failure_analysis_id == analysis_id
        mock_fa.assert_called_once()  # Failure analysis was called!


# ==============================================================================
# SECTION C: Security, Isolation, and Error Handling Tests
# ==============================================================================


def test_cross_project_workflow_isolation(db_session: Session) -> None:
    """Verifies that accessing or approving a workflow from another project is rejected."""
    proj1, req1 = create_test_project_and_requirement(db_session)
    proj2, _ = create_test_project_and_requirement(db_session)
    proj1_id = proj1.id
    req1_id = req1.id
    proj2_id = proj2.id

    checkpointer = MemorySaver()
    wf_service = WorkflowService(db=db_session, checkpointer=checkpointer)

    with (
        patch("app.orchestration.nodes.get_db", return_value=db_session),
        patch("app.orchestration.nodes.get_requirement_analysis_service") as mock_get_analysis_svc,
        patch("app.orchestration.nodes.get_test_case_generation_provider", return_value=MockTestCaseProvider()),
        patch.object(wf_service, "_get_checkpointer", return_value=checkpointer),
    ):
        mock_svc = MagicMock()
        mock_svc.analyze.return_value = sample_requirement_analysis()
        mock_get_analysis_svc.return_value = mock_svc

        wf = wf_service.start_workflow(project_id=proj1_id, requirement_id=req1_id)
        wf_id = wf.id

        # Attempt to get under proj2 -> ResourceNotFoundError
        with pytest.raises(ResourceNotFoundError):
            wf_service.get_workflow(project_id=proj2_id, workflow_id=wf_id)

        # Attempt to approve under proj2 -> ResourceNotFoundError
        with pytest.raises(ResourceNotFoundError):
            wf_service.submit_approval(
                project_id=proj2_id,
                workflow_id=wf_id,
                action=WorkflowApprovalAction.APPROVE,
            )


def test_duplicate_approval_rejection(db_session: Session) -> None:
    """Verifies that submitting approval on an already completed/rejected workflow raises ResourceConflictError."""
    proj, req = create_test_project_and_requirement(db_session)
    checkpointer = MemorySaver()
    wf_service = WorkflowService(db=db_session, checkpointer=checkpointer)

    with (
        patch("app.orchestration.nodes.get_db", return_value=db_session),
        patch("app.orchestration.nodes.get_requirement_analysis_service") as mock_get_analysis_svc,
        patch("app.orchestration.nodes.get_test_case_generation_provider", return_value=MockTestCaseProvider()),
        patch.object(wf_service, "_get_checkpointer", return_value=checkpointer),
    ):
        mock_svc = MagicMock()
        mock_svc.analyze.return_value = sample_requirement_analysis()
        mock_get_analysis_svc.return_value = mock_svc

        wf = wf_service.start_workflow(project_id=proj.id, requirement_id=req.id)
        wf_id = wf.id

        # Reject it
        wf_service.submit_approval(
            project_id=proj.id,
            workflow_id=wf_id,
            action=WorkflowApprovalAction.REJECT,
        )

        # Second approval attempt must raise ResourceConflictError
        with pytest.raises(ResourceConflictError):
            wf_service.submit_approval(
                project_id=proj.id,
                workflow_id=wf_id,
                action=WorkflowApprovalAction.APPROVE,
            )


# ==============================================================================
# SECTION D: FastAPI Endpoints Integration Tests
# ==============================================================================


def test_workflow_api_lifecycle(client: TestClient, db_session: Session) -> None:
    """
    Tests the complete workflow REST API surface:
    - POST /projects/{project_id}/workflows (starts workflow and pauses)
    - GET /projects/{project_id}/workflows/{workflow_id} (retrieves status and detail)
    - GET /projects/{project_id}/workflows/{workflow_id}/history (retrieves timeline)
    - POST /projects/{project_id}/workflows/{workflow_id}/approval (submits decision)
    """
    proj, req = create_test_project_and_requirement(db_session)
    checkpointer = MemorySaver()

    with (
        patch("app.orchestration.nodes.get_db", return_value=db_session),
        patch("app.orchestration.nodes.get_requirement_analysis_service") as mock_get_analysis_svc,
        patch("app.orchestration.nodes.get_test_case_generation_provider", return_value=MockTestCaseProvider()),
        patch("app.services.workflow_service.WorkflowService._get_checkpointer", return_value=checkpointer),
    ):
        mock_svc = MagicMock()
        mock_svc.analyze.return_value = sample_requirement_analysis()
        mock_get_analysis_svc.return_value = mock_svc

        # 1. Start workflow via POST
        start_res = client.post(
            f"/api/v1/projects/{proj.id}/workflows",
            json={"requirement_id": str(req.id), "notes": "E2E API test run"},
        )
        assert start_res.status_code == 201
        data = start_res.json()
        wf_id = data["id"]
        assert data["status"] == "paused_for_approval"
        assert data["current_stage"] == "human_approval"
        assert len(data["generated_test_case_ids"]) > 0

        # 2. GET workflow status
        get_res = client.get(f"/api/v1/projects/{proj.id}/workflows/{wf_id}")
        assert get_res.status_code == 200
        detail = get_res.json()
        assert detail["id"] == wf_id
        assert detail["status"] == "paused_for_approval"
        assert len(detail["generated_test_cases"]) > 0

        # 3. GET workflow history
        history_res = client.get(f"/api/v1/projects/{proj.id}/workflows/{wf_id}/history")
        assert history_res.status_code == 200
        events = history_res.json()["events"]
        assert len(events) >= 2
        assert any(e["event_type"] == "workflow_started" for e in events)
        assert any(e["event_type"] == "approval_required" for e in events)

        # 4. POST approval rejection
        approval_res = client.post(
            f"/api/v1/projects/{proj.id}/workflows/{wf_id}/approval",
            json={"action": "reject", "notes": "Rejected via API test."},
        )
        assert approval_res.status_code == 200
        approved_data = approval_res.json()
        assert approved_data["status"] == "rejected"


# ==============================================================================
# SECTION E: Concurrency, Idempotency, Checkpoint Recovery & Schema Validation
# ==============================================================================


def test_workflow_approval_request_schema_validation() -> None:
    """Verifies Pydantic schema validation on approval decisions and revisions."""
    # 1. Valid approval
    req_approve = WorkflowApprovalRequest(action=WorkflowApprovalAction.APPROVE, notes="Looks good")
    assert req_approve.action == WorkflowApprovalAction.APPROVE
    assert req_approve.revision_instructions is None

    # 2. Valid revision request
    req_rev = WorkflowApprovalRequest(
        action=WorkflowApprovalAction.REQUEST_REVISION,
        revision_instructions="Add boundary value test cases for negative order quantities.",
    )
    assert req_rev.action == WorkflowApprovalAction.REQUEST_REVISION
    assert "boundary value" in (req_rev.revision_instructions or "")

    # 3. Invalid revision request: missing or empty instructions
    with pytest.raises(ValidationError):
        WorkflowApprovalRequest(
            action=WorkflowApprovalAction.REQUEST_REVISION,
            revision_instructions="",
        )

    # 4. Invalid revision request: whitespace only
    with pytest.raises(ValidationError):
        WorkflowApprovalRequest(
            action=WorkflowApprovalAction.REQUEST_REVISION,
            revision_instructions="    ",
        )


def test_active_workflow_conflict_prevention() -> None:
    """Verifies that start_workflow raises ResourceConflictError if an active workflow exists for the requirement."""
    mock_db = MagicMock()
    mock_project_service = MagicMock()
    mock_req_service = MagicMock()

    proj_id = uuid4()
    req_id = uuid4()

    existing_active_wf = WorkflowExecution(
        id=uuid4(),
        project_id=proj_id,
        requirement_id=req_id,
        thread_id=str(uuid4()),
        status=WorkflowStatus.PAUSED_FOR_APPROVAL,
        current_stage=WorkflowStage.HUMAN_APPROVAL.value,
        approval_status="pending",
    )

    # Mock DB query to return the active workflow
    mock_db.scalar.return_value = existing_active_wf

    wf_service = WorkflowService(db=mock_db)

    with (
        patch("app.services.workflow_service.ProjectService", return_value=mock_project_service),
        patch("app.services.workflow_service.RequirementService", return_value=mock_req_service),
    ):
        with pytest.raises(ResourceConflictError) as exc_info:
            wf_service.start_workflow(project_id=proj_id, requirement_id=req_id)

        assert "already in state 'paused_for_approval'" in str(exc_info.value)


def test_concurrent_decision_row_locking_conflict() -> None:
    """
    Verifies that submit_approval rejects decision submission when the workflow
    is already in RUNNING or COMPLETED state, simulating a concurrent or duplicate submission.
    """
    mock_db = MagicMock()
    proj_id = uuid4()
    wf_id = uuid4()

    # Simulate that another request locked the row and changed its status to RUNNING
    already_running_wf = WorkflowExecution(
        id=wf_id,
        project_id=proj_id,
        requirement_id=uuid4(),
        thread_id=str(uuid4()),
        status=WorkflowStatus.RUNNING,
        current_stage=WorkflowStage.TEST_EXECUTION.value,
        approval_status="approved",
    )

    mock_db.scalar.return_value = already_running_wf
    wf_service = WorkflowService(db=mock_db)

    with pytest.raises(ResourceConflictError) as exc_info:
        wf_service.submit_approval(
            project_id=proj_id,
            workflow_id=wf_id,
            action=WorkflowApprovalAction.REJECT,
            notes="Late rejection attempt",
        )

    assert "cannot receive approval in state 'running'" in str(exc_info.value)


def test_checkpoint_state_restoration_and_recovery() -> None:
    """
    Verifies LangGraph checkpoint persistence and restart recovery:
    1. Compiles graph with a checkpointer.
    2. Runs graph until human_approval interrupt.
    3. Recreates graph instance (simulating backend process restart) with the same checkpointer.
    4. Retrieves checkpoint state for the thread, verifying state is completely preserved.
    5. Resumes graph from restored checkpoint and completes execution.
    """
    checkpointer = MemorySaver()
    thread_id = str(uuid4())
    config = {"configurable": {"thread_id": thread_id}}

    initial_state: WorkflowGraphState = {
        "workflow_id": str(uuid4()),
        "project_id": str(uuid4()),
        "requirement_id": str(uuid4()),
        "thread_id": thread_id,
        "status": WorkflowStatus.RUNNING.value,
        "current_stage": WorkflowStage.INITIALIZATION.value,
        "generated_test_case_ids": ["case-101", "case-102"],
        "execution_ids": [],
    }

    # Mock the upstream nodes and compile graph1 so patched nodes are registered
    with (
        patch("app.orchestration.graph.validate_context_node", return_value={"current_stage": "validate_context"}),
        patch("app.orchestration.graph.requirement_analysis_node", return_value={"current_stage": "requirement_analysis"}),
        patch("app.orchestration.graph.test_case_generation_node", return_value={"current_stage": "test_case_generation", "generated_test_case_ids": ["case-101", "case-102"]}),
    ):
        graph1 = compile_workflow_graph(checkpointer=checkpointer)
        graph1.invoke(initial_state, config=config)

    # Verify paused at human_approval in instance 1
    snapshot1 = graph1.get_state(config)
    assert snapshot1.next == ("human_approval",)
    assert snapshot1.values["generated_test_case_ids"] == ["case-101", "case-102"]

    # Resume Instance 2 with rejection decision
    decision = {
        "action": WorkflowApprovalAction.REJECT.value,
        "notes": "Recovered workflow rejected after restart",
        "submitted_at": datetime.now(timezone.utc).isoformat(),
    }

    with (
        patch("app.orchestration.graph.record_rejection_node", return_value={
            "status": WorkflowStatus.REJECTED.value,
            "current_stage": "rejected",
        }),
    ):
        # Instance 2: Simulate backend restart by creating a completely new compiled graph
        graph2 = compile_workflow_graph(checkpointer=checkpointer)
        snapshot2 = graph2.get_state(config)

        # State must be identically recovered across restart
        assert snapshot2.next == ("human_approval",)
        assert snapshot2.values["thread_id"] == thread_id
        assert snapshot2.values["generated_test_case_ids"] == ["case-101", "case-102"]

        from langgraph.types import Command
        resumed_state = graph2.invoke(Command(resume=decision), config=config)

    assert resumed_state["status"] == WorkflowStatus.REJECTED.value
    assert resumed_state["current_stage"] == "rejected"

