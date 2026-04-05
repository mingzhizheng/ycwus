"""
SQLAlchemy 2.0 Declarative ORM Models — 12 tables
Maps to sql/001_schema.sql DDL
"""

from datetime import datetime, timezone
from typing import Optional, List

from sqlalchemy import (
    Integer, String, Text, Boolean, DateTime, Numeric, Date,
    ForeignKey, Index, CheckConstraint, UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def utcnow():
    return datetime.now(timezone.utc)


class Facility(Base):
    __tablename__ = "facilities"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    address: Mapped[Optional[str]] = mapped_column(Text)
    timezone: Mapped[str] = mapped_column(String(50), default="America/New_York")
    operating_hours: Mapped[Optional[dict]] = mapped_column(JSONB, default={"start": "08:00", "end": "17:00"})
    holidays_json: Mapped[Optional[list]] = mapped_column(JSONB, default=[])
    geo_lat: Mapped[Optional[float]] = mapped_column(Numeric(10, 7))
    geo_lng: Mapped[Optional[float]] = mapped_column(Numeric(10, 7))
    geo_radius_m: Mapped[int] = mapped_column(Integer, default=500)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    locations: Mapped[List["FacilityLocation"]] = relationship(back_populates="facility")


class FacilityLocation(Base):
    __tablename__ = "facility_locations"
    __table_args__ = (
        UniqueConstraint("facility_id", "code"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    facility_id: Mapped[int] = mapped_column(Integer, ForeignKey("facilities.id"), nullable=False)
    location_type: Mapped[str] = mapped_column(String(10), nullable=False)  # DOCK, YARD
    code: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="AVAILABLE")  # AVAILABLE, OCCUPIED, MAINTENANCE
    has_leveler: Mapped[bool] = mapped_column(Boolean, default=True)
    max_weight_lbs: Mapped[Optional[int]] = mapped_column(Integer)
    accepts_sizes_json: Mapped[Optional[list]] = mapped_column(JSONB, default=["20ft", "40ft", "45ft", "53ft"])
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    facility: Mapped["Facility"] = relationship(back_populates="locations")


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[str] = mapped_column(String(100), nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    email: Mapped[Optional[str]] = mapped_column(String(255))
    phone: Mapped[Optional[str]] = mapped_column(String(30))
    company_name: Mapped[Optional[str]] = mapped_column(String(200))
    dmv_number: Mapped[Optional[str]] = mapped_column(String(50))
    facility_ids: Mapped[Optional[list]] = mapped_column(JSONB, default=[1])
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    must_change_pwd: Mapped[bool] = mapped_column(Boolean, default=True)
    created_by: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class ASN(Base):
    __tablename__ = "asns"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    facility_id: Mapped[int] = mapped_column(Integer, ForeignKey("facilities.id"), nullable=False)
    shipper_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    container_number: Mapped[Optional[str]] = mapped_column(String(30))
    cargo_type: Mapped[str] = mapped_column(String(20), nullable=False)  # PALLETIZED, FLOOR_LOAD
    expected_qty: Mapped[Optional[int]] = mapped_column(Integer)
    qty_unit: Mapped[str] = mapped_column(String(10), default="BOXES")
    reference_number: Mapped[Optional[str]] = mapped_column(String(100))
    packing_list_path: Mapped[Optional[str]] = mapped_column(Text)
    truck_plate: Mapped[Optional[str]] = mapped_column(String(30))
    truck_company: Mapped[Optional[str]] = mapped_column(String(200))
    truck_dmv: Mapped[Optional[str]] = mapped_column(String(50))
    notes: Mapped[Optional[str]] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="ACTIVE")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    shipper: Mapped["User"] = relationship(foreign_keys=[shipper_id])


class Appointment(Base):
    __tablename__ = "appointments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    facility_id: Mapped[int] = mapped_column(Integer, ForeignKey("facilities.id"), nullable=False)
    asn_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("asns.id"))
    shipper_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    carrier_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.id"))

    appointment_type: Mapped[str] = mapped_column(String(10), nullable=False)  # LIVE, DROP
    carrier_type: Mapped[str] = mapped_column(String(10), default="own")
    platform_name: Mapped[Optional[str]] = mapped_column(String(100))
    platform_order_id: Mapped[Optional[str]] = mapped_column(String(100))

    status: Mapped[str] = mapped_column(String(25), default="PENDING", nullable=False)

    scheduled_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    scheduled_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    buffer_minutes: Mapped[int] = mapped_column(Integer, default=30)

    actual_arrival: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    actual_dock_start: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    actual_unload_start: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    actual_unload_complete: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    actual_pickup: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    actual_yard_move_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    dock_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("facility_locations.id"))
    yard_spot_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("facility_locations.id"))

    driver_name: Mapped[Optional[str]] = mapped_column(String(100))
    driver_phone: Mapped[Optional[str]] = mapped_column(String(30))
    truck_plate: Mapped[Optional[str]] = mapped_column(String(30))
    checkin_token: Mapped[Optional[str]] = mapped_column(String(64), unique=True)

    checkin_lat: Mapped[Optional[float]] = mapped_column(Numeric(10, 7))
    checkin_lng: Mapped[Optional[float]] = mapped_column(Numeric(10, 7))
    geo_flag: Mapped[str] = mapped_column(String(15), default="OK")

    safety_ack_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    device_fingerprint: Mapped[Optional[str]] = mapped_column(String(255))

    cargo_type_actual: Mapped[Optional[str]] = mapped_column(String(20))
    cargo_type_mismatch: Mapped[bool] = mapped_column(Boolean, default=False)

    bol_number: Mapped[Optional[str]] = mapped_column(String(50))
    bol_file_path: Mapped[Optional[str]] = mapped_column(Text)

    actual_unload_duration: Mapped[Optional[int]] = mapped_column(Integer)
    yard_move_count: Mapped[int] = mapped_column(Integer, default=0)
    reschedule_count: Mapped[int] = mapped_column(Integer, default=0)

    ltl_master_pro: Mapped[Optional[str]] = mapped_column(String(50))

    created_by: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.id"))
    confirmed_by: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.id"))
    cancelled_by: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.id"))
    cancel_reason: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    shipper: Mapped["User"] = relationship(foreign_keys=[shipper_id])
    dock: Mapped[Optional["FacilityLocation"]] = relationship(foreign_keys=[dock_id])
    yard_spot: Mapped[Optional["FacilityLocation"]] = relationship(foreign_keys=[yard_spot_id])
    asn: Mapped[Optional["ASN"]] = relationship(foreign_keys=[asn_id])
    evidence: Mapped[List["AppointmentEvidence"]] = relationship(back_populates="appointment")
    linked_asns: Mapped[List["AppointmentASN"]] = relationship(back_populates="appointment")


