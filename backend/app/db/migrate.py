"""Programmatic Alembic configuration with no credentials in ini files or logs."""

from contextlib import contextmanager
from io import StringIO
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from sqlalchemy import text

from app.db.models import SCHEMA

HEAD = "0006_operator_targets"


def migration_config(connection):
    config = Config(stdout=StringIO(), output_buffer=StringIO())
    config.set_main_option("script_location", str(Path(__file__).parent / "migrations"))
    config.attributes["connection"] = connection
    return config


@contextmanager
def migration_transaction(engine):
    # SQLite batch table rebuilds require incoming FKs off on this dedicated
    # connection only. BEGIN IMMEDIATE excludes concurrent application writers;
    # verify every FK before committing and restore enforcement on every exit.
    with engine.connect() as connection:
        sqlite = connection.dialect.name == "sqlite"
        raw = connection.connection.driver_connection
        if sqlite:
            raw.execute("PRAGMA foreign_keys=OFF")
            connection = connection.execution_options(sqlite_write=True)
        try:
            with connection.begin():
                yield connection
                if sqlite and connection.exec_driver_sql("PRAGMA foreign_key_check").first():
                    raise RuntimeError("Migration foreign-key validation failed")
        finally:
            if sqlite:
                raw.execute("PRAGMA foreign_keys=ON")


def upgrade(engine):
    with migration_transaction(engine) as connection:
        if connection.dialect.name == "postgresql":
            connection.execute(text("CREATE SCHEMA IF NOT EXISTS reliability"))
        command.upgrade(migration_config(connection), "head")


def downgrade(engine, revision):
    with migration_transaction(engine) as connection:
        command.downgrade(migration_config(connection), revision)


def current_revision(engine):
    with engine.connect() as connection:
        schema = SCHEMA if engine.dialect.name == "postgresql" else None
        context = MigrationContext.configure(
            connection, opts={"version_table": "ra_schema_version", "version_table_schema": schema}
        )
        return context.get_current_revision()
