"""Durable one-shot local operator approval and n8n retry audit."""

import sqlalchemy as sa
from alembic import op

revision = "0004_approved_n8n_retry"
down_revision = "0003_incident_assessments"
branch_labels = None
depends_on = None


def upgrade():
    schema = "reliability" if op.get_bind().dialect.name == "postgresql" else None
    prefix = "reliability." if schema else ""
    op.create_table(
        "retry_actions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("check_id", sa.String(36), nullable=False),
        sa.Column("source_hash", sa.String(64), nullable=False),
        sa.Column("execution_id", sa.String(19), nullable=False),
        sa.Column("workflow_id", sa.String(64), nullable=False),
        sa.Column("mode", sa.String(8), nullable=False),
        sa.Column("state", sa.String(12), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("dispatch_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("new_execution_id", sa.String(19), nullable=True),
        sa.Column("provider_state", sa.String(12), nullable=True),
        sa.Column("reason", sa.String(40), nullable=True),
        sa.ForeignKeyConstraint(
            ["check_id"], [prefix + "incident_observations.check_id"], ondelete="RESTRICT"
        ),
        sa.UniqueConstraint("source_hash", "execution_id", name="retry_execution_once"),
        sa.CheckConstraint(
            "state IN ('PENDING','EXECUTING','ACCEPTED','REJECTED','UNKNOWN')",
            name="retry_action_state",
        ),
        sa.CheckConstraint("mode IN ('fixture','live')", name="retry_action_mode"),
        sa.CheckConstraint(
            "(state = 'PENDING' AND approved_at IS NULL) OR (state <> 'PENDING' "
            "AND approved_at IS NOT NULL)",
            name="retry_action_approval",
        ),
        sa.CheckConstraint(
            "(state IN ('PENDING','EXECUTING') AND completed_at IS NULL) OR (state "
            "IN ('ACCEPTED','REJECTED','UNKNOWN') AND completed_at IS NOT NULL)",
            name="retry_action_completion",
        ),
        sa.CheckConstraint(
            "(state = 'ACCEPTED' AND new_execution_id IS NOT NULL AND "
            "new_execution_id <> execution_id AND provider_state IS NOT NULL AND "
            "dispatch_started_at IS NOT NULL) OR (state <> 'ACCEPTED' AND "
            "new_execution_id IS NULL AND provider_state IS NULL)",
            name="retry_action_receipt",
        ),
        sa.CheckConstraint("expires_at > created_at", name="retry_action_expiry"),
        sa.CheckConstraint(
            "dispatch_started_at IS NULL OR approved_at IS NOT NULL",
            name="retry_action_dispatch_approval",
        ),
        sa.CheckConstraint(
            "(state IN ('REJECTED','UNKNOWN') AND reason IS NOT NULL) OR (state "
            "NOT IN ('REJECTED','UNKNOWN') AND reason IS NULL)",
            name="retry_action_failure_reason",
        ),
        sa.CheckConstraint(
            "state <> 'REJECTED' OR dispatch_started_at IS NULL", name="retry_action_rejection"
        ),
        sa.CheckConstraint(
            "state <> 'UNKNOWN' OR dispatch_started_at IS NOT NULL", name="retry_action_uncertain"
        ),
        sa.CheckConstraint(
            "provider_state IS NULL OR provider_state IN "
            "('canceled','crashed','error','new','running','success','unknown','waiting')",
            name="retry_action_provider_state",
        ),
        schema=schema,
    )


def downgrade():
    schema = "reliability" if op.get_bind().dialect.name == "postgresql" else None
    op.drop_table("retry_actions", schema=schema)
