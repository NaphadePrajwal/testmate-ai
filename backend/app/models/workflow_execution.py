from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import DateTime, Enum, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID as PostgreSQLUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base
from app.models.enums import WorkflowStatus, enum_values


class WorkflowExecution(Base):
    """
    Authoritative persistent record of a LangGraph multi-agent workflow run.
    Stores lifecycle status, project isolation boundaries, and domain references.
    """

    __tablename__ = "workflow_executions"

    id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), primary_key=True, default=uuid4)
    project_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    requirement_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True), ForeignKey("requirements.id", ondelete="CASCADE"), nullable=False, index=True
    )
    thread_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    status: Mapped[WorkflowStatus] = mapped_column(
        Enum(WorkflowStatus, native_enum=False, create_constraint=True, values_callable=enum_values),
        nullable=False,
        index=True,
        default=WorkflowStatus.PENDING,
    )
    current_stage: Mapped[str] = mapped_column(String(100), nullable=False, default="initialization")
    approval_status: Mapped[str] = mapped_column(String(50), nullable=False, default="pending")
    approval_decision: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    generated_test_case_ids: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    execution_ids: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    failure_analysis_id: Mapped[UUID | None] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("execution_failure_analyses.id", ondelete="SET NULL"),
        nullable=True,
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_: Mapped[dict[str, Any]] = mapped_column("metadata", JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    project: Mapped["Project"] = relationship("Project")
    requirement: Mapped["Requirement"] = relationship("Requirement")
    events: Mapped[list["WorkflowEvent"]] = relationship(
        "WorkflowEvent",
        back_populates="workflow",
        cascade="all, delete-orphan",
        order_by="WorkflowEvent.created_at.asc()",
    )


class WorkflowEvent(Base):
    """
    Append-only timeline audit log of state transitions within a LangGraph workflow.
    """

    __tablename__ = "workflow_events"

    id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), primary_key=True, default=uuid4)
    workflow_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("workflow_executions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    stage: Mapped[str] = mapped_column(String(100), nullable=False)
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    workflow: Mapped["WorkflowExecution"] = relationship("WorkflowExecution", back_populates="events")
