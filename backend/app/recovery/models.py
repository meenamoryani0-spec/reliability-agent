"""Immutable verification attempts; successful proof must reference a healthy stored check."""

from datetime import datetime
from uuid import uuid4

from sqlalchemy import JSON, CheckConstraint, ForeignKeyConstraint, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.actions.models import RetryAction  # noqa: F401 -- register referenced table
from app.db.models import SCHEMA, Base, UTCDateTime, now

RESOLUTION_CHECK = (
    "(status IN ('OPEN','INVESTIGATING') AND resolution_verification_id IS NULL "
    "AND resolution_result IS NULL AND resolved_at IS NULL AND resolution_scope IS NULL) OR "
    "(status = 'RESOLVED' AND resolution_verification_id IS NOT NULL "
    "AND resolution_result IS NOT NULL AND resolution_result = 'VERIFIED' "
    "AND resolved_at IS NOT NULL AND resolution_scope IS NOT NULL "
    "AND resolution_scope = 'n8n_required_nodes')"
)


class RecoveryVerification(Base):
    __tablename__ = "recovery_verifications"
    __table_args__ = (
        ForeignKeyConstraint(["action_id"], [f"{SCHEMA}.retry_actions.id"], ondelete="RESTRICT"),
        ForeignKeyConstraint(
            ["incident_id", "service_id", "kind"],
            [
                f"{SCHEMA}.incidents.id",
                f"{SCHEMA}.incidents.service_id",
                f"{SCHEMA}.incidents.kind",
            ],
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
            ondelete="RESTRICT",
        ),
        UniqueConstraint("id", "incident_id", "result", name="verification_incident_result"),
        CheckConstraint(
            "result IN ('VERIFIED','NOT_RECOVERED','INCONCLUSIVE')", name="verification_result"
        ),
        CheckConstraint("kind = 'execution'", name="verification_kind"),
        CheckConstraint(
            "result <> 'VERIFIED' OR (check_id IS NOT NULL AND "
            "check_status IS NOT NULL AND check_status = 'HEALTHY')",
            name="verification_healthy_proof",
        ),
        CheckConstraint(
            "(check_id IS NULL AND check_status IS NULL) OR "
            "(check_id IS NOT NULL AND check_status IS NOT NULL)",
            name="verification_check_pair",
        ),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    action_id: Mapped[str] = mapped_column(String(36))
    incident_id: Mapped[str] = mapped_column(String(36))
    service_id: Mapped[str] = mapped_column(String(36))
    kind: Mapped[str] = mapped_column(String(32), default="execution")
    check_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    check_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    result: Mapped[str] = mapped_column(String(20))
    reason: Mapped[str] = mapped_column(String(40))
    original_execution_id: Mapped[str] = mapped_column(String(19))
    new_execution_id: Mapped[str] = mapped_column(String(19))
    workflow_id: Mapped[str] = mapped_column(String(64))
    policy: Mapped[dict] = mapped_column(JSON)
    observed_at: Mapped[datetime] = mapped_column(UTCDateTime())
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=now)
