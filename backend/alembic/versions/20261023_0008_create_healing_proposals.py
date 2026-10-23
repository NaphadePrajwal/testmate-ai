"""create_healing_proposals

Revision ID: 20261023_0008
Revises: 20261022_0007
Create Date: 2026-10-23
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '20261023_0008'
down_revision = '20261022_0007'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'healing_proposals',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('project_id', sa.UUID(), nullable=False),
        sa.Column('test_case_id', sa.UUID(), nullable=False),
        sa.Column('original_execution_id', sa.UUID(), nullable=False),
        sa.Column('retry_execution_id', sa.UUID(), nullable=True),
        sa.Column('step_index', sa.Integer(), nullable=False),
        sa.Column('action_type', sa.String(length=50), nullable=False),
        sa.Column('original_selector', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('proposed_selector', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('approved_selector', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            'status',
            sa.Enum(
                'detected',
                'analyzing',
                'proposed',
                'awaiting_approval',
                'approved',
                'rejected',
                'validating',
                'healed',
                'failed',
                name='healingstatus',
                native_enum=False,
                create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column('failure_reason', sa.Text(), nullable=False),
        sa.Column('failure_category', sa.String(length=100), nullable=False),
        sa.Column('page_url', sa.String(length=2048), nullable=True),
        sa.Column('page_title', sa.String(length=255), nullable=True),
        sa.Column('dom_context', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('candidate_validation_results', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('confidence', sa.Float(), nullable=False),
        sa.Column('explanation', sa.Text(), nullable=True),
        sa.Column('decision_notes', sa.Text(), nullable=True),
        sa.Column('approved_by', sa.String(length=100), nullable=True),
        sa.Column('approved_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('repaired_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['original_execution_id'], ['test_executions.id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['retry_execution_id'], ['test_executions.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['test_case_id'], ['test_cases.id'], ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_healing_proposals_original_execution_id'), 'healing_proposals', ['original_execution_id'], unique=False)
    op.create_index(op.f('ix_healing_proposals_project_id'), 'healing_proposals', ['project_id'], unique=False)
    op.create_index(op.f('ix_healing_proposals_retry_execution_id'), 'healing_proposals', ['retry_execution_id'], unique=False)
    op.create_index(op.f('ix_healing_proposals_status'), 'healing_proposals', ['status'], unique=False)
    op.create_index(op.f('ix_healing_proposals_test_case_id'), 'healing_proposals', ['test_case_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_healing_proposals_test_case_id'), table_name='healing_proposals')
    op.drop_index(op.f('ix_healing_proposals_status'), table_name='healing_proposals')
    op.drop_index(op.f('ix_healing_proposals_retry_execution_id'), table_name='healing_proposals')
    op.drop_index(op.f('ix_healing_proposals_project_id'), table_name='healing_proposals')
    op.drop_index(op.f('ix_healing_proposals_original_execution_id'), table_name='healing_proposals')
    op.drop_table('healing_proposals')
