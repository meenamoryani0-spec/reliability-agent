"""Evidence-linked, concurrency-safe unresolved incident deduplication."""

import sqlalchemy as sa
from alembic import op

revision = "0002_incident_detection"
down_revision = "0001_history"
branch_labels = None
depends_on = None


def upgrade():
    connection = op.get_bind()
    schema = "reliability" if connection.dialect.name == "postgresql" else None
    prefix = "reliability." if schema else ""
    # Fail before DDL rather than discarding or silently merging historical records.
    invalid = connection.execute(
        sa.text(
            f"SELECT i.id FROM {prefix}incidents i LEFT JOIN {prefix}checks c "
            "ON c.id = i.detected_check_id AND c.service_id = i.service_id "
            "WHERE c.id IS NULL OR c.status <> 'UNHEALTHY' LIMIT 1"
        )
    ).first()
    duplicates = connection.execute(
        sa.text(
            f"SELECT i.service_id FROM {prefix}incidents i JOIN {prefix}checks c "
            "ON c.id = i.detected_check_id GROUP BY i.service_id, c.kind "
            "HAVING COUNT(*) > 1 LIMIT 1"
        )
    ).first()
    if invalid or duplicates:
        raise ValueError("Incident migration requires valid, nonduplicate unresolved history")
    op.create_index(
        "ux_checks_failure_reference",
        "checks",
        ["id", "service_id", "kind", "status"],
        unique=True,
        schema=schema,
    )
    op.add_column("incidents", sa.Column("kind", sa.String(32), nullable=True), schema=schema)
    op.add_column(
        "incidents",
        sa.Column("evidence_status", sa.String(20), nullable=False, server_default="UNHEALTHY"),
        schema=schema,
    )
    connection.execute(
        sa.text(
            f"UPDATE {prefix}incidents SET kind = (SELECT kind FROM {prefix}checks "
            f"WHERE {prefix}checks.id = {prefix}incidents.detected_check_id)"
        )
    )
    # Incidents have no incoming references yet, so SQLite's copy is safe with FKs on.
    with op.batch_alter_table("incidents", schema=schema) as batch:
        batch.alter_column("kind", existing_type=sa.String(32), nullable=False)
        batch.create_foreign_key(
            "incident_failure_reference",
            "checks",
            ["detected_check_id", "service_id", "kind", "evidence_status"],
            ["id", "service_id", "kind", "status"],
            referent_schema=schema,
            ondelete="RESTRICT",
        )
        batch.create_check_constraint("incident_unhealthy_only", "evidence_status = 'UNHEALTHY'")
        batch.create_unique_constraint("incident_identity_kind", ["id", "service_id", "kind"])
    active = sa.text("status IN ('OPEN','INVESTIGATING')")
    op.create_index(
        "ux_incidents_active_kind",
        "incidents",
        ["service_id", "kind"],
        unique=True,
        schema=schema,
        sqlite_where=active,
        postgresql_where=active,
    )
    op.create_table(
        "incident_observations",
        sa.Column("check_id", sa.String(36), primary_key=True),
        sa.Column("incident_id", sa.String(36), nullable=False),
        sa.Column("service_id", sa.String(36), nullable=False),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("check_status", sa.String(20), nullable=False, server_default="UNHEALTHY"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["incident_id", "service_id", "kind"],
            [prefix + "incidents.id", prefix + "incidents.service_id", prefix + "incidents.kind"],
            name="observation_incident_reference",
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
            name="observation_failure_reference",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint("check_status = 'UNHEALTHY'", name="observation_unhealthy_only"),
        schema=schema,
    )
    op.create_index(
        "ix_incident_observations_incident",
        "incident_observations",
        ["incident_id", "created_at", "check_id"],
        schema=schema,
    )
    connection.execute(
        sa.text(
            f"INSERT INTO {prefix}incident_observations "
            "(check_id, incident_id, service_id, kind, check_status, created_at) "
            "SELECT detected_check_id, id, service_id, kind, 'UNHEALTHY', created_at "
            f"FROM {prefix}incidents"
        )
    )


def downgrade():
    schema = "reliability" if op.get_bind().dialect.name == "postgresql" else None
    op.drop_table("incident_observations", schema=schema)
    op.drop_index("ux_incidents_active_kind", table_name="incidents", schema=schema)
    with op.batch_alter_table("incidents", schema=schema) as batch:
        batch.drop_constraint("incident_failure_reference", type_="foreignkey")
        batch.drop_constraint("incident_unhealthy_only", type_="check")
        batch.drop_constraint("incident_identity_kind", type_="unique")
        batch.drop_column("evidence_status")
        batch.drop_column("kind")
    op.drop_index("ux_checks_failure_reference", table_name="checks", schema=schema)
