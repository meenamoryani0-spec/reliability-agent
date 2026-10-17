"""Explicit engine configuration. Startup never creates or migrates tables."""

from pathlib import Path

import certifi
from sqlalchemy import create_engine, event
from sqlalchemy.engine import URL, make_url
from sqlalchemy.pool import NullPool

from app.db.models import SCHEMA

PROJECT_ROOT = Path(__file__).resolve().parents[3]


def create_storage_engine(config):
    if config.storage_mode == "disabled":
        return None
    if config.storage_mode == "local":
        path = (PROJECT_ROOT / config.storage_sqlite_file).resolve()
        path.parent.mkdir(parents=True, exist_ok=True)
        engine = create_engine(
            URL.create("sqlite+pysqlite", database=str(path)),
            connect_args={"check_same_thread": False, "timeout": 5},
            execution_options={"schema_translate_map": {SCHEMA: None}},
            poolclass=NullPool,
            hide_parameters=True,
        )

        @event.listens_for(engine, "connect")
        def configure_sqlite(connection, _record):
            connection.isolation_level = None
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute("PRAGMA busy_timeout=5000")

        @event.listens_for(engine, "begin")
        def explicit_transaction(connection):
            connection.exec_driver_sql(
                "BEGIN IMMEDIATE"
                if connection.get_execution_options().get("sqlite_write")
                else "BEGIN"
            )

        return engine
    url = make_url(config.storage_database_url.get_secret_value())
    loopback = url.host in {"127.0.0.1", "localhost"}
    args = {
        "connect_timeout": 5,
        "options": "-c statement_timeout=5000 -c lock_timeout=2000",
        "sslmode": "disable" if loopback else "verify-full",
        "gssencmode": "disable",
        "sslcertmode": "disable",
        "require_auth": "scram-sha-256,password",
    }
    if not loopback:
        args["sslrootcert"] = config.storage_ssl_ca_file or certifi.where()
    return create_engine(url, connect_args=args, poolclass=NullPool, hide_parameters=True)
