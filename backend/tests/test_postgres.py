import asyncio
import json
import os
import subprocess
import sys
import threading
import time
from unittest.mock import Mock

import psycopg
import pytest
from psycopg.conninfo import make_conninfo
from pydantic import SecretStr

from app.tools.infrastructure_models import InfrastructureError
from app.tools.postgres import PROBE_SQL, PROJECT_ROOT, PostgresChecker

PASSWORD = "PRIVATE_DATABASE_PASSWORD"


async def public_resolver(_host, _timeout):
    return ["93.184.216.34"]


def checker(connect, **kwargs):
    return PostgresChecker(
        "db.example.com",
        5432,
        "postgres",
        "probe_user",
        SecretStr(PASSWORD),
        resolver=kwargs.pop("resolver", public_resolver),
        connect=connect,
        **kwargs,
    )


def connection_returning(row):
    connection = Mock()
    connection.__enter__ = Mock(return_value=connection)
    connection.__exit__ = Mock(return_value=False)
    connection.execute.return_value.fetchone.return_value = row
    return connection


def test_fixed_select_pinned_hostaddr_verified_tls_and_read_only_policy():
    connection = connection_returning((1, "on"))
    connect = Mock(return_value=connection)
    result = asyncio.run(checker(connect).check())
    assert result == {"select_one": True, "read_only_verified": True, "tls_policy": "verify-full"}
    params = connect.call_args.kwargs
    assert params["hostaddr"] == "93.184.216.34" and params["host"] == "db.example.com"
    assert params["sslmode"] == "verify-full"
    assert params["sslcertmode"] == "disable" and params["gssencmode"] == "disable"
    assert params["require_auth"] == "scram-sha-256,password"
    assert "default_transaction_read_only=on" in params["options"]
    assert "statement_timeout=10000" in params["options"]
    assert params["autocommit"] is True and params["password"] == PASSWORD
    # Installed libpq accepts every connection parameter, without opening a connection.
    libpq_params = {
        key: value
        for key, value in params.items()
        if key not in {"autocommit", "prepare_threshold"}
    }
    make_conninfo(**libpq_params)
    connection.execute.assert_called_once_with(PROBE_SQL, prepare=False)
    connection.__exit__.assert_called_once()


@pytest.mark.parametrize(
    "row,reason",
    [
        ((1, "off"), "read_only_not_verified"),
        ((True, "on"), "invalid_response"),
        ((0, "on"), "invalid_response"),
        (None, "invalid_response"),
        ((1,), "invalid_response"),
        ((1, "on", PASSWORD), "invalid_response"),
    ],
)
def test_unverified_probe_results_never_claim_health(row, reason):
    connection = connection_returning(row)
    with pytest.raises(InfrastructureError) as caught:
        asyncio.run(checker(Mock(return_value=connection)).check())
    assert caught.value.code == reason and PASSWORD not in str(caught.value)
    connection.__exit__.assert_called_once()


@pytest.mark.parametrize(
    "error",
    [
        psycopg.OperationalError(PASSWORD),
        psycopg.errors.InvalidPassword(PASSWORD),
        psycopg.errors.QueryCanceled(PASSWORD),
        OSError(PASSWORD),
    ],
)
def test_driver_failures_are_sanitized_and_slot_is_released(error):
    connect = Mock(side_effect=error)
    probe = checker(connect)
    for _ in range(2):
        with pytest.raises(InfrastructureError, match="database_check_failed") as caught:
            asyncio.run(probe.check())
        assert PASSWORD not in str(caught.value)
    assert connect.call_count == 2


def test_query_failure_closes_connection_and_hides_driver_message():
    connection = connection_returning((1, "on"))
    connection.execute.side_effect = psycopg.OperationalError(PASSWORD)
    with pytest.raises(InfrastructureError, match="database_check_failed"):
        asyncio.run(checker(Mock(return_value=connection)).check())
    connection.__exit__.assert_called_once()


@pytest.mark.parametrize("addresses", [["127.0.0.1"], ["93.184.216.34", "10.0.0.1"], []])
def test_private_or_mixed_dns_never_sends_database_password(addresses):
    async def resolver(_host, _timeout):
        return addresses

    connect = Mock()
    with pytest.raises(InfrastructureError):
        asyncio.run(checker(connect, resolver=resolver).check())
    connect.assert_not_called()


