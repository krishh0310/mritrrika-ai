"""Administrative hierarchy and cadastral parcels (§11, §38).

Locations are a single self-referencing table rather than four, so an officer's
jurisdiction check is one recursive ancestor query instead of four joins.
"""

from __future__ import annotations

from geoalchemy2 import Geometry
from sqlalchemy import Float, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, SyntheticMixin, TimestampMixin, new_uuid


class Location(Base, TimestampMixin):
    __tablename__ = "locations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    external_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    name_devanagari: Mapped[str | None] = mapped_column(String(255))
    level: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    parent_id: Mapped[str | None] = mapped_column(
        ForeignKey("locations.id", ondelete="RESTRICT"), index=True
    )

    parent: Mapped[Location | None] = relationship(remote_side="Location.id")
    parcels: Mapped[list[Parcel]] = relationship(back_populates="village")


class Parcel(Base, TimestampMixin, SyntheticMixin):
    """The join key of the whole system (§11).

    Deliberately carries NO owner column. Ownership is expressed only through
    time-bounded OwnershipRecord rows (§39), which is what makes historical
    ownership answerable.
    """

    __tablename__ = "parcels"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    external_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    village_id: Mapped[str] = mapped_column(
        ForeignKey("locations.id", ondelete="RESTRICT"), nullable=False, index=True
    )

    khasra_number: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    khata_number: Mapped[str | None] = mapped_column(String(32), index=True)

    area_value: Mapped[float] = mapped_column(Float, nullable=False)
    area_unit: Mapped[str] = mapped_column(String(16), nullable=False)
    area_unit_raw: Mapped[str | None] = mapped_column(String(32))
    land_class: Mapped[str | None] = mapped_column(String(64))

    #: EPSG:4326. SRID is pinned here because an unset SRID makes ST_Area
    #: silently return square degrees.
    geometry: Mapped[object | None] = mapped_column(
        Geometry(geometry_type="POLYGON", srid=4326, spatial_index=True)
    )

    village: Mapped[Location] = relationship(back_populates="parcels")
    ownership: Mapped[list[OwnershipRecord]] = relationship(  # noqa: F821
        back_populates="parcel"
    )
    mutations: Mapped[list[Mutation]] = relationship(back_populates="parcel")  # noqa: F821


Index("ix_parcels_village_khasra", Parcel.village_id, Parcel.khasra_number)
