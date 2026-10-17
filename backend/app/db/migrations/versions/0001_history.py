"""Initial service/check/incident history. No customer/provider tables are changed."""

import sqlalchemy as sa
from alembic import op

revision = "0001_history"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    schema = "reliability" if op.get_bind().dialect.name == "postgresql" else None
    prefix = f"{schema}." if schema else ""
    op.create_table(
        "monitored_services",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("category", sa.String(20), nullable=False),
        sa.Column("component", sa.String(100), nullable=False),
        sa.Column("synthetic", sa.Boolean(create_constraint=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "category IN ('website','n8n','infrastructure')", name="service_category"
        ),
        schema=schema,
    )
    op.create_table(
        "checks",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("service_id", sa.String(36), nullable=False),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(
            ["service_id"], [prefix + "monitored_services.id"], ondelete="RESTRICT"
        ),
        sa.UniqueConstraint("id", "service_id", name="check_service_pair"),
        sa.CheckConstraint(
            "status IN ('HEALTHY','UNHEALTHY','DEGRADED','UNKNOWN','CHECK_FAILED')",
            name="check_status",
        ),
        schema=schema,
    )
    op.create_index(
        "ix_checks_service_observed", "checks", ["service_id", "observed_at", "id"], schema=schema
    )
    op.create_index("ix_checks_created", "checks", ["created_at", "id"], schema=schema)
    op.create_table(
        "incidents",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("service_id", sa.String(36), nullable=False),
        sa.Column("detected_check_id", sa.String(36), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("severity", sa.String(10), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["detected_check_id", "service_id"],
            [prefix + "checks.id", prefix + "checks.service_id"],
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint("status IN ('OPEN','INVESTIGATING')", name="incident_unresolved_only"),
        sa.CheckConstraint("severity IN ('warning','high')", name="incident_severity"),
        sa.UniqueConstraint("detected_check_id", name="incident_detection_once"),
        schema=schema,
    )
    op.create_index(
        "ix_incidents_service_created",
        "incidents",
        ["service_id", "created_at", "id"],
        schema=schema,
    )


def downgrade():
    schema = "reliability" if op.get_bind().dialect.name == "postgresql" else None
    op.drop_table("incidents", schema=schema)
    op.drop_table("checks", schema=schema)
    op.drop_table("monitored_services", schema=schema)
