import logging
from typing import Any

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.graph import END, START, StateGraph

from app.core.config import get_settings
from app.models.enums import WorkflowApprovalAction
from app.orchestration.nodes import (
    apply_revision_node,
    failure_analysis_node,
    handle_error_node,
    historical_rag_node,
    human_approval_node,
    record_rejection_node,
    record_success_node,
    requirement_analysis_node,
    test_case_generation_node,
    test_execution_node,
    validate_approval_node,
    validate_context_node,
)
from app.orchestration.state import WorkflowGraphState

logger = logging.getLogger(__name__)


def route_approval(state: WorkflowGraphState) -> str:
    """
    Conditional routing function evaluating human approval decision.
    Routes to execution on 'approve', rejection termination on 'reject',
    or revision regeneration on 'request_revision'.
    """
    action = state.get("approval_status")
    if action == WorkflowApprovalAction.APPROVE.value:
        return "validate_approval"
    elif action == WorkflowApprovalAction.REJECT.value:
        return "record_rejection"
    elif action == WorkflowApprovalAction.REQUEST_REVISION.value:
        return "apply_revision"
    logger.warning("Unrecognized approval action '%s', routing to handle_error", action)
    return "handle_error"


def route_execution_outcome(state: WorkflowGraphState) -> str:
    """
    Conditional routing evaluating actual test execution outcomes.
    If all executions pass -> record_success (skips RAG & failure analysis).
    If any failures/errors occur -> routes through historical RAG and failure analysis.
    """
    failed = state.get("failed_count", 0)
    error = state.get("error_count", 0)

    if failed > 0 or error > 0:
        logger.info("Executions encountered failures (failed=%d, error=%d). Routing to historical RAG.", failed, error)
        return "historical_rag"

    logger.info("All executions passed successfully. Routing to record_success.")
    return "record_success"


def build_workflow_graph() -> StateGraph:
    """
    Constructs the uncompiled LangGraph StateGraph connecting all multi-agent stages.
    """
    workflow = StateGraph(WorkflowGraphState)

    # Register Nodes
    workflow.add_node("validate_context", validate_context_node)
    workflow.add_node("requirement_analysis", requirement_analysis_node)
    workflow.add_node("test_case_generation", test_case_generation_node)
    workflow.add_node("human_approval", human_approval_node)
    workflow.add_node("apply_revision", apply_revision_node)
    workflow.add_node("record_rejection", record_rejection_node)
    workflow.add_node("validate_approval", validate_approval_node)
    workflow.add_node("test_execution", test_execution_node)
    workflow.add_node("record_success", record_success_node)
    workflow.add_node("historical_rag", historical_rag_node)
    workflow.add_node("failure_analysis", failure_analysis_node)
    workflow.add_node("handle_error", handle_error_node)

    # Core Sequential Edges
    workflow.add_edge(START, "validate_context")
    workflow.add_edge("validate_context", "requirement_analysis")
    workflow.add_edge("requirement_analysis", "test_case_generation")
    workflow.add_edge("test_case_generation", "human_approval")

    # Conditional Routing from Human Approval Checkpoint
    workflow.add_conditional_edges(
        "human_approval",
        route_approval,
        {
            "validate_approval": "validate_approval",
            "record_rejection": "record_rejection",
            "apply_revision": "apply_revision",
            "handle_error": "handle_error",
        },
    )

    # Revision Loop: apply revision -> regenerate test cases -> approval checkpoint
    workflow.add_edge("apply_revision", "test_case_generation")

    # Rejection Terminal Edge
    workflow.add_edge("record_rejection", END)

    # Approval to Execution Edge
    workflow.add_edge("validate_approval", "test_execution")

    # Conditional Routing from Execution Outcomes
    workflow.add_conditional_edges(
        "test_execution",
        route_execution_outcome,
        {
            "historical_rag": "historical_rag",
            "record_success": "record_success",
        },
    )

    # Success Terminal Edge
    workflow.add_edge("record_success", END)

    # Failure Diagnostics Path
    workflow.add_edge("historical_rag", "failure_analysis")
    workflow.add_edge("failure_analysis", END)

    # Error Terminal Edge
    workflow.add_edge("handle_error", END)

    return workflow


_checkpointer_conn: Any = None


def get_default_postgres_checkpointer() -> PostgresSaver:
    """Creates a production Postgres checkpointer using application database settings."""
    global _checkpointer_conn
    import psycopg
    from psycopg.rows import dict_row

    settings = get_settings()
    conn_str = settings.database_url.replace("postgresql+psycopg://", "postgresql://")
    if _checkpointer_conn is None or getattr(_checkpointer_conn, "closed", True):
        _checkpointer_conn = psycopg.connect(
            conn_str,
            autocommit=True,
            prepare_threshold=0,
            row_factory=dict_row,
        )
    checkpointer = PostgresSaver(_checkpointer_conn)
    checkpointer.setup()
    return checkpointer


def compile_workflow_graph(checkpointer: BaseCheckpointSaver | None = None) -> Any:
    """
    Compiles the workflow graph with persistent checkpointing.
    """
    graph = build_workflow_graph()
    if checkpointer is not None:
        return graph.compile(checkpointer=checkpointer)
    return graph.compile()
