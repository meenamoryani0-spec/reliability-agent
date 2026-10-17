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
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.types import TypeDecorator

SCHEMA = "reliability"
ACTIVE_INCIDENT = text("status IN ('OPEN','INVESTIGATING')")


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
        Index("ux_checks_failure_reference", "id", "service_id", "kind", "status", unique=True),
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
        # A successful same-incident verification is required at the database boundary.
        ForeignKeyConstraint(
            ["resolution_verification_id", "id", "resolution_result"],
            [
                f"{SCHEMA}.recovery_verifications.id",
                f"{SCHEMA}.recovery_verifications.incident_id",
                f"{SCHEMA}.recovery_verifications.result",
            ],
            name="incident_resolution_proof",
            ondelete="RESTRICT",
            use_alter=True,
        ),
        CheckConstraint(
            "(status IN ('OPEN','INVESTIGATING') AND resolution_verification_id IS NULL "
            "AND resolution_result IS NULL AND resolved_at IS NULL "
            "AND resolution_scope IS NULL) OR "
            "(status = 'RESOLVED' AND resolution_verification_id IS NOT NULL "
            "AND resolution_result IS NOT NULL AND resolution_result = 'VERIFIED' "
            "AND resolved_at IS NOT NULL AND resolution_scope IS NOT NULL "
            "AND resolution_scope = 'n8n_required_nodes')",
            name="incident_resolution_required",
        ),
        CheckConstraint("severity IN ('warning','high')", name="incident_severity"),
        UniqueConstraint("detected_check_id", name="incident_detection_once"),
        ForeignKeyConstraint(
            ["detected_check_id", "service_id", "kind", "evidence_status"],
            [
                f"{SCHEMA}.checks.id",
                f"{SCHEMA}.checks.service_id",
                f"{SCHEMA}.checks.kind",
                f"{SCHEMA}.checks.status",
            ],
            name="incident_failure_reference",
            ondelete="RESTRICT",
        ),
        CheckConstraint("evidence_status = 'UNHEALTHY'", name="incident_unhealthy_only"),
        UniqueConstraint("id", "service_id", "kind", name="incident_identity_kind"),
        Index(
            "ux_incidents_active_kind",
            "service_id",
            "kind",
            unique=True,
            sqlite_where=ACTIVE_INCIDENT,
            postgresql_where=ACTIVE_INCIDENT,
        ),
        Index("ix_incidents_service_created", "service_id", "created_at", "id"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    service_id: Mapped[str] = mapped_column(String(36))
    detected_check_id: Mapped[str] = mapped_column(String(36))
    kind: Mapped[str] = mapped_column(String(32))
    evidence_status: Mapped[str] = mapped_column(
        String(20), default="UNHEALTHY", server_default="UNHEALTHY"
    )
    status: Mapped[str] = mapped_column(String(20), default="OPEN")
    severity: Mapped[str] = mapped_column(String(10), default="high")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=now)
    resolution_verification_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    resolution_result: Mapped[str | None] = mapped_column(String(20), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    resolution_scope: Mapped[str | None] = mapped_column(String(32), nullable=True)


class IncidentObservation(Base):
    __tablename__ = "incident_observations"
    __table_args__ = (
        ForeignKeyConstraint(
            ["incident_id", "service_id", "kind"],
            [
                f"{SCHEMA}.incidents.id",
                f"{SCHEMA}.incidents.service_id",
                f"{SCHEMA}.incidents.kind",
            ],
            name="observation_incident_reference",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["check_id", "service_id", "kind", "check_status"],
            [
                f"{SCHEMA}.checks.id",
                f"{SCHEMA}.checks.service_id",
                f"{SCHEMA}.checks.kind",
                f"{SCHEMA}.checks.status",
            ],
            name="observation_failure_reference",
            ondelete="RESTRICT",
        ),
        CheckConstraint("check_status = 'UNHEALTHY'", name="observation_unhealthy_only"),
        Index("ix_incident_observations_incident", "incident_id", "created_at", "check_id"),
    )
    check_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    incident_id: Mapped[str] = mapped_column(String(36))
    service_id: Mapped[str] = mapped_column(String(36))
    kind: Mapped[str] = mapped_column(String(32))
    check_status: Mapped[str] = mapped_column(
        String(20), default="UNHEALTHY", server_default="UNHEALTHY"
    )
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=now)


class IncidentAssessment(Base):
    __tablename__ = "incident_assessments"
    __table_args__ = (
        ForeignKeyConstraint(
            ["check_id"], [f"{SCHEMA}.incident_observations.check_id"], ondelete="RESTRICT"
        ),
        CheckConstraint(
            "hypothesis IN ('authentication_rejection','permission_rejection','rate_limiting',"
            "'upstream_error','workflow_failure','website_failure','deployment_failure',"
            "'infrastructure_failure','unknown')",
            name="assessment_hypothesis",
        ),
        CheckConstraint("root_cause IS NULL", name="assessment_unverified_cause"),
        CheckConstraint(
            "inference_source IN ('scripted_fixture','nebius')", name="assessment_inference_source"
        ),
    )
    check_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    hypothesis: Mapped[str] = mapped_column(String(32))
    recommended_steps: Mapped[list] = mapped_column(JSON)
    inference_source: Mapped[str] = mapped_column(String(20))
    root_cause: Mapped[str | None] = mapped_column(String(200), nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=now)
