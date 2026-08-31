"""Owners, time-bounded ownership, mutations and land records (§38, §39, §40)."""

from __future__ import annotations

from datetime import date

from sqlalchemy import Date, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, SyntheticMixin, TimestampMixin, new_uuid


class Owner(Base, TimestampMixin, SyntheticMixin):
    """A person who can hold land.

    Distinct from User: most owners in a record set have no login at all.
    """

    __tablename__ = "owners"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    external_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    guardian_name: Mapped[str | None] = mapped_column(String(255))

    ownership: Mapped[list[OwnershipRecord]] = relationship(back_populates="owner")
    citizen_profile: Mapped[CitizenProfile | None] = relationship(  # noqa: F821
        back_populates="owner", uselist=False
    )


class OwnershipRecord(Base, TimestampMixin):
    """A time-bounded interest in a parcel (§39).

    valid_to IS NULL means "current". Share is stored as the fraction written
    on the document ('1/2'), never as a float -- rounding a recorded share
    changes its legal meaning.
    """

    __tablename__ = "ownership_records"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    external_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)

    owner_id: Mapped[str] = mapped_column(
        ForeignKey("owners.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    parcel_id: Mapped[str] = mapped_column(
        ForeignKey("parcels.id", ondelete="CASCADE"), nullable=False, index=True
    )
    mutation_id: Mapped[str | None] = mapped_column(
        ForeignKey("mutations.id", ondelete="SET NULL")
    )

    share: Mapped[str] = mapped_column(String(16), nullable=False, default="1/1")
    valid_from: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    valid_to: Mapped[date | None] = mapped_column(Date, index=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="ACTIVE")

    owner: Mapped[Owner] = relationship(back_populates="ownership")
    parcel: Mapped[Parcel] = relationship(back_populates="ownership")  # noqa: F821


#: The hot path for "what does this citizen own right now?" and for
#: "who held this parcel on date X?" -- both hit owner/parcel + validity.
Index("ix_ownership_owner_validity", OwnershipRecord.owner_id,
      OwnershipRecord.valid_from, OwnershipRecord.valid_to)
Index("ix_ownership_parcel_validity", OwnershipRecord.parcel_id,
      OwnershipRecord.valid_from, OwnershipRecord.valid_to)


class Mutation(Base, TimestampMixin):
    """A recorded transfer (§40)."""

    __tablename__ = "mutations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    external_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    parcel_id: Mapped[str] = mapped_column(
        ForeignKey("parcels.id", ondelete="CASCADE"), nullable=False, index=True
    )
    mutation_number: Mapped[str] = mapped_column(String(32), nullable=False)
    mutation_type: Mapped[str] = mapped_column(String(32), nullable=False)
    effective_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    registration_date: Mapped[date | None] = mapped_column(Date)
    source_document_id: Mapped[str | None] = mapped_column(
        ForeignKey("documents.id", ondelete="SET NULL")
    )
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="REGISTERED")
    notes: Mapped[str | None] = mapped_column(Text)

    parcel: Mapped[Parcel] = relationship(back_populates="mutations")  # noqa: F821


class LandRecord(Base, TimestampMixin, SyntheticMixin):
    """A record-of-rights row tying a parcel to a record year."""

    __tablename__ = "land_records"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    external_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    parcel_id: Mapped[str] = mapped_column(
        ForeignKey("parcels.id", ondelete="CASCADE"), nullable=False, index=True
    )
    document_type: Mapped[str] = mapped_column(String(32), nullable=False)
    record_year: Mapped[str] = mapped_column(String(16), nullable=False)

    #: Only APPROVED records are ever exposed to citizens (§17).
    status: Mapped[str] = mapped_column(
        String(24), nullable=False, default="APPROVED", index=True
    )
