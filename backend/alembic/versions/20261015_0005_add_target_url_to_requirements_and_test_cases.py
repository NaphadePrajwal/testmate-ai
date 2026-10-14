"""Add target_url to requirements and test_cases.

Revision ID: 20261015_0005
Revises: 20261013_0004
Create Date: 2026-10-15
"""
from alembic import op
import sqlalchemy as sa

revision = "20261015_0005"
down_revision = "20261013_0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("requirements", sa.Column("target_url", sa.String(length=2048), nullable=True))
    op.add_column("test_cases", sa.Column("target_url", sa.String(length=2048), nullable=True))


def downgrade() -> None:
    op.drop_column("test_cases", "target_url")
    op.drop_column("requirements", "target_url")
