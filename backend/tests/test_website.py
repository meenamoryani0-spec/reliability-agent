import asyncio
import json
import ssl

import dns.asyncresolver
import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.config import Settings
from app.main import create_app
from app.tools.dns import ResolutionError, resolve_addresses
from app.tools.models import CheckStatus, WebsiteTarget
from app.tools.targets import TargetError, validate_addresses
from app.tools.website import WebsiteChecker

PUBLIC_IP = "93.184.216.34"
TARGET = WebsiteTarget(id="demo", url="https://demo.example/health")


async def public_resolver(host, timeout):
    return [PUBLIC_IP]


def checker_with_handler(handler, **kwargs):
    return WebsiteChecker(
        resolver=public_resolver,
        transport_factory=lambda: httpx.MockTransport(handler),
        **kwargs,
    )


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "ftp://demo.example",
        "https://user:sentinel-password@demo.example",
        "https://demo.example?token=sentinel-secret",
        "https://demo.example/#sentinel-secret",
        "https://127.0.0.1",
        "https://[::1]",
        "https://localhost",
        "https://app.local",
        "https://app.internal",
        "https://app.home.arpa",
        "https://demo.example:8000",
        "https://demo.example:80",
        "https://demo.example:invalid",
    ],
)
def test_unsafe_target_configuration_is_rejected_without_echoing_secrets(url):
    with pytest.raises(ValidationError) as error:
        WebsiteTarget(id="demo", url=url)
    assert "sentinel" not in str(error.value)


@pytest.mark.parametrize(
    "address",
    [
        "127.0.0.1",
        "10.0.0.1",
        "172.16.0.1",
        "192.168.1.1",
        "169.254.169.254",
        "100.64.0.1",
        "0.0.0.0",
        "224.0.0.1",
        "192.0.2.1",
        "::1",
        "fc00::1",
        "fe80::1",
        "ff02::1",
        "::ffff:127.0.0.1",
        "64:ff9b::7f00:1",
        "2002:7f00:1::",
        "2001::1",
        "2001:db8::1",
    ],
)
def test_one_unsafe_dns_answer_rejects_the_entire_destination(address):
    with pytest.raises(TargetError, match="non_public_destination"):
        validate_addresses([PUBLIC_IP, address])


@pytest.mark.parametrize("addresses", [[], ["not-an-address"], [PUBLIC_IP] * 33])
def test_invalid_dns_answer_sets_are_rejected(addresses):
    with pytest.raises(TargetError, match="invalid_dns_addresses"):
        validate_addresses(addresses)


@pytest.mark.parametrize(
    "code,status,healthy",
    [
        (200, CheckStatus.HEALTHY, True),
        (404, CheckStatus.UNHEALTHY, False),
        (500, CheckStatus.UNHEALTHY, False),
        (401, CheckStatus.CHECK_FAILED, None),
        (403, CheckStatus.CHECK_FAILED, None),
        (429, CheckStatus.DEGRADED, None),
    ],
)
def test_http_classification_and_normalized_evidence(code, status, healthy):
    checker = checker_with_handler(lambda request: httpx.Response(code))
    result = asyncio.run(checker.check_http(TARGET))
    assert result.status == status
    assert result.healthy is healthy
    assert result.evidence["http_status"] == code
    assert result.evidence["probed_ip"] == PUBLIC_IP
    assert result.latency_ms >= 0
    assert result.checked_at.tzinfo is not None


def test_custom_expected_status_and_latency_warning():
    async def handler(request):
        await asyncio.sleep(0.02)
        return httpx.Response(204)

    target = WebsiteTarget(
        id="demo", url=TARGET.url, expected_statuses=(204,), latency_warning_ms=1
    )
    result = asyncio.run(checker_with_handler(handler).check_http(target))
    assert result.status == CheckStatus.DEGRADED
    assert result.latency_ms > target.latency_warning_ms
    assert result.evidence["expected_statuses"] == [204]


