"""Single fixed PostgreSQL probe. Credentials enter only through a private stdin pipe."""

import json
import sys

import psycopg
from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator

from app.tools.infrastructure_models import (
    DatabaseName,
    InfrastructureError,
    validate_database_host,
)
from app.tools.postgres import PostgresChecker
from app.tools.targets import validate_addresses


class ProbeInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, hide_input_in_errors=True)
    host: str = Field(max_length=253)
    hostaddr: str
    port: int
    dbname: DatabaseName
    user: DatabaseName
    password: SecretStr = Field(min_length=1, max_length=1024)
    timeout: float = Field(gt=0, le=30)

    @field_validator("host")
    @classmethod
    def valid_host(cls, value):
        return validate_database_host(value)

    @field_validator("hostaddr")
    @classmethod
    def valid_address(cls, value):
        return validate_addresses([value])[0]


def main():
    try:
        raw = sys.stdin.read(16385)
        if len(raw) > 16384:
            raise ValueError("Input too large")
        data = ProbeInput.model_validate_json(raw)
        checker = PostgresChecker(
            data.host,
            data.port,
            data.dbname,
            data.user,
            data.password,
            timeout=data.timeout,
            connect=psycopg.connect,
        )
        checker._lock.acquire()
        checker._probe(data.hostaddr)
        result = {"ok": True}
    except InfrastructureError as error:
        result = {"reason": error.code}
    except Exception:
        # Never echo input, DSNs, SQL errors, credentials, or tracebacks to the parent.
        result = {"reason": "database_check_failed"}
    sys.stdout.write(json.dumps(result))


if __name__ == "__main__":
    main()