def test_slow_dns_has_a_total_deadline_without_starting_a_worker():
    async def resolver(_host, _timeout):
        await asyncio.sleep(0.1)
        return ["93.184.216.34"]

    connect = Mock()
    with pytest.raises(InfrastructureError, match="timeout"):
        asyncio.run(checker(connect, resolver=resolver, timeout=0.01).check())
    connect.assert_not_called()


def test_timed_out_worker_keeps_slot_until_actual_cleanup():
    started, release = threading.Event(), threading.Event()

    def connect(**_kwargs):
        started.set()
        release.wait(timeout=1)
        return connection_returning((1, "on"))

    probe = checker(connect, timeout=0.03)

    async def run():
        try:
            with pytest.raises(InfrastructureError, match="timeout"):
                await probe.check()
            assert started.is_set()
            with pytest.raises(InfrastructureError, match="database_busy"):
                await probe.check()
        finally:
            release.set()
        for _ in range(100):
            if not probe._lock.locked():
                break
            await asyncio.sleep(0.01)
        assert not probe._lock.locked()
        assert (await probe.check())["select_one"] is True

    before = time.monotonic()
    asyncio.run(run())
    assert time.monotonic() - before < 2


def isolated_checker():
    return PostgresChecker(
        "db.example.com",
        5432,
        "postgres",
        "probe_user",
        SecretStr(PASSWORD),
        resolver=public_resolver,
    )


def mock_worker(monkeypatch, output='{"ok":true}'):
    process = Mock(returncode=0)
    process.communicate.return_value = (output, None)
    process.poll.return_value = 0
    popen = Mock(return_value=process)
    monkeypatch.setattr("app.tools.postgres.subprocess.Popen", popen)
    return process, popen


def test_live_driver_worker_uses_stdin_and_excludes_other_credentials(monkeypatch):
    monkeypatch.setenv("NEBIUS_API_KEY", PASSWORD)
    monkeypatch.setenv("PGSERVICE", PASSWORD)
    monkeypatch.setenv("HTTPS_PROXY", PASSWORD)
    process, popen = mock_worker(monkeypatch)
    assert asyncio.run(isolated_checker().check())["select_one"]
    assert PASSWORD not in json.dumps(popen.call_args.args)
    assert not {"PGSERVICE", "NEBIUS_API_KEY", "HTTPS_PROXY"} & popen.call_args.kwargs["env"].keys()
    request = json.loads(process.communicate.call_args.kwargs["input"])
    assert request["password"] == PASSWORD and request["hostaddr"] == "93.184.216.34"
    assert popen.call_args.kwargs["env"]["TEMP"].startswith(str(PROJECT_ROOT))
    assert popen.call_args.kwargs["stderr"] == subprocess.DEVNULL


@pytest.mark.parametrize(
    "output",
    [
        "bad json",
        "[]",
        "{}",
        '{"ok":1}',
        '{"reason":[]}',
        '{"reason":"' + PASSWORD + '"}',
        "x" * 1025,
    ],
)
def test_invalid_worker_output_is_sanitized(monkeypatch, output):
    mock_worker(monkeypatch, output)
    with pytest.raises(InfrastructureError, match="database_worker_failed") as caught:
        asyncio.run(isolated_checker().check())
    assert PASSWORD not in str(caught.value)


def test_stalled_database_worker_is_terminated(monkeypatch):
    process, _ = mock_worker(monkeypatch)
    process.communicate.side_effect = subprocess.TimeoutExpired("worker", 10)
    process.poll.return_value = None
    cleanup = Mock()
    monkeypatch.setattr("app.tools.postgres.stop_worker", cleanup)
    probe = isolated_checker()
    with pytest.raises(InfrastructureError, match="timeout"):
        asyncio.run(probe.check())
    cleanup.assert_called_once_with(process)
    assert not probe._lock.locked()
    process.stdin.close.assert_called_once()
    process.stdout.close.assert_called_once()


def test_real_worker_rejects_invalid_input_without_echoing_it():
    response = subprocess.run(
        [sys.executable, "-m", "app.tools.postgres_worker"],
        cwd=PROJECT_ROOT / "backend",
        input=json.dumps({"password": PASSWORD}),
        capture_output=True,
        text=True,
        timeout=10,
        creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        env={**os.environ, "PYTHONUTF8": "1"},
    )
    assert response.returncode == 0
    assert json.loads(response.stdout) == {"reason": "database_check_failed"}
    assert PASSWORD not in response.stdout + response.stderr
