"""Persist operator-registered public website targets separately from observations."""

import sqlalchemy as sa
from alembic import op

revision = "0006_operator_targets"
down_revision = "0005_verified_recovery"
branch_labels = None
depends_on = None


def upgrade():
    schema = "reliability" if op.get_bind().dialect.name == "postgresql" else None
    op.create_table(
        "website_targets",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("configuration", sa.JSON(), nullable=False),
        schema=schema,
    )


def downgrade():
    # Never discard an operator's saved targets through an incidental rollback.
    schema = "reliability" if op.get_bind().dialect.name == "postgresql" else None
    prefix = "reliability." if schema else ""
    count = op.get_bind().execute(sa.text(f"SELECT count(*) FROM {prefix}website_targets")).scalar()
    if count:
        raise RuntimeError("Saved website targets prevent downgrade")
    op.drop_table("website_targets", schema=schema)
