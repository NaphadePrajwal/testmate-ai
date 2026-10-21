"""Add defect resolution verification fields and knowledge_indexing_jobs table.

Revision ID: 20261022_0006
Revises: 20261015_0005
Create Date: 2026-10-22
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20261022_0006"
down_revision = "20261015_0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    verification_status_enum = sa.Enum(
        "unverified", "verified", "revoked",
        name="verificationstatus",
        native_enum=False,
        create_constraint=True,
    )
    indexing_action_enum = sa.Enum(
        "upsert", "delete",
        name="indexingjobaction",
        native_enum=False,
        create_constraint=True,
    )
    indexing_status_enum = sa.Enum(
        "pending", "processing", "completed", "failed",
        name="indexingjobstatus",
        native_enum=False,
        create_constraint=True,
    )

    # 1. Add verification and resolution fields to defects table
    op.add_column("defects", sa.Column("resolution_notes", sa.Text(), nullable=True))
    op.add_column(
        "defects",
        sa.Column(
            "verification_status",
            verification_status_enum,
            nullable=False,
            server_default="unverified",
        ),
    )
    op.add_column("defects", sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("defects", sa.Column("verification_method", sa.String(length=100), nullable=True))
    op.add_column("defects", sa.Column("verification_evidence", sa.Text(), nullable=True))
    op.create_index("ix_defects_verification_status", "defects", ["verification_status"], unique=False)

    # 2. Create knowledge_indexing_jobs table (transactional outbox)
    op.create_table(
        "knowledge_indexing_jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "project_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("record_type", sa.String(length=50), nullable=False),
        sa.Column("source_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("action", indexing_action_enum, nullable=False, server_default="upsert"),
        sa.Column("status", indexing_status_enum, nullable=False, server_default="pending"),
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_retries", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_knowledge_indexing_jobs_project_id", "knowledge_indexing_jobs", ["project_id"], unique=False)
    op.create_index("ix_knowledge_indexing_jobs_record_type", "knowledge_indexing_jobs", ["record_type"], unique=False)
    op.create_index("ix_knowledge_indexing_jobs_source_id", "knowledge_indexing_jobs", ["source_id"], unique=False)
    op.create_index("ix_knowledge_indexing_jobs_status", "knowledge_indexing_jobs", ["status"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_knowledge_indexing_jobs_status", table_name="knowledge_indexing_jobs")
    op.drop_index("ix_knowledge_indexing_jobs_source_id", table_name="knowledge_indexing_jobs")
    op.drop_index("ix_knowledge_indexing_jobs_record_type", table_name="knowledge_indexing_jobs")
    op.drop_index("ix_knowledge_indexing_jobs_project_id", table_name="knowledge_indexing_jobs")
    op.drop_table("knowledge_indexing_jobs")

    op.drop_index("ix_defects_verification_status", table_name="defects")
    op.drop_column("defects", "verification_evidence")
    op.drop_column("defects", "verification_method")
    op.drop_column("defects", "verified_at")
    op.drop_column("defects", "verification_status")
    op.drop_column("defects", "resolution_notes")
