"""documents.handwriting_meta (JSONB), for enriched review routing

Revision ID: b8c9d0e1f2a3
Revises: a7b8c9d0e1f2
Create Date: 2026-09-19 21:00:00.000000

Existing documents keep NULL until reprocessed: the metadata is computed from
OCR geometry at pipeline time.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = 'b8c9d0e1f2a3'
down_revision: str | None = 'a7b8c9d0e1f2'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('documents', sa.Column('handwriting_meta',
                                         postgresql.JSONB(astext_type=sa.Text()), nullable=True))


def downgrade() -> None:
    op.drop_column('documents', 'handwriting_meta')
