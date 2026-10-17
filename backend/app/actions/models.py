"""Persistent one-shot approval and dispatch audit; no recovery claims."""

from datetime import datetime
from uuid import uuid4

from sqlalchemy import CheckConstraint, ForeignKeyConstraint, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models import SCHEMA, Base, UTCDateTime, now

ACTION_CONSTRAINTS = {
    "retry_action_state": "state IN ('PENDING','EXECUTING','ACCEPTED','REJECTED','UNKNOWN')",
    "retry_action_mode": "mode IN ('fixture','live')",
    "retry_action_approval": "(state = 'PENDING' AND approved_at IS NULL) OR "
    "(state <> 'PENDING' AND approved_at IS NOT NULL)",
    "retry_action_completion": "(state IN ('PENDING','EXECUTING') AND completed_at IS NULL) OR "
    "(state IN ('ACCEPTED','REJECTED','UNKNOWN') AND completed_at IS NOT NULL)",
    "retry_action_receipt": "(state = 'ACCEPTED' AND new_execution_id IS NOT NULL AND "
    "new_execution_id <> execution_id AND provider_state IS NOT NULL AND "
    "dispatch_started_at IS NOT NULL) OR "
    "(state <> 'ACCEPTED' AND new_execution_id IS NULL AND provider_state IS NULL)",
    "retry_action_expiry": "expires_at > created_at",
    "retry_action_dispatch_approval": "dispatch_started_at IS NULL OR approved_at IS NOT NULL",
    "retry_action_failure_reason": "(state IN ('REJECTED','UNKNOWN') AND reason IS NOT NULL) OR "
    "(state NOT IN ('REJECTED','UNKNOWN') AND reason IS NULL)",
    "retry_action_rejection": "state <> 'REJECTED' OR dispatch_started_at IS NULL",
    "retry_action_uncertain": "state <> 'UNKNOWN' OR dispatch_started_at IS NOT NULL",
    "retry_action_provider_state": "provider_state IS NULL OR provider_state IN "
    "('canceled','crashed','error','new','running','success','unknown','waiting')",
}


class RetryAction(Base):
    __tablename__ = "retry_actions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["check_id"], [f"{SCHEMA}.incident_observations.check_id"], ondelete="RESTRICT"
        ),
        UniqueConstraint("source_hash", "execution_id", name="retry_execution_once"),
        *(CheckConstraint(value, name=name) for name, value in ACTION_CONSTRAINTS.items()),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    check_id: Mapped[str] = mapped_column(String(36))
    source_hash: Mapped[str] = mapped_column(String(64))
    execution_id: Mapped[str] = mapped_column(String(19))
    workflow_id: Mapped[str] = mapped_column(String(64))
    mode: Mapped[str] = mapped_column(String(8))
    state: Mapped[str] = mapped_column(String(12), default="PENDING")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=now)
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime())
    approved_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    dispatch_started_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    new_execution_id: Mapped[str | None] = mapped_column(String(19), nullable=True)
    provider_state: Mapped[str | None] = mapped_column(String(12), nullable=True)
    reason: Mapped[str | None] = mapped_column(String(40), nullable=True)
