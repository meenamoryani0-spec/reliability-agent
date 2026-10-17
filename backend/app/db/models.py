from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKeyConstraint,
    Index,
    MetaData,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.types import TypeDecorator

SCHEMA = "reliability"


def now():
    return datetime.now(UTC)


class UTCDateTime(TypeDecorator):
    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None or value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Timezone-aware timestamp required")
        return value.astimezone(UTC)

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


class Base(DeclarativeBase):
    metadata = MetaData(schema=SCHEMA)


class MonitoredService(Base):
    __tablename__ = "monitored_services"
    __table_args__ = (
        CheckConstraint("category IN ('website','n8n','infrastructure')", name="service_category"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    category: Mapped[str] = mapped_column(String(20))
    component: Mapped[str] = mapped_column(String(100))
    synthetic: Mapped[bool] = mapped_column(Boolean(create_constraint=True))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=now)


class StoredCheck(Base):
    __tablename__ = "checks"
    __table_args__ = (
        ForeignKeyConstraint(
            ["service_id"], [f"{SCHEMA}.monitored_services.id"], ondelete="RESTRICT"
        ),
        UniqueConstraint("id", "service_id", name="check_service_pair"),
        CheckConstraint(
            "status IN ('HEALTHY','UNHEALTHY','DEGRADED','UNKNOWN','CHECK_FAILED')",
            name="check_status",
        ),
        Index("ix_checks_service_observed", "service_id", "observed_at", "id"),
        Index("ix_checks_created", "created_at", "id"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    service_id: Mapped[str] = mapped_column(String(36))
    kind: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(20))
    observed_at: Mapped[datetime] = mapped_column(UTCDateTime())
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=now)
    payload: Mapped[dict] = mapped_column(JSON)


class Incident(Base):
    __tablename__ = "incidents"
    __table_args__ = (
        ForeignKeyConstraint(
            ["detected_check_id", "service_id"],
            [f"{SCHEMA}.checks.id", f"{SCHEMA}.checks.service_id"],
            ondelete="RESTRICT",
        ),
        CheckConstraint("status IN ('OPEN','INVESTIGATING')", name="incident_unresolved_only"),
        CheckConstraint("severity IN ('warning','high')", name="incident_severity"),
        UniqueConstraint("detected_check_id", name="incident_detection_once"),
        Index("ix_incidents_service_created", "service_id", "created_at", "id"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    service_id: Mapped[str] = mapped_column(String(36))
    detected_check_id: Mapped[str] = mapped_column(String(36))
    status: Mapped[str] = mapped_column(String(20), default="OPEN")
    severity: Mapped[str] = mapped_column(String(10), default="high")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=now)
    # Resolution and diagnosis fields are added with their verified workflows in later phases.
