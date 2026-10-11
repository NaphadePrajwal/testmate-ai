"""Add test_case review_status column.

Revision ID: 20261011_0003
Revises: 20261004_0002
Create Date: 2026-10-11
"""
from alembic import op
import sqlalchemy as sa

revision = "20261011_0003"
down_revision = "20261004_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    review_status_enum = sa.Enum(
        "pending", "approved", "rejected",
        name="reviewstatus",
        native_enum=False,
        create_constraint=True,
    )
    op.add_column(
        "test_cases",
        sa.Column(
            "review_status",
            review_status_enum,
            nullable=False,
            server_default="pending",
        ),
    )
    op.create_index("ix_test_cases_review_status", "test_cases", ["review_status"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_test_cases_review_status", table_name="test_cases")
    op.drop_column("test_cases", "review_status")
