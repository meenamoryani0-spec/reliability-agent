"""Disposable loopback TLS infrastructure for the production-mode HTTP smoke."""

import http.client
import ipaddress
import json
import socket
import ssl
import subprocess
import sys
import threading
import time
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import httpx
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID
from smoke_support import HIDDEN, ROOT


def certificate(directory):
    now = datetime.now(UTC)
    authority = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Disposable Phase 14 CA")])
    ca = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(authority.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=5))
        .not_valid_after(now + timedelta(days=1))
        .add_extension(x509.BasicConstraints(ca=True, path_length=0), True)
        .sign(authority, hashes.SHA256())
    )
    key = ec.generate_private_key(ec.SECP256R1())
    leaf = (
        x509.CertificateBuilder()
        .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "127.0.0.1")]))
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=5))
        .not_valid_after(now + timedelta(days=1))
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), True)
        .add_extension(
            x509.SubjectAlternativeName(
                [x509.IPAddress(ipaddress.ip_address("127.0.0.1")), x509.DNSName("localhost")]
            ),
            False,
        )
        .sign(authority, hashes.SHA256())
    )
    paths = {part: directory / f"{part}.pem" for part in ("ca", "certificate", "key")}
    paths["ca"].write_bytes(ca.public_bytes(serialization.Encoding.PEM))
    paths["certificate"].write_bytes(leaf.public_bytes(serialization.Encoding.PEM))
    paths["key"].write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    paths["key"].chmod(0o600)
    return paths


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def stop(process):
    process.terminate()
    try:
        process.wait(timeout=15)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


@contextmanager
def production_backend(environment, paths, context):
    port = free_port()
    environment = {**environment, "API_ALLOWED_HOSTS": json.dumps([f"127.0.0.1:{port}"])}
    with (ROOT / "work/logs/phase-14-tls-backend.log").open("w", encoding="utf-8") as output:
        process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "app.main:app",
                "--host",
                "127.0.0.1",
                "--port",
                str(port),
                "--ssl-keyfile",
                str(paths["key"]),
                "--ssl-certfile",
                str(paths["certificate"]),
                "--no-access-log",
                "--no-proxy-headers",
            ],
            cwd=ROOT / "backend",
            env=environment,
            stdout=output,
            stderr=subprocess.STDOUT,
            creationflags=HIDDEN,
        )
        try:
            with httpx.Client(
                base_url=f"https://127.0.0.1:{port}", verify=context, trust_env=False, timeout=10
            ) as client:
                deadline = time.monotonic() + 40
                while True:
                    if process.poll() is not None:
                        raise RuntimeError("Production-mode backend exited; inspect its local log")
                    try:
                        client.get("/health", timeout=1).raise_for_status()
                        break
                    except httpx.TransportError:
                        if time.monotonic() > deadline:
                            raise RuntimeError(
                                "Production-mode backend startup timed out"
                            ) from None
                        time.sleep(0.1)
                yield client
        finally:
            stop(process)


@contextmanager
def tls_frontend_proxy(upstream_port, paths):
    # This proxy is a test harness, never a deployment server. Its single fixed
    # destination is the test Next.js listener, not an arbitrary URL proxy.
    class Handler(BaseHTTPRequestHandler):
        def forward(self):
            size = int(self.headers.get("Content-Length", "0"))
            if not 0 <= size <= 8192:
                self.send_error(413)
                return
            body = self.rfile.read(size) if size else None
            connection = http.client.HTTPConnection("127.0.0.1", upstream_port, timeout=15)
            try:
                headers = {
                    key: value
                    for key, value in self.headers.items()
                    if key.lower() not in {"connection", "transfer-encoding"}
                }
                connection.request(self.command, self.path, body=body, headers=headers)
                response = connection.getresponse()
                data = response.read(2_097_153)
                if len(data) > 2_097_152:
                    raise RuntimeError("Test proxy response limit")
                self.send_response(response.status)
                for key, value in response.getheaders():
                    if key.lower() not in {"connection", "transfer-encoding", "content-length"}:
                        self.send_header(key, value)
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
            finally:
                connection.close()

        do_GET = do_POST = do_DELETE = forward

        def log_message(self, *_):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    tls = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    tls.load_cert_chain(paths["certificate"], paths["key"])
    server.socket = tls.wrap_socket(server.socket, server_side=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"https://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
