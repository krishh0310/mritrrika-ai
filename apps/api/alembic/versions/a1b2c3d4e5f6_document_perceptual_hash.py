"""document perceptual hash for near-duplicate detection

Revision ID: a1b2c3d4e5f6
Revises: f67d310791a5
Create Date: 2026-09-13 13:10:00.000000

Existing rows keep a NULL hash rather than being backfilled: the bytes are in
object storage, so a backfill is a separate, resumable job -- not something to
run inside a schema migration. find_near_duplicates() skips NULLs, so an
un-backfilled corpus simply yields no near matches.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = 'a1b2c3d4e5f6'
down_revision: str | None = 'f67d310791a5'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'documents',
        sa.Column('perceptual_hash', sa.String(length=16), nullable=True),
    )
    op.create_index(
        op.f('ix_documents_perceptual_hash'),
        'documents',
        ['perceptual_hash'],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f('ix_documents_perceptual_hash'), table_name='documents')
    op.drop_column('documents', 'perceptual_hash')
