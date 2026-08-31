"""Declarative base and shared column mixins.

Every table gets created/dropped through this Base so Alembic autogenerate
sees the whole schema from one import.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, MetaData, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

#: Explicit naming so Alembic emits stable, readable constraint names rather
#: than backend-generated ones that churn between autogenerate runs.
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


def new_uuid() -> str:
    return str(uuid.uuid4())


class TimestampMixin:
    """created_at / updated_at, maintained by the database."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class SyntheticMixin:
    """§83 -- every record carries whether it is demo data.

    Held on the row rather than inferred, so an export or a screenshot cannot
    lose the distinction.
    """

    from sqlalchemy import Boolean

    is_synthetic: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
