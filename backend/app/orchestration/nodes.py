from datetime import datetime, timezone
import logging
from typing import Any, Callable
from uuid import UUID

from langgraph.types import interrupt
from sqlalchemy.orm import Session

from app.core.exceptions import ResourceConflictError, ResourceNotFoundError
from app.db.session import SessionLocal
from app.models.enums import ReviewStatus, WorkflowApprovalAction, WorkflowStage, WorkflowStatus
from app.models.requirement import Requirement
from app.models.test_case import TestCase
from app.models.test_execution import TestExecution
from app.orchestration.state import WorkflowGraphState
from app.schemas.failure_analysis import FailureCategory
from app.schemas.requirement_analysis import RequirementAnalysis
from app.services.database import commit_or_rollback
from app.services.execution_service import ExecutionService
from app.services.failure_analysis_service import (
    FailureAnalysisService,
    extract_failure_search_query,
    get_failure_analysis_provider,
)
from app.services.knowledge_retrieval_service import KnowledgeRetrievalService
from app.services.project_service import ProjectService
from app.services.requirement_analysis_service import get_requirement_analysis_service
from app.services.requirement_service import RequirementService
from app.services.test_case_generation_service import (
    TestCaseGenerationService,
    get_test_case_generation_provider,
)
from app.services.test_case_service import TestCaseService

logger = logging.getLogger(__name__)

from contextlib import contextmanager

# Test injection hooks
_db_factory_override: Callable[[], Session] | None = None


def set_db_factory_override(fn: Callable[[], Session] | None) -> None:
    global _db_factory_override
    _db_factory_override = fn


@contextmanager
def get_db():
    if _db_factory_override is not None:
        yield _db_factory_override()
    else:
        db = SessionLocal()
        try:
            yield db
        finally:
            db.close()



def validate_context_node(state: WorkflowGraphState) -> dict[str, Any]:
    """
    Node 1: Load and Validate Project & Requirement Context.
    Ensures requirement exists and belongs to the specified project.
    """
    project_id = UUID(state["project_id"])
    requirement_id = UUID(state["requirement_id"])

    with get_db() as db:
        ProjectService(db).get_project(project_id)
        requirement = RequirementService(db).get_requirement(project_id, requirement_id)

        return {
            "requirement_title": requirement.title,
            "requirement_description": requirement.description,
            "requirement_acceptance_criteria": requirement.acceptance_criteria,
            "requirement_target_url": requirement.target_url,
            "current_stage": WorkflowStage.INITIALIZATION.value,
            "status": WorkflowStatus.RUNNING.value,
        }


def requirement_analysis_node(state: WorkflowGraphState) -> dict[str, Any]:
    """
    Node 2: Requirement Analysis Agent.
    Invokes existing requirement analysis service to parse requirements, extract scope,
    identify edge cases, and evaluate risk.
    """
    project_id = UUID(state["project_id"])
    requirement_id = UUID(state["requirement_id"])

    with get_db() as db:
        requirement = RequirementService(db).get_requirement(project_id, requirement_id)
        analysis_service = get_requirement_analysis_service()
        analysis_result = analysis_service.analyze(requirement)

        # Validate structured output
        analysis_dict = analysis_result.analysis.model_dump(mode="json")
        metadata_dict = analysis_result.metadata.model_dump(mode="json")

        return {
            "requirement_analysis": analysis_dict,
            "analysis_metadata": metadata_dict,
            "current_stage": WorkflowStage.REQUIREMENT_ANALYSIS.value,
        }


def test_case_generation_node(state: WorkflowGraphState) -> dict[str, Any]:
    """
    Node 3: Test Case Generation Agent.
    Consumes requirement and validated analysis from shared state to produce structured test cases.
    If revision instructions are present in state, incorporates them.
    """
    project_id = UUID(state["project_id"])
    requirement_id = UUID(state["requirement_id"])
    revision_instructions = state.get("revision_instructions")

    with get_db() as db:
        provider = get_test_case_generation_provider()
        gen_service = TestCaseGenerationService(db, provider)

        response = gen_service.generate_for_requirement(
            project_id=project_id,
            requirement_id=requirement_id,
            instructions=revision_instructions,
        )

        case_ids = [str(item.id) for item in response.items]

        return {
            "generated_test_case_ids": case_ids,
            "generated_test_cases_summary": response.requirement_coverage_summary,
            "generation_metadata": response.metadata.model_dump(mode="json") if response.metadata else None,
            "current_stage": WorkflowStage.TEST_CASE_GENERATION.value,
            "approval_status": "pending",
        }


