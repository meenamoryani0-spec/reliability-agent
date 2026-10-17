import os
import re

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.engine import make_url

from app.config import PROJECT_ROOT, Settings
from app.db.database import create_storage_engine
from app.db.migrate import upgrade
from app.db.repository import HistoryRepository
from app.main import create_app


@pytest.fixture
def client():
    settings = Settings(_env_file=None, environment="test")
    with TestClient(create_app(settings)) as test_client:
        yield test_client


@pytest.fixture(params=("local", "postgresql"))
def database_config(request, tmp_path):
    if request.param == "local":
        return Settings(
            _env_file=None,
            storage_mode="local",
            storage_sqlite_file=str((tmp_path / "history.sqlite3").relative_to(PROJECT_ROOT)),
        )
    raw = os.environ.get("RA_TEST_POSTGRES_URL")
    if not raw:
        pytest.skip("Run scripts/postgres-integration.ps1 for isolated PostgreSQL tests")
    url = make_url(raw)
    if url.host != "127.0.0.1" or not re.fullmatch(r"ra_phase7_[0-9a-f]{16}", url.database or ""):
        pytest.fail("Refusing a non-isolated PostgreSQL test database")
    return Settings(
        _env_file=None,
        storage_mode="postgresql",
        storage_database_url=raw,
        storage_allow_loopback=True,
    )


@pytest.fixture
def engine(database_config):
    value = create_storage_engine(database_config)
    upgrade(value)
    try:
        yield value
    finally:
        # Only the dedicated fixture database is destroyed. Cyclic proof FKs
        # intentionally prevent downgrade once real recovery audit exists.
        from sqlalchemy import inspect

        from app.db.migrate import migration_transaction

        with migration_transaction(value) as connection:
            if value.dialect.name == "postgresql":
                connection.exec_driver_sql("DROP SCHEMA reliability CASCADE")
            else:
                for table in inspect(connection).get_table_names():
                    assert table in {
                        "monitored_services",
                        "checks",
                        "incidents",
                        "incident_observations",
                        "incident_assessments",
                        "retry_actions",
                        "recovery_verifications",
                        "ra_schema_version",
                    }
                    connection.exec_driver_sql(f'DROP TABLE "{table}"')
        value.dispose()


@pytest.fixture
def repository(engine):
    return HistoryRepository(engine)
