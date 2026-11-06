# Mirrors the database schema for the application models
#
#
# TODO: Add SQLAlchemy relationship helpers. Work done when the endpoints need them.

from datetime import date, datetime

from sqlalchemy import (
    BigInteger, Boolean, CheckConstraint, UniqueConstraint, Column, Date, DateTime, ForeignKey, Identity,
    Integer, SmallInteger, Text, func, select, text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from .extensions import db

ROLES = ("admin", "manager", "navigator")

class SoftDeleteMixin:
    """Rows are hidden, not removed. Always query through Model.active()"""
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)

    @classmethod
    def active(cls):
        return select(cls).where(cls.deleted_at.is_(None))

class Tech(db.Model):
    __tablename__ = "tech"

    tech_id: Mapped[int] = mapped_column(Identity(always=True), primary_key=True)
    first_name: Mapped[str] = mapped_column(Text)
    last_name: Mapped[str] = mapped_column(Text)
    start_date: Mapped[date] = mapped_column(Date)
    is_active: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))


class Client(SoftDeleteMixin,db.Model):
    __tablename__ = "client"

    client_id: Mapped[int] = mapped_column(Identity(always=True), primary_key=True)
    first_name: Mapped[str] = mapped_column(Text)
    last_name: Mapped[str] = mapped_column(Text)
    phone: Mapped[str | None] = mapped_column(Text)
    email: Mapped[str | None] = mapped_column(Text)
    zipcode: Mapped[str | None] = mapped_column(Text)
    languages: Mapped[list[str]] = mapped_column(ARRAY(Text), server_default=text("'{}'"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ClientDevice(SoftDeleteMixin,db.Model):
    __tablename__ = "client_device"

    device_id: Mapped[int] = mapped_column(Identity(always=True), primary_key=True)
    client_id: Mapped[int] = mapped_column(
        ForeignKey("client.client_id", ondelete="CASCADE"), index=True
    )
    device_type: Mapped[str] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)


class Appointment(SoftDeleteMixin, db.Model):
    __tablename__ = "appointment"
    __table_args__ = (
        CheckConstraint("length_minutes > 0", name="length_positive"),
    )

    appointment_id: Mapped[int] = mapped_column(Identity(always=True), primary_key=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("client.client_id"), index=True)
    tech_id: Mapped[int] = mapped_column(ForeignKey("tech.tech_id"), index=True)
    appointment_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    location_id: Mapped[int | None] = mapped_column(ForeignKey("location.location_id"), index=True)
    length_minutes: Mapped[int | None] = mapped_column(SmallInteger)
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


appointment_device = db.Table(
    "appointment_device",
    Column(
        "appointment_id", Integer,
        ForeignKey("appointment.appointment_id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "device_id", Integer,
        ForeignKey("client_device.device_id"),
        primary_key=True,
    ),
)


class CallLog(SoftDeleteMixin, db.Model):
    __tablename__ = "call_log"

    call_id: Mapped[int] = mapped_column(Identity(always=True), primary_key=True)
    client_id: Mapped[int | None] = mapped_column(
        ForeignKey("client.client_id", ondelete="SET NULL"), index=True
    )
    client_first_name: Mapped[str | None] = mapped_column(Text)
    client_last_name: Mapped[str | None] = mapped_column(Text)
    phone: Mapped[str | None] = mapped_column(Text)
    called_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    notes: Mapped[str | None] = mapped_column(Text)


class ClientFeedback(db.Model):
    __tablename__ = "client_feedback"
    __table_args__ = (
        CheckConstraint("overall_session_rating BETWEEN 1 AND 5", name="overall_rating_range"),
        CheckConstraint("tech_knowledge_rating BETWEEN 1 AND 5", name="knowledge_rating_range"),
        CheckConstraint("tech_communication_rating BETWEEN 1 AND 5", name="communication_rating_range"),
        CheckConstraint("tech_friendliness_rating BETWEEN 1 AND 5", name="friendliness_rating_range"),
    )

    feedback_id: Mapped[int] = mapped_column(Identity(always=True), primary_key=True)
    tech_id: Mapped[int] = mapped_column(ForeignKey("tech.tech_id"), index=True)
    submitted_on: Mapped[date] = mapped_column(Date, server_default=func.current_date())
    overall_session_rating: Mapped[int | None] = mapped_column(SmallInteger)
    tech_knowledge_rating: Mapped[int | None] = mapped_column(SmallInteger)
    tech_communication_rating: Mapped[int | None] = mapped_column(SmallInteger)
    tech_friendliness_rating: Mapped[int | None] = mapped_column(SmallInteger)
    comments: Mapped[str | None] = mapped_column(Text)

class AppUser(db.Model):
    __tablename__ = "app_user"
    __table_args__ = (
        CheckConstraint("role IN ('admin', 'manager', 'navigator')", name="role_valid"),
        CheckConstraint("username = lower(username)", name="username_lowercase"),
        CheckConstraint("role <> 'navigator' OR tech_id IS NOT NULL", name="navigator_has_tech"),
    )

    user_id: Mapped[int] = mapped_column(Identity(always=True), primary_key=True)
    username: Mapped[str] = mapped_column(Text, unique=True)
    password_hash: Mapped[str] = mapped_column(Text)
    role: Mapped[str] = mapped_column(Text)
    tech_id: Mapped[int | None] = mapped_column(ForeignKey("tech.tech_id"), unique=True)
    is_active: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    failed_login_count: Mapped[int] = mapped_column(SmallInteger, server_default=text("0"))
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    lockout_requires_admin: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    password_changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    totp_secret_encrypted: Mapped[str | None] = mapped_column(Text)
    totp_enabled: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    totp_last_used_step: Mapped[int | None] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class UserSession(db.Model):
    __tablename__ = "user_session"

    token_hash: Mapped[str] = mapped_column(Text, primary_key=True)   # SHA-256 of the cookie token
    user_id: Mapped[int] = mapped_column(ForeignKey("app_user.user_id", ondelete="CASCADE"), unique=True)
    csrf_token: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))   # absolute timeout