def human_approval_node(state: WorkflowGraphState) -> dict[str, Any]:
    """
    Node 4: Human Approval Checkpoint.
    Pauses execution and persists state. Awaits resume input from an authorized user
    (approve, reject, or request_revision).
    """
    # Trigger LangGraph interrupt
    decision_payload = interrupt({
        "workflow_id": state["workflow_id"],
        "stage": "human_approval",
        "message": "Generated test cases require human review and approval before execution.",
        "generated_test_case_ids": state.get("generated_test_case_ids", []),
    })

    if not isinstance(decision_payload, dict):
        decision_payload = {"action": str(decision_payload)}

    action = decision_payload.get("action", WorkflowApprovalAction.REJECT.value)
    notes = decision_payload.get("notes")
    revision_instructions = decision_payload.get("revision_instructions")

    return {
        "approval_status": action,
        "approval_decision": {
            "action": action,
            "notes": notes,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
        "revision_instructions": revision_instructions,
        "current_stage": WorkflowStage.HUMAN_APPROVAL.value,
    }


def apply_revision_node(state: WorkflowGraphState) -> dict[str, Any]:
    """
    Handles revision request: increments revision counter and prepares state to loop back
    to test case generation.
    """
    rev_count = state.get("revision_count", 0) + 1
    return {
        "revision_count": rev_count,
        "approval_status": "pending",
        "current_stage": "revision_requested",
        "status": WorkflowStatus.REVISION_REQUESTED.value,
    }


def record_rejection_node(state: WorkflowGraphState) -> dict[str, Any]:
    """
    Handles rejection: marks generated test cases as rejected in the database
    and marks workflow as REJECTED without executing test cases.
    """
    project_id = UUID(state["project_id"])
    requirement_id = UUID(state["requirement_id"])
    case_ids = state.get("generated_test_case_ids", [])

    with get_db() as db:
        tc_service = TestCaseService(db)
        for cid_str in case_ids:
            try:
                tc_service.reject_requirement_test_case(project_id, requirement_id, UUID(cid_str))
            except Exception as exc:
                logger.warning("Could not mark test case %s as rejected: %s", cid_str, exc)

    return {
        "status": WorkflowStatus.REJECTED.value,
        "current_stage": "rejected",
    }


def validate_approval_node(state: WorkflowGraphState) -> dict[str, Any]:
    """
    Validates that test cases are approved. Marks test cases as APPROVED in the database
    so they become eligible for execution engine execution.
    """
    project_id = UUID(state["project_id"])
    requirement_id = UUID(state["requirement_id"])
    case_ids = state.get("generated_test_case_ids", [])

    with get_db() as db:
        tc_service = TestCaseService(db)
        for cid_str in case_ids:
            try:
                tc = tc_service.get_requirement_test_case(project_id, requirement_id, UUID(cid_str))
                if tc.review_status != ReviewStatus.APPROVED:
                    tc_service.approve_requirement_test_case(project_id, requirement_id, UUID(cid_str))
            except Exception as exc:
                logger.warning("Could not approve test case %s: %s", cid_str, exc)

    return {
        "status": WorkflowStatus.APPROVED.value,
        "current_stage": "approved",
    }


def test_execution_node(state: WorkflowGraphState) -> dict[str, Any]:
    """
    Node 5: Test Execution Integration.
    Executes approved test cases using the existing ExecutionService.
    Captures execution IDs and counts for conditional routing.
    """
    project_id = UUID(state["project_id"])
    case_ids = state.get("generated_test_case_ids", [])

    execution_ids: list[str] = []
    execution_results: list[dict[str, Any]] = []
    passed = 0
    failed = 0
    error = 0
    first_failed_id: str | None = None

    with get_db() as db:
        exec_service = ExecutionService(db)
        for cid_str in case_ids:
            try:
                execution = exec_service.execute_test_case(
                    project_id=project_id,
                    test_case_id=UUID(cid_str),
                    executor="LangGraph Orchestrator",
                )
                exec_id_str = str(execution.id)
                execution_ids.append(exec_id_str)

                status_val = execution.status.value if hasattr(execution.status, "value") else str(execution.status)
                result_info = {
                    "execution_id": exec_id_str,
                    "test_case_id": cid_str,
                    "status": status_val,
                    "error_message": execution.error_message,
                }
                execution_results.append(result_info)

                if status_val == "passed":
                    passed += 1
                elif status_val == "failed":
                    failed += 1
                    if first_failed_id is None:
                        first_failed_id = exec_id_str
                else:
                    error += 1
                    if first_failed_id is None:
                        first_failed_id = exec_id_str
            except Exception as exc:
                logger.error("Execution failed for test case %s: %s", cid_str, exc)
                error += 1
                execution_results.append({
                    "test_case_id": cid_str,
                    "status": "error",
                    "error_message": str(exc),
                })

    return {
        "execution_ids": execution_ids,
        "execution_results": execution_results,
        "passed_count": passed,
        "failed_count": failed,
        "error_count": error,
        "failed_execution_id": first_failed_id,
        "current_stage": WorkflowStage.TEST_EXECUTION.value,
    }


def record_success_node(state: WorkflowGraphState) -> dict[str, Any]:
    """
    All executions passed!
    Records successful completion, skipping historical RAG and failure analysis.
    """
    return {
        "status": WorkflowStatus.COMPLETED.value,
        "current_stage": WorkflowStage.COMPLETED.value,
        "retrieval_status": "not_attempted",
    }


def historical_rag_node(state: WorkflowGraphState) -> dict[str, Any]:
    """
    Node 6: Historical RAG Retrieval.
    Gathers failure context from the failed execution and queries project-scoped
    Qdrant vector knowledge.
    """
    project_id = UUID(state["project_id"])
    failed_id_str = state.get("failed_execution_id")

    if not failed_id_str:
        return {
            "historical_candidates": [],
            "retrieval_status": "not_attempted",
            "current_stage": WorkflowStage.HISTORICAL_RAG.value,
        }

    failed_exec_id = UUID(failed_id_str)
    candidates_data: list[dict[str, Any]] = []
    retrieval_status = "no_matches"
    retrieval_query = None
    retrieval_error = None

    with get_db() as db:
        try:
            exec_service = ExecutionService(db)
            context = exec_service.get_execution_for_analysis(project_id, failed_exec_id)
            retrieval_query = extract_failure_search_query(context)

            rag_service = KnowledgeRetrievalService(db=db)
            search_res = rag_service.search_project_knowledge(
                project_id=project_id,
                query=retrieval_query,
                limit=3,
            )
            if search_res.candidates:
                candidates_data = [c.model_dump(mode="json") for c in search_res.candidates]
                retrieval_status = "success"
        except Exception as exc:
            logger.warning("Historical knowledge retrieval failed in workflow: %s", exc)
            retrieval_status = "failed"
            retrieval_error = str(exc)

    return {
        "historical_candidates": candidates_data,
        "retrieval_status": retrieval_status,
        "retrieval_query": retrieval_query,
        "retrieval_error": retrieval_error,
        "current_stage": WorkflowStage.HISTORICAL_RAG.value,
    }


def failure_analysis_node(state: WorkflowGraphState) -> dict[str, Any]:
    """
    Node 7: Failure Analysis Agent.
    Consumes failed execution details and historical knowledge to diagnose root causes
    and generate actionable fix recommendations.
    """
    project_id = UUID(state["project_id"])
    failed_id_str = state.get("failed_execution_id")

    if not failed_id_str:
        return {
            "status": WorkflowStatus.COMPLETED.value,
            "current_stage": WorkflowStage.COMPLETED.value,
        }

    failed_exec_id = UUID(failed_id_str)
    analysis_id: str | None = None
    analysis_res_dict: dict[str, Any] | None = None
    defect_ids: list[str] = []

    with get_db() as db:
        fa_service = FailureAnalysisService(db)
        try:
            analysis = fa_service.get_or_create_analysis(project_id, failed_exec_id)
            analysis_id = str(analysis.id)
            analysis_res_dict = {
                "id": str(analysis.id),
                "failure_category": analysis.failure_category,
                "summary": analysis.summary,
                "likely_root_cause": analysis.likely_root_cause,
                "confidence": analysis.confidence,
                "recommended_debugging_steps": analysis.recommended_debugging_steps,
            }

            # Collect linked defects
            exec_detail = ExecutionService(db).get_execution_detail(project_id, failed_exec_id)
            defect_ids = [str(d.id) for d in exec_detail.defects]
        except Exception as exc:
            logger.error("Failure analysis node encountered error: %s", exc)

    return {
        "failure_analysis_id": analysis_id,
        "failure_analysis_result": analysis_res_dict,
        "defect_ids": defect_ids,
        "status": WorkflowStatus.COMPLETED.value,
        "current_stage": WorkflowStage.COMPLETED.value,
    }


def handle_error_node(state: WorkflowGraphState) -> dict[str, Any]:
    """
    Error Handler Node:
    Records sanitized failure information and marks workflow as FAILED.
    """
    return {
        "status": WorkflowStatus.FAILED.value,
        "current_stage": WorkflowStage.FAILED.value,
    }
