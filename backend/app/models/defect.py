from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, Enum, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import UUID as PostgreSQLUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base
from app.models.enums import DefectStatus, Severity, enum_values


class Defect(Base):
    """A durable defect record originating from a specific execution."""

    __tablename__ = "defects"

    id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), primary_key=True, default=uuid4)
    execution_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True), ForeignKey("test_executions.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    severity: Mapped[Severity] = mapped_column(
        Enum(Severity, native_enum=False, create_constraint=True, values_callable=enum_values), nullable=False, index=True
    )
    status: Mapped[DefectStatus] = mapped_column(
        Enum(DefectStatus, native_enum=False, create_constraint=True, values_callable=enum_values),
        nullable=False,
        default=DefectStatus.NEW,
        index=True,
    )
    fingerprint: Mapped[str | None] = mapped_column(String(255), unique=True, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    execution: Mapped["TestExecution"] = relationship(back_populates="defects")
