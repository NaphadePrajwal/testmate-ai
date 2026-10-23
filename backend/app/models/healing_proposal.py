from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import DateTime, Enum, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID as PostgreSQLUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base
from app.models.enums import HealingStatus, enum_values


class HealingProposal(Base):
    """
    Persistent record of a self-healing attempt for a broken test step selector.
    Tracks detection, candidate generation & live validation, human approval,
    repair application, and retry execution verification.
    """

    __tablename__ = "healing_proposals"

    id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), primary_key=True, default=uuid4)
    project_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    test_case_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True), ForeignKey("test_cases.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    original_execution_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True), ForeignKey("test_executions.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    retry_execution_id: Mapped[UUID | None] = mapped_column(
        PostgreSQLUUID(as_uuid=True), ForeignKey("test_executions.id", ondelete="SET NULL"), nullable=True, index=True
    )
    step_index: Mapped[int] = mapped_column(Integer, nullable=False)
    action_type: Mapped[str] = mapped_column(String(50), nullable=False)
    original_selector: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    proposed_selector: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    approved_selector: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    status: Mapped[HealingStatus] = mapped_column(
        Enum(HealingStatus, native_enum=False, create_constraint=True, values_callable=enum_values),
        nullable=False,
        default=HealingStatus.DETECTED,
        index=True,
    )
    failure_reason: Mapped[str] = mapped_column(Text, nullable=False)
    failure_category: Mapped[str] = mapped_column(String(100), nullable=False, default="element_not_found")
    page_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    page_title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    dom_context: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    candidate_validation_results: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    explanation: Mapped[str | None] = mapped_column(Text, nullable=True)
    decision_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    approved_by: Mapped[str | None] = mapped_column(String(100), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    repaired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    # Relationships
    project: Mapped["Project"] = relationship()
    test_case: Mapped["TestCase"] = relationship(back_populates="healing_proposals")
    original_execution: Mapped["TestExecution"] = relationship(
        foreign_keys=[original_execution_id], back_populates="healing_proposals"
    )
    retry_execution: Mapped["TestExecution | None"] = relationship(
        foreign_keys=[retry_execution_id], back_populates="healing_retries"
    )
