from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import DateTime, Enum, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID as PostgreSQLUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base
from app.models.enums import ExecutionStatus, enum_values


class TestExecution(Base):
    """An immutable record of a test-case execution attempt."""

    __test__ = False
    __tablename__ = "test_executions"

    id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), primary_key=True, default=uuid4)
    test_case_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True), ForeignKey("test_cases.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    status: Mapped[ExecutionStatus] = mapped_column(
        Enum(ExecutionStatus, native_enum=False, create_constraint=True, values_callable=enum_values), nullable=False, index=True
    )
    executor: Mapped[str | None] = mapped_column(String(100), nullable=True)
    run_reference: Mapped[str | None] = mapped_column(String(255), unique=True, nullable=True)
    summary: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    test_case: Mapped["TestCase"] = relationship(back_populates="executions")
    evidence_items: Mapped[list["ExecutionEvidence"]] = relationship(back_populates="execution", passive_deletes=True)
    defects: Mapped[list["Defect"]] = relationship(back_populates="execution", passive_deletes=True)
