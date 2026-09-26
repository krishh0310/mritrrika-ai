"""forensic_reports: Gemini tamper/stamp/signature/area/fraud checks

Revision ID: c9d0e1f2a3b4
Revises: b8c9d0e1f2a3
Create Date: 2026-09-26 12:00:00.000000
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = 'c9d0e1f2a3b4'
down_revision: str | None = 'b8c9d0e1f2a3'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'forensic_reports',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('document_id', sa.String(length=36), nullable=False),
        sa.Column('check', sa.String(length=16), nullable=False),
        sa.Column('verdict', sa.String(length=32), nullable=False),
        sa.Column('score', sa.Float(), nullable=True),
        sa.Column('result', sa.JSON(), nullable=False),
        sa.Column('model_version', sa.String(length=48), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['document_id'], ['documents.id'], name=op.f('fk_forensic_reports_document_id_documents'), ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_forensic_reports')),
    )
    op.create_index(op.f('ix_forensic_reports_document_id'), 'forensic_reports', ['document_id'])


def downgrade() -> None:
    op.drop_index(op.f('ix_forensic_reports_document_id'), table_name='forensic_reports')
    op.drop_table('forensic_reports')
