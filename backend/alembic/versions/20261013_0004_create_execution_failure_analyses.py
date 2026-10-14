"""Create execution_failure_analyses table for Phase 7.

Revision ID: 20261013_0004
Revises: 20261011_0003
Create Date: 2026-10-13
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20261013_0004"
down_revision = "20261011_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "execution_failure_analyses",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "execution_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("test_executions.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "project_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("projects.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("failure_category", sa.String(length=100), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("observed_error", sa.Text(), nullable=False),
        sa.Column("likely_root_cause", sa.Text(), nullable=False),
        sa.Column("supporting_evidence", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="[]"),
        sa.Column("recommended_debugging_steps", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="[]"),
        sa.Column("confidence", sa.String(length=50), nullable=False, server_default="medium"),
        sa.Column("uncertainty_notes", sa.Text(), nullable=True),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index(
        "ix_execution_failure_analyses_execution_id",
        "execution_failure_analyses",
        ["execution_id"],
        unique=True,
    )
    op.create_index(
        "ix_execution_failure_analyses_project_id",
        "execution_failure_analyses",
        ["project_id"],
        unique=False,
    )
    op.create_index(
        "ix_execution_failure_analyses_failure_category",
        "execution_failure_analyses",
        ["failure_category"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_execution_failure_analyses_failure_category", table_name="execution_failure_analyses")
    op.drop_index("ix_execution_failure_analyses_project_id", table_name="execution_failure_analyses")
    op.drop_index("ix_execution_failure_analyses_execution_id", table_name="execution_failure_analyses")
    op.drop_table("execution_failure_analyses")
