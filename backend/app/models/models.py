from datetime import date, datetime, time
from decimal import Decimal
from typing import Optional

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Numeric, String, Text, Time, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import ExcludeConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class User(TimestampMixin, Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    __table_args__ = (CheckConstraint("role IN ('owner', 'admin', 'barber', 'client')", name="ck_users_role"),)


class AuthSession(Base):
    __tablename__ = "auth_sessions"
    id: Mapped[int] = mapped_column(primary_key=True)
    # Supports account-scoped session lookup and future revocation.
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", name="fk_auth_sessions_user_id", ondelete="RESTRICT"),
        nullable=False, index=True,
    )
    session_token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    csrf_token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        UniqueConstraint("session_token_hash", name="uq_auth_sessions_session_token_hash"),
    )


class Barber(TimestampMixin, Base):
    __tablename__ = "barbers"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id", name="fk_barbers_user_id", ondelete="RESTRICT"),
        nullable=True,
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    appointments: Mapped[list["Appointment"]] = relationship(back_populates="barber")
    business_hours: Mapped[list["BusinessHours"]] = relationship(back_populates="barber")
    blocked_times: Mapped[list["BlockedTime"]] = relationship(back_populates="barber")

    __table_args__ = (UniqueConstraint("user_id", name="uq_barbers_user_id"),)


class Service(TimestampMixin, Base):
    __tablename__ = "services"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    price: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    duration_minutes: Mapped[int] = mapped_column(nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    appointments: Mapped[list["Appointment"]] = relationship(back_populates="service")

    __table_args__ = (CheckConstraint("price >= 0", name="ck_services_price_non_negative"), CheckConstraint("duration_minutes > 0", name="ck_services_duration_positive"))


class Appointment(TimestampMixin, Base):
    __tablename__ = "appointments"
    id: Mapped[int] = mapped_column(primary_key=True)
    client_user_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id", name="fk_appointments_client_user_id", ondelete="RESTRICT"),
        nullable=True,
    )
    client_name: Mapped[str] = mapped_column(String(120), nullable=False)
    client_phone: Mapped[str] = mapped_column(String(40), nullable=False)
    service_id: Mapped[int] = mapped_column(ForeignKey("services.id", ondelete="RESTRICT"), nullable=False, index=True)
    barber_id: Mapped[int] = mapped_column(ForeignKey("barbers.id", ondelete="RESTRICT"), nullable=False, index=True)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    notes: Mapped[Optional[str]] = mapped_column(Text)
    service: Mapped[Service] = relationship(back_populates="appointments")
    barber: Mapped[Barber] = relationship(back_populates="appointments")

    __table_args__ = (
        CheckConstraint("ends_at > starts_at", name="ck_appointments_time_order"),
        CheckConstraint("status IN ('pending', 'confirmed', 'completed', 'cancelled', 'no_show')", name="ck_appointments_status"),
        ExcludeConstraint(
            (text("barber_id"), "="), (text("tstzrange(starts_at, ends_at, '[)')"), "&&"),
            where=text("status IN ('pending', 'confirmed')"),
            using="gist",
            name="ex_appointments_active_barber_time_overlap",
        ),
    )


class BusinessHours(Base):
    __tablename__ = "business_hours"
    id: Mapped[int] = mapped_column(primary_key=True)
    barber_id: Mapped[int] = mapped_column(ForeignKey("barbers.id", ondelete="CASCADE"), nullable=False, index=True)
    day_of_week: Mapped[int] = mapped_column(nullable=False)
    opening_time: Mapped[Optional[time]] = mapped_column(Time)
    closing_time: Mapped[Optional[time]] = mapped_column(Time)
    is_open: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    barber: Mapped[Barber] = relationship(back_populates="business_hours")

    __table_args__ = (CheckConstraint("day_of_week BETWEEN 0 AND 6", name="ck_business_hours_day"), CheckConstraint("NOT is_open OR (opening_time IS NOT NULL AND closing_time IS NOT NULL AND closing_time > opening_time)", name="ck_business_hours_time_order"))


class BlockedTime(Base):
    __tablename__ = "blocked_times"
    id: Mapped[int] = mapped_column(primary_key=True)
    barber_id: Mapped[int] = mapped_column(ForeignKey("barbers.id", ondelete="CASCADE"), nullable=False, index=True)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    reason: Mapped[Optional[str]] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    barber: Mapped[Barber] = relationship(back_populates="blocked_times")

    __table_args__ = (CheckConstraint("ends_at > starts_at", name="ck_blocked_times_time_order"),)
