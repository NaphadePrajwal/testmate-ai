"""Add core testing workflow tables.

Revision ID: 20261004_0002
Revises: 20261004_0001
Create Date: 2026-10-04
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20261004_0002"
down_revision = "20261004_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    requirement_status = sa.Enum(
        "draft", "approved", "obsolete", name="requirementstatus", native_enum=False, create_constraint=True
    )
    test_case_status = sa.Enum(
        "draft", "approved", "retired", name="testcasestatus", native_enum=False, create_constraint=True
    )
    test_type = sa.Enum("web", "api", "manual", name="testtype", native_enum=False, create_constraint=True)
    priority = sa.Enum("low", "medium", "high", "critical", name="priority", native_enum=False, create_constraint=True)
    execution_status = sa.Enum(
        "queued", "running", "passed", "failed", "error", "cancelled",
        name="executionstatus", native_enum=False, create_constraint=True,
    )
    evidence_type = sa.Enum(
        "screenshot", "video", "log", "trace", "request_response",
        name="evidencetype", native_enum=False, create_constraint=True,
    )
    defect_status = sa.Enum("new", "triaged", "resolved", "closed", name="defectstatus", native_enum=False, create_constraint=True)
    severity = sa.Enum("low", "medium", "high", "critical", name="severity", native_enum=False, create_constraint=True)

    op.create_table(
        "requirements",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("status", requirement_status, nullable=False),
        sa.Column("acceptance_criteria", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", "title", name="uq_requirements_project_title"),
    )
    op.create_index("ix_requirements_project_id", "requirements", ["project_id"], unique=False)
    op.create_index("ix_requirements_status", "requirements", ["status"], unique=False)

    op.create_table(
        "test_cases",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("requirement_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("preconditions", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("steps", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("expected_result", sa.Text(), nullable=False),
        sa.Column("test_type", test_type, nullable=False),
        sa.Column("priority", priority, nullable=False),
        sa.Column("status", test_case_status, nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["requirement_id"], ["requirements.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("requirement_id", "title", name="uq_test_cases_requirement_title"),
    )
    op.create_index("ix_test_cases_priority", "test_cases", ["priority"], unique=False)
    op.create_index("ix_test_cases_requirement_id", "test_cases", ["requirement_id"], unique=False)
    op.create_index("ix_test_cases_status", "test_cases", ["status"], unique=False)

    op.create_table(
        "test_executions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("test_case_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", execution_status, nullable=False),
        sa.Column("executor", sa.String(length=100), nullable=True),
        sa.Column("run_reference", sa.String(length=255), nullable=True),
        sa.Column("summary", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["test_case_id"], ["test_cases.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("run_reference"),
    )
    op.create_index("ix_test_executions_started_at", "test_executions", ["started_at"], unique=False)
    op.create_index("ix_test_executions_status", "test_executions", ["status"], unique=False)
    op.create_index("ix_test_executions_test_case_id", "test_executions", ["test_case_id"], unique=False)

    op.create_table(
        "execution_evidence",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("execution_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("evidence_type", evidence_type, nullable=False),
        sa.Column("uri", sa.String(length=2048), nullable=False),
        sa.Column("label", sa.String(length=255), nullable=True),
        sa.Column("content_type", sa.String(length=100), nullable=True),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["execution_id"], ["test_executions.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_execution_evidence_evidence_type", "execution_evidence", ["evidence_type"], unique=False)
    op.create_index("ix_execution_evidence_execution_id", "execution_evidence", ["execution_id"], unique=False)

    op.create_table(
        "defects",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("execution_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("severity", severity, nullable=False),
        sa.Column("status", defect_status, nullable=False),
        sa.Column("fingerprint", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["execution_id"], ["test_executions.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("fingerprint"),
    )
    op.create_index("ix_defects_execution_id", "defects", ["execution_id"], unique=False)
    op.create_index("ix_defects_severity", "defects", ["severity"], unique=False)
    op.create_index("ix_defects_status", "defects", ["status"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_defects_status", table_name="defects")
    op.drop_index("ix_defects_severity", table_name="defects")
    op.drop_index("ix_defects_execution_id", table_name="defects")
    op.drop_table("defects")
    op.drop_index("ix_execution_evidence_execution_id", table_name="execution_evidence")
    op.drop_index("ix_execution_evidence_evidence_type", table_name="execution_evidence")
    op.drop_table("execution_evidence")
    op.drop_index("ix_test_executions_test_case_id", table_name="test_executions")
    op.drop_index("ix_test_executions_status", table_name="test_executions")
    op.drop_index("ix_test_executions_started_at", table_name="test_executions")
    op.drop_table("test_executions")
    op.drop_index("ix_test_cases_status", table_name="test_cases")
    op.drop_index("ix_test_cases_requirement_id", table_name="test_cases")
    op.drop_index("ix_test_cases_priority", table_name="test_cases")
    op.drop_table("test_cases")
    op.drop_index("ix_requirements_status", table_name="requirements")
    op.drop_index("ix_requirements_project_id", table_name="requirements")
    op.drop_table("requirements")
