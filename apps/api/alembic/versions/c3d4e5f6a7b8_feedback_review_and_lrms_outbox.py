"""feedback review decisions, and the LRMS delivery outbox

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-09-19 12:00:00.000000

Two independent additions that land together:

  * ai_feedback gains who reviewed a correction, when, and what they decided.
    `reviewed` alone could not say whether a reviewed row was accepted for
    training or rejected, so nothing could safely be exported.
  * lrms_sync_records is the outbox approved records are delivered from.

Existing feedback rows keep NULL decisions: none of them was ever reviewed,
because until now nothing could review them.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = 'c3d4e5f6a7b8'
down_revision: str | None = 'b2c3d4e5f6a7'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('ai_feedback', sa.Column('review_decision', sa.String(length=16), nullable=True))
    op.add_column('ai_feedback', sa.Column('reviewed_by_id', sa.String(length=36), nullable=True))
    op.add_column('ai_feedback', sa.Column('reviewed_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('ai_feedback', sa.Column('review_note', sa.Text(), nullable=True))
    op.create_foreign_key(
        op.f('fk_ai_feedback_reviewed_by_id_users'), 'ai_feedback', 'users',
        ['reviewed_by_id'], ['id'], ondelete='SET NULL',
    )
    op.create_index(
        op.f('ix_ai_feedback_review_decision'), 'ai_feedback', ['review_decision'], unique=False,
    )

    op.create_table(
        'lrms_sync_records',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('document_id', sa.String(length=36), nullable=False),
        sa.Column('payload', sa.JSON(), nullable=False),
        sa.Column('payload_sha256', sa.String(length=64), nullable=False),
        sa.Column('status', sa.String(length=16), nullable=False),
        sa.Column('attempts', sa.Integer(), nullable=False),
        sa.Column('adapter', sa.String(length=32), nullable=True),
        sa.Column('remote_reference', sa.String(length=255), nullable=True),
        sa.Column('last_error', sa.Text(), nullable=True),
        sa.Column('delivered_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(
            ['document_id'], ['documents.id'],
            name=op.f('fk_lrms_sync_records_document_id_documents'), ondelete='CASCADE',
        ),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_lrms_sync_records')),
    )
    op.create_index(
        op.f('ix_lrms_sync_records_document_id'), 'lrms_sync_records', ['document_id'], unique=False,
    )
    op.create_index(
        op.f('ix_lrms_sync_records_status'), 'lrms_sync_records', ['status'], unique=False,
    )
    op.create_index(
        'uq_lrms_sync_document_digest', 'lrms_sync_records',
        ['document_id', 'payload_sha256'], unique=True,
    )


def downgrade() -> None:
    op.drop_index('uq_lrms_sync_document_digest', table_name='lrms_sync_records')
    op.drop_index(op.f('ix_lrms_sync_records_status'), table_name='lrms_sync_records')
    op.drop_index(op.f('ix_lrms_sync_records_document_id'), table_name='lrms_sync_records')
    op.drop_table('lrms_sync_records')

    op.drop_index(op.f('ix_ai_feedback_review_decision'), table_name='ai_feedback')
    op.drop_constraint(
        op.f('fk_ai_feedback_reviewed_by_id_users'), 'ai_feedback', type_='foreignkey',
    )
    op.drop_column('ai_feedback', 'review_note')
    op.drop_column('ai_feedback', 'reviewed_at')
    op.drop_column('ai_feedback', 'reviewed_by_id')
    op.drop_column('ai_feedback', 'review_decision')
