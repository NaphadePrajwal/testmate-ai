from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID as PostgreSQLUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


class ExecutionFailureAnalysis(Base):
    """Durable record of an AI root-cause failure analysis for a test execution."""

    __tablename__ = "execution_failure_analyses"

    id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), primary_key=True, default=uuid4)
    execution_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("test_executions.id", ondelete="RESTRICT"),
        nullable=False,
        unique=True,
        index=True,
    )
    project_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    failure_category: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    observed_error: Mapped[str] = mapped_column(Text, nullable=False)
    likely_root_cause: Mapped[str] = mapped_column(Text, nullable=False)
    supporting_evidence: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    recommended_debugging_steps: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    confidence: Mapped[str] = mapped_column(String(50), nullable=False, default="medium")
    uncertainty_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_: Mapped[dict[str, Any]] = mapped_column("metadata", JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    execution: Mapped["TestExecution"] = relationship(back_populates="failure_analysis")
