"""Real loopback I/O through trusted fixtures; production's public-IP policy stays enabled."""

import asyncio
import ssl
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta

import dns.asyncresolver
import dns.message
import dns.rcode
import dns.rdatatype
import dns.rrset
import httpx
import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID

from app.tools.dns import ResolutionError, resolve_addresses
from app.tools.models import CheckStatus, WebsiteTarget
from app.tools.website import WebsiteChecker

PUBLIC_IP = "93.184.216.34"
TARGET = WebsiteTarget(id="demo", url="https://demo.example/health")


async def public_resolver(host, timeout):
    return [PUBLIC_IP]


@pytest.fixture
def certificate_factory(tmp_path):
    def create(*, days=90, hostname="demo.example", trust_ca=True):
        now = datetime.now(UTC)
        ca_key = ec.generate_private_key(ec.SECP256R1())
        ca_name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Disposable test CA")])
        ca = (
            x509.CertificateBuilder()
            .subject_name(ca_name)
            .issuer_name(ca_name)
            .public_key(ca_key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now - timedelta(days=10))
            .not_valid_after(now + timedelta(days=365))
            .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
            .add_extension(
                x509.KeyUsage(True, False, False, False, False, True, True, False, False),
                critical=True,
            )
            .sign(ca_key, hashes.SHA256())
        )
        key = ec.generate_private_key(ec.SECP256R1())
        certificate = (
            x509.CertificateBuilder()
            .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, hostname)]))
            .issuer_name(ca_name)
            .public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now - timedelta(days=5))
            .not_valid_after(now + timedelta(days=days))
            .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
            .add_extension(x509.SubjectAlternativeName([x509.DNSName(hostname)]), critical=False)
            .add_extension(
                x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_key.public_key()),
                critical=False,
            )
            .sign(ca_key, hashes.SHA256())
        )
        ca_path = tmp_path / "ca.pem"
        certificate_path = tmp_path / "certificate.pem"
        key_path = tmp_path / "key.pem"
        ca_path.write_bytes(ca.public_bytes(serialization.Encoding.PEM))
        certificate_path.write_bytes(certificate.public_bytes(serialization.Encoding.PEM))
        key_path.write_bytes(
            key.private_bytes(
                serialization.Encoding.PEM,
                serialization.PrivateFormat.PKCS8,
                serialization.NoEncryption(),
            )
        )
        server_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        server_context.load_cert_chain(certificate_path, key_path)
        client_context = ssl.create_default_context(cafile=str(ca_path) if trust_ca else None)
        return server_context, client_context

    return create


@asynccontextmanager
async def local_server(context=None, *, header_delay=0):
    requests = []
    sni_names = []
    tasks = set()
    if context is not None:
        context.set_servername_callback(lambda connection, name, context: sni_names.append(name))

    async def serve(reader, writer):
        tasks.add(asyncio.current_task())
        try:
            async with asyncio.timeout(2):
                line = await reader.readline()
                if not line:
                    return  # The certificate-only probe closes without sending HTTP.
                headers = []
                while header := await reader.readline():
                    if header == b"\r\n":
                        break
                    headers.append(header)
                requests.append((line, b"".join(headers)))
                await asyncio.sleep(header_delay)
                code = 500 if b"/fail " in line else 200
                writer.write(
                    (
                        f"HTTP/1.1 {code} Test\r\nContent-Length: 2\r\nConnection: close\r\n\r\nok"
                    ).encode()
                )
                await writer.drain()
        except (OSError, TimeoutError):
            pass
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except OSError:
                pass
            tasks.discard(asyncio.current_task())

    server = await asyncio.start_server(serve, "127.0.0.1", 0, ssl=context)
    port = server.sockets[0].getsockname()[1]
    try:
        yield port, requests, sni_names
    finally:
        server.close()
        await server.wait_closed()
        pending = list(tasks)
        for task in pending:
            task.cancel()
        await asyncio.gather(*pending, return_exceptions=True)


class LoopbackTransport(httpx.AsyncBaseTransport):
    """Only the test fixture maps a validated public address to its local server."""

    def __init__(self, port, context):
        self.port = port
        self.inner = httpx.AsyncHTTPTransport(verify=context, trust_env=False, retries=0)

    async def handle_async_request(self, request):
        assert request.url.host == PUBLIC_IP
        mapped = httpx.Request(
            request.method,
            request.url.copy_with(host="127.0.0.1", port=self.port),
            headers=request.headers,
            stream=request.stream,
            extensions=request.extensions,
        )
        return await self.inner.handle_async_request(mapped)

    async def aclose(self):
        await self.inner.aclose()


