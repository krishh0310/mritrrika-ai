"""documents.translated_from, for the IndicTrans2 fallback

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-09-19 18:00:00.000000
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = 'e5f6a7b8c9d0'
down_revision: str | None = 'd4e5f6a7b8c9'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('documents', sa.Column('translated_from', sa.String(length=8), nullable=True))


def downgrade() -> None:
    op.drop_column('documents', 'translated_from')
