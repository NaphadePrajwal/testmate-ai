from datetime import datetime, timezone
import logging
from typing import Any
from uuid import UUID, uuid4

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.types import Command
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.exceptions import ResourceConflictError, ResourceNotFoundError
from app.models.enums import ReviewStatus, WorkflowApprovalAction, WorkflowStage, WorkflowStatus
from app.models.execution_failure_analysis import ExecutionFailureAnalysis
from app.models.project import Project
from app.models.requirement import Requirement
from app.models.test_case import TestCase
from app.models.test_execution import TestExecution
from app.models.workflow_execution import WorkflowEvent, WorkflowExecution
from app.orchestration.graph import compile_workflow_graph, get_default_postgres_checkpointer
from app.schemas.execution import ExecutionRead
from app.schemas.failure_analysis import ExecutionFailureAnalysisRead
from app.schemas.test_case import TestCaseRead
from app.schemas.workflow import WorkflowDetailRead, WorkflowEventRead, WorkflowRead
from app.services.database import commit_and_refresh, commit_or_rollback
from app.services.project_service import ProjectService
from app.services.requirement_service import RequirementService

logger = logging.getLogger(__name__)


class WorkflowService:
    """
    Manages workflow lifecycle, execution coordination through LangGraph,
    authoritative PostgreSQL persistence, and event logging.
    """

    def __init__(self, db: Session, checkpointer: BaseCheckpointSaver | None = None) -> None:
        self.db = db
        self.checkpointer = checkpointer

    def _get_checkpointer(self) -> BaseCheckpointSaver:
        if self.checkpointer is not None:
            return self.checkpointer
        return get_default_postgres_checkpointer()

    def _record_event(
        self,
        workflow_id: UUID,
        stage: str,
        event_type: str,
        message: str,
        payload: dict[str, Any] | None = None,
    ) -> WorkflowEvent:
        event = WorkflowEvent(
            id=uuid4(),
            workflow_id=workflow_id,
            stage=stage,
            event_type=event_type,
            message=message,
            payload=payload or {},
            created_at=datetime.now(timezone.utc),
        )
        self.db.add(event)
        commit_or_rollback(self.db)
        return event

    def start_workflow(
        self,
        project_id: UUID,
        requirement_id: UUID,
        notes: str | None = None,
    ) -> WorkflowExecution:
        """
        Initializes and runs the multi-agent graph until the first checkpoint (Human Approval).
        """
        # Validate existence and ownership
        ProjectService(self.db).get_project(project_id)
        requirement = RequirementService(self.db).get_requirement(project_id, requirement_id)

        # Check for active existing workflow to prevent concurrent duplicate executions
        active_wf = self.db.scalar(
            select(WorkflowExecution).where(
                WorkflowExecution.project_id == project_id,
                WorkflowExecution.requirement_id == requirement_id,
                WorkflowExecution.status.in_([WorkflowStatus.RUNNING, WorkflowStatus.PAUSED_FOR_APPROVAL]),
            )
        )
        if active_wf is not None:
            raise ResourceConflictError(
                f"An active workflow (ID: {active_wf.id}) is already in state '{active_wf.status.value}' for this requirement."
            )

        thread_id = str(uuid4())
        workflow_id = uuid4()

        wf = WorkflowExecution(
            id=workflow_id,
            project_id=project_id,
            requirement_id=requirement_id,
            thread_id=thread_id,
            status=WorkflowStatus.RUNNING,
            current_stage=WorkflowStage.INITIALIZATION.value,
            approval_status="pending",
            approval_decision={},
            generated_test_case_ids=[],
            execution_ids=[],
            metadata_={"notes": notes} if notes else {},
        )
        self.db.add(wf)
        commit_and_refresh(self.db, wf)

        self._record_event(
            workflow_id=wf.id,
            stage=WorkflowStage.INITIALIZATION.value,
            event_type="workflow_started",
            message=f"Started workflow for requirement '{requirement.title}'",
            payload={"requirement_id": str(requirement_id), "notes": notes},
        )

        # Compile and execute graph
        checkpointer = self._get_checkpointer()
        graph = compile_workflow_graph(checkpointer=checkpointer)

        initial_state = {
            "workflow_id": str(wf.id),
            "project_id": str(project_id),
            "requirement_id": str(requirement_id),
            "thread_id": thread_id,
            "status": WorkflowStatus.RUNNING.value,
            "current_stage": WorkflowStage.INITIALIZATION.value,
            "generated_test_case_ids": [],
            "execution_ids": [],
        }
        config = {"configurable": {"thread_id": thread_id}}

        from app.orchestration.nodes import set_db_factory_override

        set_db_factory_override(lambda: self.db)
        try:
            # Invoking graph will run through analysis, generation, and pause at human_approval
            graph.invoke(initial_state, config=config)
            snapshot = graph.get_state(config)

            # Re-fetch wf within current session in case internal commits occurred
            wf = self.db.get(WorkflowExecution, workflow_id)

            # Check if paused at human_approval checkpoint
            if snapshot.next and "human_approval" in snapshot.next:
                case_ids = snapshot.values.get("generated_test_case_ids", [])
                wf.status = WorkflowStatus.PAUSED_FOR_APPROVAL
                wf.current_stage = WorkflowStage.HUMAN_APPROVAL.value
                wf.generated_test_case_ids = case_ids

                # Save analysis metadata
                if snapshot.values.get("requirement_analysis"):
                    meta = dict(wf.metadata_)
                    meta["requirement_analysis"] = snapshot.values.get("requirement_analysis")
                    meta["analysis_metadata"] = snapshot.values.get("analysis_metadata")
                    wf.metadata_ = meta

                self.db.commit()

                self._record_event(
                    workflow_id=workflow_id,
                    stage=WorkflowStage.HUMAN_APPROVAL.value,
                    event_type="approval_required",
                    message=f"Generated {len(case_ids)} test cases. Workflow paused for human approval.",
                    payload={"generated_test_case_ids": case_ids},
                )
            else:
                # Graph finished without interrupt
                final_status = snapshot.values.get("status", WorkflowStatus.COMPLETED.value)
                wf.status = WorkflowStatus(final_status)
                wf.current_stage = snapshot.values.get("current_stage", WorkflowStage.COMPLETED.value)
                wf.completed_at = datetime.now(timezone.utc)
                self.db.commit()

        except Exception as exc:
            logger.error("Error executing workflow %s: %s", workflow_id, exc, exc_info=True)
            wf = self.db.get(WorkflowExecution, workflow_id) or wf
            wf.status = WorkflowStatus.FAILED
            wf.current_stage = WorkflowStage.FAILED.value
            wf.error_message = str(exc)
            wf.completed_at = datetime.now(timezone.utc)
            self.db.commit()

            self._record_event(
                workflow_id=workflow_id,
                stage=WorkflowStage.FAILED.value,
                event_type="workflow_failed",
                message=f"Workflow failed: {exc}",
                payload={"error": str(exc)},
            )
            raise

        finally:
            set_db_factory_override(None)

        return wf


    def get_workflow(self, project_id: UUID, workflow_id: UUID) -> WorkflowExecution:
        wf = self.db.scalar(
            select(WorkflowExecution).where(
                WorkflowExecution.id == workflow_id,
                WorkflowExecution.project_id == project_id,
            )
        )
        if wf is None:
            raise ResourceNotFoundError("Workflow not found for this project.")
        return wf

    def get_workflow_detail(self, project_id: UUID, workflow_id: UUID) -> WorkflowDetailRead:
        wf = self.get_workflow(project_id, workflow_id)

        # Load Requirement Title
        requirement = self.db.scalar(select(Requirement).where(Requirement.id == wf.requirement_id))
        requirement_title = requirement.title if requirement else None

        # Load Test Cases
        case_uuids = [UUID(cid) for cid in wf.generated_test_case_ids if cid]
        cases: list[TestCase] = []
        if case_uuids:
            cases = list(
                self.db.scalars(
                    select(TestCase)
                    .where(TestCase.id.in_(case_uuids))
                    .order_by(TestCase.created_at.asc())
                )
            )

        # Load Executions
        exec_uuids = [UUID(eid) for eid in wf.execution_ids if eid]
        executions: list[TestExecution] = []
        if exec_uuids:
            executions = list(
                self.db.scalars(
                    select(TestExecution)
                    .where(TestExecution.id.in_(exec_uuids))
                    .order_by(TestExecution.created_at.asc())
                )
            )

        # Load Failure Analysis
        failure_analysis_read = None
        if wf.failure_analysis_id:
            fa = self.db.scalar(
                select(ExecutionFailureAnalysis).where(ExecutionFailureAnalysis.id == wf.failure_analysis_id)
            )
            if fa:
                failure_analysis_read = ExecutionFailureAnalysisRead.model_validate(fa)

        # Load Events
        events = list(
            self.db.scalars(
                select(WorkflowEvent)
                .where(WorkflowEvent.workflow_id == wf.id)
                .order_by(WorkflowEvent.created_at.asc())
            )
        )

        return WorkflowDetailRead(
            id=wf.id,
            project_id=wf.project_id,
            requirement_id=wf.requirement_id,
            thread_id=wf.thread_id,
            status=wf.status,
            current_stage=wf.current_stage,
            approval_status=wf.approval_status,
            approval_decision=wf.approval_decision,
            generated_test_case_ids=wf.generated_test_case_ids,
            execution_ids=wf.execution_ids,
            failure_analysis_id=wf.failure_analysis_id,
            error_message=wf.error_message,
            metadata=wf.metadata_,
            created_at=wf.created_at,
            updated_at=wf.updated_at,
            completed_at=wf.completed_at,
            requirement_title=requirement_title,
            generated_test_cases=[TestCaseRead.model_validate(c) for c in cases],
            executions=[ExecutionRead.model_validate(e) for e in executions],
            failure_analysis=failure_analysis_read,
            events=[WorkflowEventRead.model_validate(ev) for ev in events],
        )

    def list_workflows(
        self,
        project_id: UUID,
        limit: int = 20,
        offset: int = 0,
        requirement_id: UUID | None = None,
    ) -> tuple[list[WorkflowExecution], int]:
        ProjectService(self.db).get_project(project_id)
        stmt = select(WorkflowExecution).where(WorkflowExecution.project_id == project_id)
        if requirement_id is not None:
            stmt = stmt.where(WorkflowExecution.requirement_id == requirement_id)
        total = self.db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
        items = list(
            self.db.scalars(stmt.order_by(WorkflowExecution.created_at.desc()).offset(offset).limit(limit))
        )
        return items, total

    def get_workflow_history(self, project_id: UUID, workflow_id: UUID) -> list[WorkflowEvent]:
        self.get_workflow(project_id, workflow_id)
        return list(
            self.db.scalars(
                select(WorkflowEvent)
                .where(WorkflowEvent.workflow_id == workflow_id)
                .order_by(WorkflowEvent.created_at.asc())
            )
        )

    def submit_approval(
        self,
        project_id: UUID,
        workflow_id: UUID,
        action: WorkflowApprovalAction,
        notes: str | None = None,
        revision_instructions: str | None = None,
    ) -> WorkflowExecution:
        """
        Resumes the paused LangGraph workflow with the user's approval decision.
        Uses database row locking to guarantee serialized handling of concurrent decisions.
        """
        if action == WorkflowApprovalAction.REQUEST_REVISION:
            if not revision_instructions or not revision_instructions.strip():
                raise ValueError("revision_instructions cannot be empty when action is 'request_revision'.")

        wf = self.db.scalar(
            select(WorkflowExecution)
            .where(
                WorkflowExecution.id == workflow_id,
                WorkflowExecution.project_id == project_id,
            )
            .with_for_update()
        )
        if wf is None:
            raise ResourceNotFoundError("Workflow not found for this project.")

        # Validate that workflow is paused at approval
        if wf.status != WorkflowStatus.PAUSED_FOR_APPROVAL:
            raise ResourceConflictError(
                f"Workflow cannot receive approval in state '{wf.status.value}'. Must be 'paused_for_approval'."
            )

        # Prepare decision
        decision_data = {
            "action": action.value,
            "notes": notes,
            "revision_instructions": revision_instructions.strip() if revision_instructions else None,
            "submitted_at": datetime.now(timezone.utc).isoformat(),
        }
        wf.status = WorkflowStatus.RUNNING
        wf.approval_status = action.value
        wf.approval_decision = decision_data
        self.db.commit()

        self._record_event(
            workflow_id=wf.id,
            stage=WorkflowStage.HUMAN_APPROVAL.value,
            event_type="decision_submitted",
            message=f"Human reviewer submitted decision: '{action.value}'.",
            payload=decision_data,
        )

        checkpointer = self._get_checkpointer()
        graph = compile_workflow_graph(checkpointer=checkpointer)
        config = {"configurable": {"thread_id": wf.thread_id}}

        from app.orchestration.nodes import set_db_factory_override

        set_db_factory_override(lambda: self.db)
        try:
            resume_cmd = Command(resume=decision_data)
            final_state = graph.invoke(resume_cmd, config=config)

            # Re-fetch wf within current session in case internal commits occurred
            wf = self.db.get(WorkflowExecution, workflow_id)

            # Check if paused again (e.g. revision requested -> regenerated -> paused for review again)
            snapshot = graph.get_state(config)
            if snapshot.next and "human_approval" in snapshot.next:
                new_case_ids = snapshot.values.get("generated_test_case_ids", [])
                wf.status = WorkflowStatus.PAUSED_FOR_APPROVAL
                wf.current_stage = WorkflowStage.HUMAN_APPROVAL.value
                wf.generated_test_case_ids = new_case_ids
                self.db.commit()

                self._record_event(
                    workflow_id=workflow_id,
                    stage=WorkflowStage.HUMAN_APPROVAL.value,
                    event_type="approval_required",
                    message="Revised test cases generated. Workflow paused for re-approval.",
                    payload={"generated_test_case_ids": new_case_ids},
                )
                return wf

            # Update final workflow state
            wf.status = WorkflowStatus(final_state.get("status", WorkflowStatus.COMPLETED.value))
            wf.current_stage = final_state.get("current_stage", WorkflowStage.COMPLETED.value)
            wf.execution_ids = final_state.get("execution_ids", [])

            if final_state.get("failure_analysis_id"):
                wf.failure_analysis_id = UUID(final_state["failure_analysis_id"])

            wf.completed_at = datetime.now(timezone.utc)
            meta = dict(wf.metadata_)
            if "historical_candidates" in final_state:
                meta["historical_candidates_count"] = len(final_state.get("historical_candidates", []))
                meta["retrieval_status"] = final_state.get("retrieval_status")
            wf.metadata_ = meta

            self.db.commit()

            self._record_event(
                workflow_id=workflow_id,
                stage=wf.current_stage,
                event_type="workflow_completed",
                message=f"Workflow completed with final status '{wf.status.value}'.",
                payload={
                    "status": wf.status.value,
                    "execution_ids": wf.execution_ids,
                    "failure_analysis_id": str(wf.failure_analysis_id) if wf.failure_analysis_id else None,
                },
            )

        except Exception as exc:
            logger.error("Error resuming workflow %s: %s", workflow_id, exc, exc_info=True)
            wf = self.db.get(WorkflowExecution, workflow_id) or wf
            wf.status = WorkflowStatus.FAILED
            wf.current_stage = WorkflowStage.FAILED.value
            wf.error_message = str(exc)
            wf.completed_at = datetime.now(timezone.utc)
            self.db.commit()

            self._record_event(
                workflow_id=workflow_id,
                stage=WorkflowStage.FAILED.value,
                event_type="workflow_failed",
                message=f"Workflow resumption failed: {exc}",
                payload={"error": str(exc)},
            )
            raise
        finally:
            set_db_factory_override(None)

        return wf

