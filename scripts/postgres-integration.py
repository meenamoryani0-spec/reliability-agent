"""Run the test suite with an isolated, loopback-only PostgreSQL cluster on D:."""

import argparse
import json
import os
import secrets
import socket
import subprocess
import tempfile
from pathlib import Path

import psycopg
from psycopg import sql
from sqlalchemy.engine import URL

ROOT = Path(__file__).resolve().parents[1]
HIDDEN = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--bin-dir", type=Path, required=True)
    parser.add_argument("--powershell", type=Path, required=True)
    args = parser.parse_args()
    bins = args.bin_dir.resolve()
    if not bins.is_relative_to((ROOT / "work").resolve()):
        raise SystemExit("Test PostgreSQL binaries must be inside project work/")
    for name in ("initdb.exe", "pg_ctl.exe"):
        if not (bins / name).is_file():
            raise SystemExit("PostgreSQL test binaries are missing")
    workspace = ROOT / "work" / "postgres-tests"
    workspace.mkdir(parents=True, exist_ok=True)
    directory = Path(tempfile.mkdtemp(prefix="cluster-", dir=workspace))
    data = directory / "data"
    password = secrets.token_urlsafe(32)
    password_file = directory / "password.txt"
    password_file.write_text(password, encoding="utf-8")
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    server_env = {
        key: value
        for key, value in os.environ.items()
        if key.upper() in {"SYSTEMROOT", "WINDIR", "PATH", "PATHEXT", "COMSPEC", "TEMP", "TMP"}
    }
    started = False
    try:
        with (directory / "initdb.log").open("w", encoding="utf-8") as output:
            subprocess.run(
                [
                    str(bins / "initdb.exe"),
                    "-D",
                    str(data),
                    "-U",
                    "ra_test",
                    "--pwfile=" + str(password_file),
                    "--auth=scram-sha-256",
                    "--no-locale",
                    "--encoding=UTF8",
                ],
                env=server_env,
                stdout=output,
                stderr=subprocess.STDOUT,
                timeout=60,
                check=True,
                creationflags=HIDDEN,
            )
        password_file.unlink()
        started = True
        subprocess.run(
            [
                str(bins / "pg_ctl.exe"),
                "-D",
                str(data),
                "-l",
                str(directory / "server.log"),
                "-o",
                f"-h 127.0.0.1 -p {port}",
                "-w",
                "-t",
                "20",
                "start",
            ],
            env=server_env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=30,
            check=True,
            creationflags=HIDDEN,
        )
        started = True
        database = "ra_phase7_" + secrets.token_hex(8)
        with psycopg.connect(
            host="127.0.0.1",
            port=port,
            user="ra_test",
            password=password,
            dbname="postgres",
            sslmode="disable",
            gssencmode="disable",
            connect_timeout=5,
            autocommit=True,
        ) as connection:
            connection.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(database)))
        url = URL.create(
            "postgresql+psycopg",
            username="ra_test",
            password=password,
            host="127.0.0.1",
            port=port,
            database=database,
        )
        log_dir = ROOT / "work" / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        suite_log = log_dir / "phase-7-postgresql-tests.log"
        with suite_log.open("w", encoding="utf-8") as output:
            result = subprocess.run(
                [str(args.powershell), "-NoProfile", "-File", str(ROOT / "scripts" / "test.ps1")],
                env={
                    **os.environ,
                    "RA_TEST_POSTGRES_URL": url.render_as_string(hide_password=False),
                },
                cwd=ROOT,
                stdout=output,
                stderr=subprocess.STDOUT,
                creationflags=HIDDEN,
            )
        lines = suite_log.read_text(encoding="utf-8").splitlines()
        print("\n".join(lines[-60:] if result.returncode else lines[-6:]))
        evidence = {
            "result": "PASS" if result.returncode == 0 else "FAIL",
            "database": "isolated_local_postgresql",
            "listen_address": "127.0.0.1",
            "cloud_database_accessed": False,
        }
        (ROOT / "work" / "evidence").mkdir(parents=True, exist_ok=True)
        (ROOT / "work" / "evidence" / "phase-7-postgresql.json").write_text(
            json.dumps(evidence, indent=2)
        )
        return result.returncode
    finally:
        if started and (data / "postmaster.pid").exists():
            subprocess.run(
                [str(bins / "pg_ctl.exe"), "-D", str(data), "-m", "fast", "-w", "-t", "20", "stop"],
                env=server_env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=30,
                check=True,
                creationflags=HIDDEN,
            )
        if password_file.exists():
            password_file.unlink()


if __name__ == "__main__":
    raise SystemExit(main())
