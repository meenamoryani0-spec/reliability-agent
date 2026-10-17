"""Programmatic Alembic configuration with no credentials in ini files or logs."""

from io import StringIO
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from sqlalchemy import text

from app.db.models import SCHEMA

HEAD = "0004_approved_n8n_retry"


def migration_config(connection):
    config = Config(stdout=StringIO(), output_buffer=StringIO())
    config.set_main_option("script_location", str(Path(__file__).parent / "migrations"))
    config.attributes["connection"] = connection
    return config


def upgrade(engine):
    with engine.begin() as connection:
        if connection.dialect.name == "postgresql":
            connection.execute(text("CREATE SCHEMA IF NOT EXISTS reliability"))
        command.upgrade(migration_config(connection), "head")


def current_revision(engine):
    with engine.connect() as connection:
        schema = SCHEMA if engine.dialect.name == "postgresql" else None
        context = MigrationContext.configure(
            connection, opts={"version_table": "ra_schema_version", "version_table_schema": schema}
        )
        return context.get_current_revision()