def test_same_host_redirects_pin_dns_once_preserve_host_and_sni():
    resolutions = []
    requests = []

    async def resolver(host, timeout):
        resolutions.append(host)
        return [PUBLIC_IP] if len(resolutions) == 1 else ["127.0.0.1"]

    def handler(request):
        requests.append(request)
        if request.url.path == "/health":
            return httpx.Response(302, headers={"location": "/ready"})
        return httpx.Response(200)

    checker = WebsiteChecker(
        resolver=resolver, transport_factory=lambda: httpx.MockTransport(handler)
    )
    result = asyncio.run(checker.check_http(TARGET))
    assert result.status == CheckStatus.HEALTHY
    assert resolutions == ["demo.example"]
    assert result.evidence["status_chain"] == [302, 200]
    assert result.evidence["redirect_count"] == 1
    assert len(requests) == 2
    for request in requests:
        assert request.url.host == PUBLIC_IP
        assert request.headers["host"] == "demo.example"
        assert request.extensions["sni_hostname"] == "demo.example"


@pytest.mark.parametrize(
    "location,reason",
    [
        ("https://other.example/", "cross_host_redirect_not_allowed"),
        ("http://demo.example/", "https_downgrade_not_allowed"),
        ("http://169.254.169.254/", "invalid_redirect"),
        # HTTPX rejects this Location while preparing its unused next request.
        ("https://demo.example:invalid/", "http_transport_failed"),
        ("/health", "redirect_loop"),
        (None, "invalid_redirect"),
    ],
)
def test_redirect_policy_failures_are_not_claimed_as_site_outages(location, reason):
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(302, headers={"location": location} if location else {})

    result = asyncio.run(checker_with_handler(handler).check_http(TARGET))
    assert result.status == CheckStatus.CHECK_FAILED
    assert result.evidence["reason"] == reason
    assert len(requests) == 1


def test_redirect_limit_is_bounded():
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(302, headers={"location": f"/hop-{len(requests)}"})

    result = asyncio.run(checker_with_handler(handler).check_http(TARGET))
    assert result.evidence["reason"] == "redirect_limit_exceeded"
    assert len(requests) == 4


class UnreadBody(httpx.AsyncByteStream):
    async def __aiter__(self):
        raise AssertionError("Health probes must not read response bodies")
        yield b""  # pragma: no cover


def test_http_probe_never_reads_site_body():
    checker = checker_with_handler(lambda request: httpx.Response(200, stream=UnreadBody()))
    assert asyncio.run(checker.check_http(TARGET)).status == CheckStatus.HEALTHY


@pytest.mark.parametrize("kind", ["http", "dns", "ssl"])
@pytest.mark.parametrize("confirmed", [False, True])
def test_dns_failures_keep_confirmed_outages_separate_from_check_failures(kind, confirmed):
    async def resolver(host, timeout):
        raise ResolutionError("dns_nxdomain" if confirmed else "dns_timeout", confirmed=confirmed)

    checker = WebsiteChecker(resolver=resolver)
    result = asyncio.run(getattr(checker, f"check_{kind}")(TARGET))
    assert result.status == (CheckStatus.UNHEALTHY if confirmed else CheckStatus.CHECK_FAILED)
    assert result.healthy is (False if confirmed else None)


@pytest.mark.parametrize("kind", ["http", "dns", "ssl"])
def test_unsafe_dns_stops_all_network_probes(kind):
    calls = []

    async def resolver(host, timeout):
        return [PUBLIC_IP, "127.0.0.1"]

    def forbidden_io(*args, **kwargs):
        calls.append(True)
        raise AssertionError("Private destination must never be probed")

    checker = WebsiteChecker(
        resolver=resolver, transport_factory=forbidden_io, connector=forbidden_io
    )
    result = asyncio.run(getattr(checker, f"check_{kind}")(TARGET))
    assert result.status == CheckStatus.CHECK_FAILED
    assert result.evidence["reason"] == "non_public_destination"
    assert not calls


@pytest.mark.parametrize("kind", ["http", "dns", "ssl"])
def test_total_deadline_includes_dns(kind):
    async def resolver(host, timeout):
        await asyncio.sleep(5)

    checker = WebsiteChecker(timeout=0.01, resolver=resolver)
    result = asyncio.run(getattr(checker, f"check_{kind}")(TARGET))
    assert result.status == CheckStatus.CHECK_FAILED
    assert result.evidence["reason"] == "check_timeout"