class AuditLog(db.Model):
    __tablename__ = "audit_log"

    audit_id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    actor_user_id: Mapped[int | None] = mapped_column(Integer)  # deliberately no foreign key
    actor_username: Mapped[str | None] = mapped_column(Text)    # snapshot that survives account changes
    action: Mapped[str] = mapped_column(Text, index=True)
    target_type: Mapped[str | None] = mapped_column(Text)
    target_id: Mapped[str | None] = mapped_column(Text)
    detail: Mapped[dict | None] = mapped_column(JSONB(none_as_null=True))
    ip_address: Mapped[str | None] = mapped_column(Text)        # validated by audit.record 

class MfaChallenge(db.Model):
    """Proof that the password step passed. Not a session: it unlocks only /login/totp."""
    __tablename__ = "mfa_challenge"

    token_hash: Mapped[str] = mapped_column(Text, primary_key=True)   # SHA-256 of the cookie token
    user_id: Mapped[int] = mapped_column(ForeignKey("app_user.user_id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class RecoveryCode(db.Model):
    __tablename__ = "recovery_code"
    __table_args__ = (UniqueConstraint("user_id", "code_hash"),)

    code_id: Mapped[int] = mapped_column(Identity(always=True), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("app_user.user_id", ondelete="CASCADE"))
    code_hash: Mapped[str] = mapped_column(Text)                      # SHA-256, never the code itself
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

class Location(db.Model):
    __tablename__ = "location"

    location_id: Mapped[int] = mapped_column(Identity(always=True), primary_key=True)
    name: Mapped[str] = mapped_column(Text)
    name_key: Mapped[str] = mapped_column(Text, unique=True)   # casefolded name: case-insensitive uniqueness
    is_active: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())    