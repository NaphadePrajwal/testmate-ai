from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID as PostgreSQLUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base
from app.models.enums import Priority, TestCaseStatus, TestType, enum_values


class TestCase(Base):
    """A versioned test specification traced to exactly one requirement."""

    __tablename__ = "test_cases"
    __table_args__ = (UniqueConstraint("requirement_id", "title", name="uq_test_cases_requirement_title"),)

    id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), primary_key=True, default=uuid4)
    requirement_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True), ForeignKey("requirements.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    preconditions: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    steps: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)
    expected_result: Mapped[str] = mapped_column(Text, nullable=False)
    test_type: Mapped[TestType] = mapped_column(
        Enum(TestType, native_enum=False, create_constraint=True, values_callable=enum_values), nullable=False
    )
    priority: Mapped[Priority] = mapped_column(
        Enum(Priority, native_enum=False, create_constraint=True, values_callable=enum_values),
        nullable=False,
        default=Priority.MEDIUM,
        index=True,
    )
    status: Mapped[TestCaseStatus] = mapped_column(
        Enum(TestCaseStatus, native_enum=False, create_constraint=True, values_callable=enum_values),
        nullable=False,
        default=TestCaseStatus.DRAFT,
        index=True,
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    requirement: Mapped["Requirement"] = relationship(back_populates="test_cases")
    executions: Mapped[list["TestExecution"]] = relationship(back_populates="test_case", passive_deletes=True)
