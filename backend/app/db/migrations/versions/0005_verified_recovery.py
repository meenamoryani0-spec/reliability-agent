"""Scoped n8n verification proof and guarded incident resolution."""

import sqlalchemy as sa
from alembic import op

revision = "0005_verified_recovery"
down_revision = "0004_approved_n8n_retry"
branch_labels = None
depends_on = None

RESOLUTION_CHECK = (
    "(status IN ('OPEN','INVESTIGATING') AND resolution_verification_id IS NULL "
    "AND resolution_result IS NULL AND resolved_at IS NULL AND resolution_scope IS NULL) OR "
    "(status = 'RESOLVED' AND resolution_verification_id IS NOT NULL "
    "AND resolution_result IS NOT NULL AND resolution_result = 'VERIFIED' "
    "AND resolved_at IS NOT NULL AND resolution_scope IS NOT NULL "
    "AND resolution_scope = 'n8n_required_nodes')"
)


def upgrade():
    schema = "reliability" if op.get_bind().dialect.name == "postgresql" else None
    prefix = "reliability." if schema else ""
    op.create_table(
        "recovery_verifications",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("action_id", sa.String(36), nullable=False),
        sa.Column("incident_id", sa.String(36), nullable=False),
        sa.Column("service_id", sa.String(36), nullable=False),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("check_id", sa.String(36), nullable=True),
        sa.Column("check_status", sa.String(20), nullable=True),
        sa.Column("result", sa.String(20), nullable=False),
        sa.Column("reason", sa.String(40), nullable=False),
        sa.Column("original_execution_id", sa.String(19), nullable=False),
        sa.Column("new_execution_id", sa.String(19), nullable=False),
        sa.Column("workflow_id", sa.String(64), nullable=False),
        sa.Column("policy", sa.JSON(), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["action_id"], [prefix + "retry_actions.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["incident_id", "service_id", "kind"],
            [prefix + "incidents.id", prefix + "incidents.service_id", prefix + "incidents.kind"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["check_id", "service_id", "kind", "check_status"],
            [
                prefix + "checks.id",
                prefix + "checks.service_id",
                prefix + "checks.kind",
                prefix + "checks.status",
            ],
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint("id", "incident_id", "result", name="verification_incident_result"),
        sa.CheckConstraint(
            "result IN ('VERIFIED','NOT_RECOVERED','INCONCLUSIVE')", name="verification_result"
        ),
        sa.CheckConstraint("kind = 'execution'", name="verification_kind"),
        sa.CheckConstraint(
            "result <> 'VERIFIED' OR (check_id IS NOT NULL AND "
            "check_status IS NOT NULL AND check_status = 'HEALTHY')",
            name="verification_healthy_proof",
        ),
        sa.CheckConstraint(
            "(check_id IS NULL AND check_status IS NULL) OR "
            "(check_id IS NOT NULL AND check_status IS NOT NULL)",
            name="verification_check_pair",
        ),
        schema=schema,
    )
    with op.batch_alter_table("incidents", schema=schema) as batch:
        batch.add_column(sa.Column("resolution_verification_id", sa.String(36), nullable=True))
        batch.add_column(sa.Column("resolution_result", sa.String(20), nullable=True))
        batch.add_column(sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column("resolution_scope", sa.String(32), nullable=True))
        batch.drop_constraint("incident_unresolved_only", type_="check")
        batch.create_check_constraint("incident_resolution_required", RESOLUTION_CHECK)
        batch.create_foreign_key(
            "incident_resolution_proof",
            "recovery_verifications",
            ["resolution_verification_id", "id", "resolution_result"],
            ["id", "incident_id", "result"],
            referent_schema=schema,
            ondelete="RESTRICT",
        )


def downgrade():
    schema = "reliability" if op.get_bind().dialect.name == "postgresql" else None
    prefix = "reliability." if schema else ""
    # Never erase recovery history or silently reopen a resolved incident.
    if (
        op.get_bind()
        .execute(sa.text(f"SELECT 1 FROM {prefix}recovery_verifications LIMIT 1"))
        .first()
    ):
        raise RuntimeError("Recovery history prevents downgrade; retain the verified schema")
    with op.batch_alter_table("incidents", schema=schema) as batch:
        batch.drop_constraint("incident_resolution_proof", type_="foreignkey")
        batch.drop_constraint("incident_resolution_required", type_="check")
        batch.create_check_constraint(
            "incident_unresolved_only", "status IN ('OPEN','INVESTIGATING')"
        )
        for name in (
            "resolution_verification_id",
            "resolution_result",
            "resolved_at",
            "resolution_scope",
        ):
            batch.drop_column(name)
    op.drop_table("recovery_verifications", schema=schema)