def test_http_transport_errors_are_sanitized():
    def handler(request):
        raise httpx.ConnectError("sentinel-private-server-message")

    result = asyncio.run(checker_with_handler(handler).check_http(TARGET))
    assert result.status == CheckStatus.CHECK_FAILED
    assert "sentinel" not in result.model_dump_json()


def test_plain_http_has_no_tls_result():
    target = WebsiteTarget(id="demo", url="http://demo.example")
    result = asyncio.run(WebsiteChecker().check_ssl(target))
    assert result.status == CheckStatus.UNKNOWN
    assert result.healthy is None


def test_tls_transport_errors_are_sanitized():
    async def connector(*args, **kwargs):
        raise ssl.SSLError("sentinel-private-server-message")

    result = asyncio.run(
        WebsiteChecker(resolver=public_resolver, connector=connector).check_ssl(TARGET)
    )
    assert result.status == CheckStatus.CHECK_FAILED
    assert "sentinel" not in result.model_dump_json()


def test_settings_load_registered_targets_from_json_and_reject_duplicate_ids(monkeypatch):
    monkeypatch.setenv("WEBSITE_TARGETS", json.dumps([{"id": "demo", "url": TARGET.url}]))
    settings = Settings(_env_file=None)
    assert settings.website_targets == [TARGET]
    with pytest.raises(ValidationError, match="must be unique"):
        Settings(_env_file=None, website_targets=[TARGET, TARGET])


def test_missing_os_resolver_is_reported_as_a_configuration_failure(monkeypatch):
    resolver = dns.asyncresolver.Resolver(configure=False)
    monkeypatch.setattr(dns.asyncresolver, "Resolver", lambda **kwargs: resolver)
    with pytest.raises(ResolutionError, match="dns_resolver_not_configured") as error:
        asyncio.run(resolve_addresses("demo.example", 1))
    assert error.value.confirmed is False


def test_dns_override_is_validated_and_does_not_change_the_system_resolver(monkeypatch):
    settings = Settings(_env_file=None, website_dns_nameservers=("1.1.1.1",))
    assert settings.website_dns_nameservers == ("1.1.1.1",)
    with pytest.raises(ValidationError):
        Settings(_env_file=None, website_dns_nameservers=("https://dns.example/query",))
    with pytest.raises(ValidationError):
        Settings(_env_file=None, website_dns_nameservers=("127.0.0.1",))
    created_with = []
    resolver = dns.asyncresolver.Resolver(configure=False)

    async def resolve_name(host, **kwargs):
        assert resolver.nameservers == ["1.1.1.1"]
        raise dns.resolver.NXDOMAIN()

    resolver.resolve_name = resolve_name

    def factory(**kwargs):
        created_with.append(kwargs)
        return resolver

    monkeypatch.setattr(dns.asyncresolver, "Resolver", factory)
    with pytest.raises(ResolutionError):
        asyncio.run(
            resolve_addresses("demo.example", 1, nameservers=settings.website_dns_nameservers)
        )
    assert created_with == [{"configure": False}]


@pytest.mark.parametrize("kind", ["http", "dns", "ssl"])
def test_api_checks_only_registered_targets_and_returns_normalized_result(kind):
    checker = checker_with_handler(lambda request: httpx.Response(200))
    settings = Settings(_env_file=None, environment="test", website_targets=[TARGET])
    with TestClient(create_app(settings, website_checker=checker)) as client:
        assert client.get("/services/websites").json() == [{"id": "demo", "url": TARGET.url}]
        # Use the DNS path for a real normalized result on all three dispatched methods.
        setattr(checker, f"check_{kind}", checker.check_dns)
        response = client.post(f"/checks/websites/demo?kind={kind}")
        assert response.status_code == 200
        body = response.json()
        assert body["component"] == "demo"
        assert body["status"] == "HEALTHY"
        assert body["healthy"] is True
        assert body["check_type"] == "dns"
        assert client.post(f"/checks/websites/unregistered?kind={kind}").status_code == 404
        assert client.post("/checks/websites/demo?kind=shell").status_code == 422
        assert client.get("/checks/websites/demo").status_code == 405
