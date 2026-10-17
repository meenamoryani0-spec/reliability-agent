"""Persist evidence-supported investigation assessments without claiming root cause."""

import sqlalchemy as sa
from alembic import op

revision = "0003_incident_assessments"
down_revision = "0002_incident_detection"
branch_labels = None
depends_on = None


def upgrade():
    schema = "reliability" if op.get_bind().dialect.name == "postgresql" else None
    prefix = "reliability." if schema else ""
    op.create_table(
        "incident_assessments",
        sa.Column("check_id", sa.String(36), primary_key=True),
        sa.Column("hypothesis", sa.String(32), nullable=False),
        sa.Column("recommended_steps", sa.JSON(), nullable=False),
        sa.Column("inference_source", sa.String(20), nullable=False),
        sa.Column("root_cause", sa.String(200), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["check_id"], [prefix + "incident_observations.check_id"], ondelete="RESTRICT"
        ),
        sa.CheckConstraint(
            "hypothesis IN ('authentication_rejection','permission_rejection','rate_limiting',"
            "'upstream_error','workflow_failure','website_failure','deployment_failure',"
            "'infrastructure_failure','unknown')",
            name="assessment_hypothesis",
        ),
        sa.CheckConstraint("root_cause IS NULL", name="assessment_unverified_cause"),
        sa.CheckConstraint(
            "inference_source IN ('scripted_fixture','nebius')", name="assessment_inference_source"
        ),
        schema=schema,
    )


def downgrade():
    schema = "reliability" if op.get_bind().dialect.name == "postgresql" else None
    op.drop_table("incident_assessments", schema=schema)
