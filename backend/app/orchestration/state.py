from typing import Any, TypedDict


class WorkflowGraphState(TypedDict, total=False):
    """
    Typed, validated shared state passed between LangGraph agent nodes.
    Maintains workflow identity, agent outputs, checkpoints, and execution results.
    """

    # Identifiers & Isolation
    workflow_id: str
    project_id: str
    requirement_id: str
    thread_id: str

    # Lifecycle & Stage
    status: str
    current_stage: str

    # Requirement Context & Analysis Output
    requirement_title: str
    requirement_description: str
    requirement_acceptance_criteria: str | None
    requirement_target_url: str | None
    requirement_analysis: dict[str, Any] | None
    analysis_metadata: dict[str, Any] | None

    # Test Case Generation Output
    generated_test_case_ids: list[str]
    generated_test_cases_summary: str | None
    generation_metadata: dict[str, Any] | None

    # Human Approval Checkpoint
    approval_status: str  # pending, approve, reject, request_revision
    approval_decision: dict[str, Any] | None
    revision_instructions: str | None
    revision_count: int

    # Test Execution Integration
    execution_ids: list[str]
    execution_results: list[dict[str, Any]]
    passed_count: int
    failed_count: int
    error_count: int
    failed_execution_id: str | None

    # Historical RAG Retrieval
    historical_candidates: list[dict[str, Any]]
    retrieval_status: str  # success, no_matches, failed, not_attempted
    retrieval_query: str | None
    retrieval_error: str | None

    # Failure Analysis Diagnosis
    failure_analysis_id: str | None
    failure_analysis_result: dict[str, Any] | None
    defect_ids: list[str]

    # Error Handling & Timeline
    error_message: str | None
    error_stage: str | None
    stage_history: list[dict[str, Any]]
