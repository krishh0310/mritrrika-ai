"""Users, roles and the citizen -> owner link (§38, §13).

The link that matters most: CitizenProfile.owner_id. Citizen authorization is
derived from it server-side and never accepted from the client (§62).
"""

from __future__ import annotations

from sqlalchemy import Boolean, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, SyntheticMixin, TimestampMixin, new_uuid


class Role(Base, TimestampMixin):
    __tablename__ = "roles"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    code: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)

    users: Mapped[list[UserRole]] = relationship(back_populates="role")


class Permission(Base, TimestampMixin):
    """A named capability from the §36 matrix, e.g. 'document:upload'."""

    __tablename__ = "permissions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)


class RolePermission(Base):
    __tablename__ = "role_permissions"
    __table_args__ = (UniqueConstraint("role_id", "permission_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    role_id: Mapped[str] = mapped_column(ForeignKey("roles.id", ondelete="CASCADE"))
    permission_id: Mapped[str] = mapped_column(
        ForeignKey("permissions.id", ondelete="CASCADE")
    )


class User(Base, TimestampMixin, SyntheticMixin):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    external_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)

    #: Argon2 hash. Plaintext is never stored, logged or returned (§61).
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    #: Highest location an officer may act within (§36 jurisdiction).
    #: Null for citizens, whose scope comes from ownership instead.
    jurisdiction_id: Mapped[str | None] = mapped_column(
        ForeignKey("locations.id", ondelete="SET NULL")
    )

    roles: Mapped[list[UserRole]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    citizen_profile: Mapped[CitizenProfile | None] = relationship(
        back_populates="user", uselist=False, cascade="all, delete-orphan"
    )

    @property
    def role_codes(self) -> set[str]:
        return {ur.role.code for ur in self.roles if ur.role}


class UserRole(Base, TimestampMixin):
    __tablename__ = "user_roles"
    __table_args__ = (UniqueConstraint("user_id", "role_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    role_id: Mapped[str] = mapped_column(ForeignKey("roles.id", ondelete="CASCADE"))

    user: Mapped[User] = relationship(back_populates="roles")
    role: Mapped[Role] = relationship(back_populates="users")


class CitizenProfile(Base, TimestampMixin, SyntheticMixin):
    """Binds a login to a recorded landholder (§13).

    This is the ONLY sanctioned path from an authenticated request to a set of
    parcels. Any endpoint that takes an owner_id from the client is a bug (§62).
    """

    __tablename__ = "citizen_profiles"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    owner_id: Mapped[str] = mapped_column(
        ForeignKey("owners.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    phone: Mapped[str | None] = mapped_column(String(32))

    user: Mapped[User] = relationship(back_populates="citizen_profile")
    owner: Mapped[Owner] = relationship(back_populates="citizen_profile")  # noqa: F821