class AppointmentASN(Base):
    __tablename__ = "appointment_asns"
    __table_args__ = (
        UniqueConstraint("appointment_id", "asn_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    appointment_id: Mapped[int] = mapped_column(Integer, ForeignKey("appointments.id"), nullable=False)
    asn_id: Mapped[int] = mapped_column(Integer, ForeignKey("asns.id"), nullable=False)
    is_arrived: Mapped[bool] = mapped_column(Boolean, default=False)

    appointment: Mapped["Appointment"] = relationship(back_populates="linked_asns")
    asn: Mapped["ASN"] = relationship()


class AppointmentEvidence(Base):
    __tablename__ = "appointment_evidence"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    appointment_id: Mapped[int] = mapped_column(Integer, ForeignKey("appointments.id"), nullable=False)
    photo_type: Mapped[str] = mapped_column(String(25), nullable=False)
    file_path: Mapped[str] = mapped_column(Text, nullable=False)
    thumbnail_path: Mapped[Optional[str]] = mapped_column(Text)
    cloud_path: Mapped[Optional[str]] = mapped_column(Text)
    sync_status: Mapped[str] = mapped_column(String(10), default="SYNCED")
    gps_lat: Mapped[Optional[float]] = mapped_column(Numeric(10, 7))
    gps_lng: Mapped[Optional[float]] = mapped_column(Numeric(10, 7))
    taken_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    taken_by: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.id"))
    notes: Mapped[Optional[str]] = mapped_column(Text)
    litigation_hold: Mapped[bool] = mapped_column(Boolean, default=False)

    appointment: Mapped["Appointment"] = relationship(back_populates="evidence")


class BillingEvent(Base):
    __tablename__ = "billing_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    facility_id: Mapped[int] = mapped_column(Integer, ForeignKey("facilities.id"), nullable=False)
    appointment_id: Mapped[int] = mapped_column(Integer, ForeignKey("appointments.id"), nullable=False)
    shipper_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    event_type: Mapped[str] = mapped_column(String(20), nullable=False)  # DETENTION, NO_SHOW, OVERTIME, SHUNTING
    amount: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="USD")
    status: Mapped[str] = mapped_column(String(15), default="PENDING")  # PENDING, INVOICED, WAIVED, PAID
    free_period_end: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    billable_start: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    billable_end: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    waived_by: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.id"))
    waive_reason: Mapped[Optional[str]] = mapped_column(Text)
    liable_party: Mapped[str] = mapped_column(String(20), default="shipper")
    liable_note: Mapped[Optional[str]] = mapped_column(Text)
    rate_snapshot: Mapped[Optional[dict]] = mapped_column(JSONB)
    invoice_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("invoices.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    appointment: Mapped["Appointment"] = relationship()


class Invoice(Base):
    __tablename__ = "invoices"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    facility_id: Mapped[int] = mapped_column(Integer, ForeignKey("facilities.id"), nullable=False)
    shipper_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    invoice_number: Mapped[str] = mapped_column(String(30), unique=True, nullable=False)
    period_start: Mapped[datetime] = mapped_column(Date, nullable=False)
    period_end: Mapped[datetime] = mapped_column(Date, nullable=False)
    total_amount: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    status: Mapped[str] = mapped_column(String(15), default="DRAFT")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class BillingConfig(Base):
    __tablename__ = "billing_config"
    __table_args__ = (
        UniqueConstraint("facility_id", "config_key"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    facility_id: Mapped[int] = mapped_column(Integer, ForeignKey("facilities.id"), nullable=False)
    config_key: Mapped[str] = mapped_column(String(50), nullable=False)
    config_value: Mapped[dict] = mapped_column(JSONB, nullable=False)


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.id"))
    user_display: Mapped[Optional[str]] = mapped_column(String(100))
    action: Mapped[str] = mapped_column(String(50), nullable=False)
    target: Mapped[Optional[str]] = mapped_column(String(200))
    payload: Mapped[Optional[dict]] = mapped_column(JSONB)
    ip_address: Mapped[Optional[str]] = mapped_column(String(45))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Setting(Base):
    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[dict] = mapped_column(JSONB, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
