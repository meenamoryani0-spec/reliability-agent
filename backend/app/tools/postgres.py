"""A fixed SELECT probe with pinned DNS, verified TLS, and read-only sessions."""

import asyncio
import json
import math
import os
import subprocess
import sys
import threading
import time
from functools import partial
from pathlib import Path

import certifi
import psycopg
from pydantic import SecretStr

from app.tools.browser import stop_worker
from app.tools.dns import ResolutionError, resolve_addresses
from app.tools.infrastructure_models import InfrastructureError, validate_database_host
from app.tools.targets import TargetError, validate_addresses

PROBE_SQL = "SELECT 1, current_setting('transaction_read_only')"
PROJECT_ROOT = Path(__file__).resolve().parents[3]


class PostgresChecker:
    def __init__(
        self,
        host: str,
        port: int,
        dbname: str,
        user: str,
        password: SecretStr,
        *,
        timeout=10,
        nameservers=(),
        resolver=None,
        connect=None,
    ):
        self._host = validate_database_host(host)
        if port not in (5432, 6543):
            raise ValueError("Unsupported PostgreSQL port")
        self._port, self._dbname, self._user = port, dbname, user
        self._password, self._timeout = password, timeout
        self._resolver = resolver or partial(resolve_addresses, nameservers=nameservers)
        # Driver injection is reserved for local tests/fixtures. Live mode is process-isolated.
        self._connect = connect
        self._lock = threading.Lock()

    def _probe(self, address: str, budget: float | None = None) -> dict:
        try:
            if self._connect is None:
                return self._subprocess_probe(
                    address, budget if budget is not None else self._timeout
                )
            # No DSN or arbitrary SQL. hostaddr pins the socket; host preserves TLS identity.
            with self._connect(
                host=self._host,
                hostaddr=address,
                port=self._port,
                dbname=self._dbname,
                user=self._user,
                password=self._password.get_secret_value(),
                connect_timeout=max(2, math.ceil(self._timeout)),
                autocommit=True,
                sslmode="verify-full",
                sslrootcert=certifi.where(),
                sslcertmode="disable",
                gssencmode="disable",
                require_auth="scram-sha-256,password",
                application_name="reliability-agent-check",
                prepare_threshold=None,
                options="-c default_transaction_read_only=on -c statement_timeout="
                + str(max(1, int(self._timeout * 1000)))
                + " -c lock_timeout=1000 -c search_path=pg_catalog",
            ) as connection:
                row = connection.execute(PROBE_SQL, prepare=False).fetchone()
                if (
                    not isinstance(row, tuple)
                    or len(row) != 2
                    or type(row[0]) is not int
                    or row[0] != 1
                ):
                    raise InfrastructureError("invalid_response")
                if row[1] != "on":
                    raise InfrastructureError("read_only_not_verified")
            return {"select_one": True, "read_only_verified": True, "tls_policy": "verify-full"}
        except psycopg.Error:
            # Client/transport/authentication failure is not evidence the DB is unhealthy.
            raise InfrastructureError("database_check_failed") from None
        except OSError:
            raise InfrastructureError("database_check_failed") from None
        finally:
            self._lock.release()

    def _subprocess_probe(self, address: str, budget: float) -> dict:
        process = None
        try:
            worker_env = {
                key: value
                for key, value in os.environ.items()
                if key.upper() in {"SYSTEMROOT", "WINDIR", "PATH", "PATHEXT", "COMSPEC"}
            }
            temporary = PROJECT_ROOT / "work" / "tmp"
            temporary.mkdir(parents=True, exist_ok=True)
            worker_env.update(
                TEMP=str(temporary),
                TMP=str(temporary),
                PYTHONUTF8="1",
                PYTHONPYCACHEPREFIX=str(PROJECT_ROOT / "work" / "cache" / "pycache"),
            )
            request = json.dumps(
                {
                    "host": self._host,
                    "hostaddr": address,
                    "port": self._port,
                    "dbname": self._dbname,
                    "user": self._user,
                    "password": self._password.get_secret_value(),
                    "timeout": budget,
                }
            )
            process = subprocess.Popen(
                [sys.executable, "-m", "app.tools.postgres_worker"],
                cwd=PROJECT_ROOT / "backend",
                env=worker_env,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                encoding="utf-8",
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
                start_new_session=sys.platform != "win32",
            )
            output, _ = process.communicate(input=request, timeout=budget)
            if process.returncode != 0 or len(output) > 1024:
                raise InfrastructureError("database_worker_failed")
            try:
                result = json.loads(output)
            except (ValueError, RecursionError):
                raise InfrastructureError("database_worker_failed") from None
            if not (isinstance(result, dict) and set(result) == {"ok"} and result["ok"] is True):
                reason = result.get("reason") if isinstance(result, dict) else None
                if not isinstance(reason, str) or reason not in {
                    "database_check_failed",
                    "invalid_response",
                    "read_only_not_verified",
                }:
                    reason = "database_worker_failed"
                raise InfrastructureError(reason)
            return {"select_one": True, "read_only_verified": True, "tls_policy": "verify-full"}
        except subprocess.TimeoutExpired:
            raise InfrastructureError("timeout") from None
        except (OSError, UnicodeError):
            raise InfrastructureError("database_worker_failed") from None
        finally:
            if process is not None:
                try:
                    if process.poll() is None:
                        stop_worker(process)
                except (OSError, subprocess.TimeoutExpired):
                    raise InfrastructureError("database_worker_failed") from None
                finally:
                    for stream in (process.stdin, process.stdout):
                        if stream is not None:
                            stream.close()

    async def check(self) -> dict:
        try:
            deadline = time.monotonic() + self._timeout
            async with asyncio.timeout(self._timeout):
                addresses = validate_addresses(await self._resolver(self._host, self._timeout))
                budget = deadline - time.monotonic()
                if budget <= 0:
                    raise InfrastructureError("timeout")
                if not self._lock.acquire(blocking=False):
                    raise InfrastructureError("database_busy")
                # Keep the slot until the actual worker exits, including after caller timeout.
                worker = asyncio.create_task(asyncio.to_thread(self._probe, addresses[0], budget))
                worker.add_done_callback(
                    lambda task: task.exception() if not task.cancelled() else None
                )
                return await asyncio.shield(worker)
        except TimeoutError:
            raise InfrastructureError("timeout") from None
        except (TargetError, ResolutionError) as error:
            raise InfrastructureError(error.code) from None
