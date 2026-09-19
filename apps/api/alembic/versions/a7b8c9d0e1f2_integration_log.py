"""integration_log: every attempt to reach DILRMP / LRMS

Revision ID: a7b8c9d0e1f2
Revises: f6a7b8c9d0e1
Create Date: 2026-09-19 20:00:00.000000
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = 'a7b8c9d0e1f2'
down_revision: str | None = 'f6a7b8c9d0e1'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'integration_log',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('connector', sa.String(length=32), nullable=False),
        sa.Column('record_id', sa.String(length=64), nullable=False),
        sa.Column('status', sa.String(length=16), nullable=False),
        sa.Column('error', sa.Text(), nullable=True),
        sa.Column('attempted_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_integration_log')),
    )
    op.create_index(op.f('ix_integration_log_connector'), 'integration_log', ['connector'])
    op.create_index(op.f('ix_integration_log_record_id'), 'integration_log', ['record_id'])
    op.create_index(op.f('ix_integration_log_attempted_at'), 'integration_log', ['attempted_at'])


def downgrade() -> None:
    op.drop_index(op.f('ix_integration_log_attempted_at'), table_name='integration_log')
    op.drop_index(op.f('ix_integration_log_record_id'), table_name='integration_log')
    op.drop_index(op.f('ix_integration_log_connector'), table_name='integration_log')
    op.drop_table('integration_log')
