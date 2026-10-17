from alembic import context

from app.db.models import SCHEMA, Base

connection = context.config.attributes["connection"]
context.configure(
    connection=connection,
    target_metadata=Base.metadata,
    version_table="ra_schema_version",
    version_table_schema=SCHEMA if connection.dialect.name == "postgresql" else None,
)
with context.begin_transaction():
    context.run_migrations()
