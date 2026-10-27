# Mirrors the database schema for the application models
#
#
# TODO: Add SQLAlchemy relationship helpers. Work done when the endpoints need them.

from datetime import date, datetime

from sqlalchemy import (
    Boolean, CheckConstraint, Column, Date, DateTime, ForeignKey, Identity,
    Integer, SmallInteger, Text, func, text,
)
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from .extensions import db


class Tech(db.Model):
    __tablename__ = "tech"

    tech_id: Mapped[int] = mapped_column(Identity(always=True), primary_key=True)
    first_name: Mapped[str] = mapped_column(Text)
    last_name: Mapped[str] = mapped_column(Text)
    start_date: Mapped[date] = mapped_column(Date)
    is_active: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))


class Client(db.Model):
    __tablename__ = "client"

    client_id: Mapped[int] = mapped_column(Identity(always=True), primary_key=True)
    first_name: Mapped[str] = mapped_column(Text)
    last_name: Mapped[str] = mapped_column(Text)
    phone: Mapped[str | None] = mapped_column(Text)
    email: Mapped[str | None] = mapped_column(Text)
    zipcode: Mapped[str | None] = mapped_column(Text)
    languages: Mapped[list[str]] = mapped_column(ARRAY(Text), server_default=text("'{}'"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ClientDevice(db.Model):
    __tablename__ = "client_device"

    device_id: Mapped[int] = mapped_column(Identity(always=True), primary_key=True)
    client_id: Mapped[int] = mapped_column(
        ForeignKey("client.client_id", ondelete="CASCADE"), index=True
    )
    device_type: Mapped[str] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)


class Appointment(db.Model):
    __tablename__ = "appointment"
    __table_args__ = (
        CheckConstraint("length_minutes > 0", name="length_positive"),
    )

    appointment_id: Mapped[int] = mapped_column(Identity(always=True), primary_key=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("client.client_id"), index=True)
    tech_id: Mapped[int] = mapped_column(ForeignKey("tech.tech_id"), index=True)
    appointment_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    location: Mapped[str | None] = mapped_column(Text)
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


class CallLog(db.Model):
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