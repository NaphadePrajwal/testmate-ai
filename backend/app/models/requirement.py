from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, Enum, ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID as PostgreSQLUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base
from app.models.enums import RequirementStatus, enum_values


class Requirement(Base):
    """A project requirement that provides traceability for generated test cases."""

    __tablename__ = "requirements"
    __table_args__ = (UniqueConstraint("project_id", "title", name="uq_requirements_project_title"),)

    id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), primary_key=True, default=uuid4)
    project_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True), ForeignKey("projects.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[RequirementStatus] = mapped_column(
        Enum(RequirementStatus, native_enum=False, create_constraint=True, values_callable=enum_values),
        nullable=False,
        default=RequirementStatus.DRAFT,
        index=True,
    )
    acceptance_criteria: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    project: Mapped["Project"] = relationship(back_populates="requirements")
    test_cases: Mapped[list["TestCase"]] = relationship(back_populates="requirement", passive_deletes=True)
