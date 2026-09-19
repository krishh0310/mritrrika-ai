"""model_registry: the active field extractor and every retrain candidate

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-09-19 19:00:00.000000

Seeded with the rules extractor as the active model at its measured val F1
(0.592, docs/ai-pipeline.md), so the table is never without an active row.
"""
from __future__ import annotations

import uuid

import sqlalchemy as sa
from alembic import op

revision: str = 'f6a7b8c9d0e1'
down_revision: str | None = 'e5f6a7b8c9d0'
branch_labels = None
depends_on = None

RULES_F1 = 0.592


def upgrade() -> None:
    op.create_table(
        'model_registry',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('model_path', sa.String(length=512), nullable=False),
        sa.Column('f1_score', sa.Float(), nullable=True),
        sa.Column('promoted_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_model_registry')),
    )
    op.create_index('uq_model_registry_one_active', 'model_registry', ['is_active'],
                    unique=True, postgresql_where=sa.text('is_active'))
    op.execute(sa.text(
        "INSERT INTO model_registry (id, model_path, f1_score, promoted_at, is_active, notes) "
        "VALUES (:id, 'rules', :f1, now(), true, "
        "'deterministic extractor-v1; val F1 from scripts/evaluate_extraction.py')"
    ).bindparams(id=str(uuid.uuid4()), f1=RULES_F1))


def downgrade() -> None:
    op.drop_index('uq_model_registry_one_active', table_name='model_registry')
    op.drop_table('model_registry')