def test_real_http_headers_classify_healthy_and_failing_endpoint():
    async def scenario():
        async with local_server() as (port, requests, _):
            checker = WebsiteChecker(
                resolver=public_resolver,
                transport_factory=lambda: LoopbackTransport(port, ssl.create_default_context()),
            )
            healthy = await checker.check_http(
                WebsiteTarget(id="demo", url="http://demo.example/health")
            )
            failing = await checker.check_http(
                WebsiteTarget(id="demo", url="http://demo.example/fail")
            )
            assert healthy.status == CheckStatus.HEALTHY
            assert failing.status == CheckStatus.UNHEALTHY
            assert failing.evidence["http_status"] == 500
            assert len(requests) == 2
            assert all(b"Host: demo.example\r\n" in headers for _, headers in requests)

    asyncio.run(scenario())


def test_real_http_slow_headers_respect_deadline():
    async def scenario():
        async with local_server(header_delay=1) as (port, _, _):
            checker = WebsiteChecker(
                timeout=0.1,
                resolver=public_resolver,
                transport_factory=lambda: LoopbackTransport(port, ssl.create_default_context()),
            )
            result = await checker.check_http(
                WebsiteTarget(id="demo", url="http://demo.example/health")
            )
            assert result.status == CheckStatus.CHECK_FAILED
            assert result.evidence["reason"] == "check_timeout"

    asyncio.run(scenario())


def test_real_https_preserves_sni_while_connecting_to_a_pinned_ip(certificate_factory):
    server_context, client_context = certificate_factory()

    async def scenario():
        async with local_server(server_context) as (port, requests, sni_names):
            checker = WebsiteChecker(
                resolver=public_resolver,
                transport_factory=lambda: LoopbackTransport(port, client_context),
            )
            result = await checker.check_http(TARGET)
            assert result.status == CheckStatus.HEALTHY
            assert sni_names == ["demo.example"]
            assert b"Host: demo.example\r\n" in requests[0][1]

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "options,status",
    [
        ({"days": 90}, CheckStatus.HEALTHY),
        ({"days": 10}, CheckStatus.DEGRADED),
        ({"days": -1}, CheckStatus.UNHEALTHY),
        ({"hostname": "other.example"}, CheckStatus.UNHEALTHY),
        ({"trust_ca": False}, CheckStatus.UNHEALTHY),
    ],
)
def test_real_tls_certificate_verification(certificate_factory, options, status):
    server_context, client_context = certificate_factory(**options)

    async def scenario():
        async with local_server(server_context) as (port, _, sni_names):

            async def connector(host, requested_port, **kwargs):
                assert host == PUBLIC_IP
                assert requested_port == 443
                return await asyncio.open_connection("127.0.0.1", port, **kwargs)

            checker = WebsiteChecker(
                resolver=public_resolver, connector=connector, ssl_context=client_context
            )
            result = await checker.check_ssl(TARGET)
            assert result.status == status
            assert sni_names == ["demo.example"]
            if status == CheckStatus.UNHEALTHY:
                assert result.evidence["reason"] == "certificate_verification_failed"
                assert isinstance(result.evidence["verify_code"], int)
                assert "days_remaining" not in result.evidence
            else:
                assert result.evidence["days_remaining"] > 0
                assert result.evidence["tls_version"].startswith("TLS")

    asyncio.run(scenario())


class LocalDnsServer(asyncio.DatagramProtocol):
    def connection_made(self, transport):
        self.transport = transport

    def datagram_received(self, data, address):
        query = dns.message.from_wire(data)
        response = dns.message.make_response(query)
        question = query.question[0]
        hostname = question.name.to_text()
        if hostname == "missing.example.":
            response.set_rcode(dns.rcode.NXDOMAIN)
        elif hostname == "demo.example.":
            ip = PUBLIC_IP if question.rdtype == dns.rdatatype.A else "2606:4700:4700::1111"
            response.answer.append(
                dns.rrset.from_text(question.name, 60, "IN", question.rdtype, ip)
            )
        elif hostname == "timeout.example.":
            return
        self.transport.sendto(response.to_wire(), address)


@pytest.mark.parametrize(
    "host,reason",
    [
        ("demo.example", None),
        ("missing.example", "dns_nxdomain"),
        ("empty.example", "dns_no_address_records"),
        ("timeout.example", "dns_timeout"),
    ],
)
def test_real_dns_adapter_with_local_udp_resolver(monkeypatch, host, reason):
    async def scenario():
        loop = asyncio.get_running_loop()
        transport, _ = await loop.create_datagram_endpoint(
            LocalDnsServer, local_addr=("127.0.0.1", 0)
        )
        resolver = dns.asyncresolver.Resolver(configure=False)
        resolver.nameservers = ["127.0.0.1"]
        resolver.port = transport.get_extra_info("sockname")[1]
        monkeypatch.setattr(dns.asyncresolver, "Resolver", lambda **kwargs: resolver)
        try:
            if reason is None:
                addresses = await resolve_addresses(host, 0.5)
                assert set(addresses) == {PUBLIC_IP, "2606:4700:4700::1111"}
            else:
                with pytest.raises(ResolutionError) as error:
                    await resolve_addresses(host, 0.1)
                assert error.value.code == reason
                assert error.value.confirmed is (reason != "dns_timeout")
        finally:
            transport.close()
            await asyncio.sleep(0)

    asyncio.run(scenario())
