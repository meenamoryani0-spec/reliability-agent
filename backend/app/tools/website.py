import asyncio
import ssl
import time
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from functools import partial

import httpx

from app.tools.dns import ResolutionError, resolve_addresses
from app.tools.models import CheckResult, CheckStatus, CheckType, WebsiteTarget
from app.tools.targets import PinnedTransport, TargetError, parse_url, validate_addresses

Resolver = Callable[[str, float], Awaitable[list[str]]]
Connector = Callable[..., Awaitable[tuple[asyncio.StreamReader, asyncio.StreamWriter]]]


class WebsiteChecker:
    """Probe registered public targets; injectable I/O is for trusted test code only."""

    def __init__(
        self,
        *,
        timeout: float = 10,
        resolver: Resolver | None = None,
        nameservers: tuple[str, ...] = (),
        transport_factory: Callable[[], httpx.AsyncBaseTransport] | None = None,
        connector: Connector = asyncio.open_connection,
        ssl_context: ssl.SSLContext | None = None,
    ):
        self._timeout = timeout
        self._resolver = resolver or partial(resolve_addresses, nameservers=nameservers)
        self._context = ssl_context or ssl.create_default_context()
        self._transport_factory = transport_factory or (
            lambda: httpx.AsyncHTTPTransport(verify=self._context, trust_env=False, retries=0)
        )
        self._connector = connector

    async def _addresses(self, host: str) -> list[str]:
        return validate_addresses(await self._resolver(host, self._timeout))

    @staticmethod
    def _failure(target: WebsiteTarget, kind: CheckType, error: Exception) -> CheckResult:
        confirmed = isinstance(error, ResolutionError) and error.confirmed
        code = error.code if isinstance(error, (TargetError, ResolutionError)) else "check_timeout"
        return CheckResult(
            component=target.id,
            check_type=kind,
            status=CheckStatus.UNHEALTHY if confirmed else CheckStatus.CHECK_FAILED,
            severity="high" if confirmed else "none",
            summary="DNS returned no usable address"
            if confirmed
            else "Website check could not complete",
            evidence={"reason": code},
        )

    async def check_dns(self, target: WebsiteTarget) -> CheckResult:
        try:
            async with asyncio.timeout(self._timeout):
                url = parse_url(target.url)
                addresses = await self._addresses(url.host)
                return CheckResult(
                    component=target.id,
                    check_type=CheckType.DNS,
                    status=CheckStatus.HEALTHY,
                    summary="Hostname resolves to public addresses",
                    evidence={"hostname": url.host, "addresses": addresses},
                )
        except (TargetError, ResolutionError, TimeoutError) as error:
            return self._failure(target, CheckType.DNS, error)

    async def check_http(self, target: WebsiteTarget) -> CheckResult:
        start = time.perf_counter()
        try:
            async with asyncio.timeout(self._timeout):
                original = parse_url(target.url)
                url = original
                visited = set()
                statuses = []
                addresses = await self._addresses(url.host)
                for hop in range(4):
                    if str(url) in visited:
                        raise TargetError("redirect_loop")
                    visited.add(str(url))
                    transport = PinnedTransport(addresses[0], self._transport_factory())
                    async with httpx.AsyncClient(
                        transport=transport,
                        trust_env=False,
                        follow_redirects=False,
                        timeout=self._timeout,
                    ) as client:
                        # Only headers are needed; do not read or retain the site's body.
                        async with client.stream("GET", url) as response:
                            code = response.status_code
                            location = response.headers.get("location")
                    statuses.append(code)
                    if code in {301, 302, 303, 307, 308}:
                        if not location or len(location) > 2048:
                            raise TargetError("invalid_redirect")
                        if hop == 3:
                            raise TargetError("redirect_limit_exceeded")
                        try:
                            redirected = parse_url(str(url.join(location)))
                        except (httpx.InvalidURL, ValueError):
                            raise TargetError("invalid_redirect") from None
                        if redirected.host != original.host:
                            raise TargetError("cross_host_redirect_not_allowed")
                        if url.scheme == "https" and redirected.scheme != "https":
                            raise TargetError("https_downgrade_not_allowed")
                        url = redirected
                        continue
                    elapsed = round((time.perf_counter() - start) * 1000, 2)
                    if code in target.expected_statuses:
                        slow = elapsed > target.latency_warning_ms
                        status = CheckStatus.DEGRADED if slow else CheckStatus.HEALTHY
                        severity = "low" if slow else "none"
                        summary = (
                            "Endpoint responded slowly"
                            if slow
                            else "Endpoint returned an expected HTTP status"
                        )
                    elif code in {401, 403}:
                        status, severity = CheckStatus.CHECK_FAILED, "none"
                        summary = "Endpoint denied the unauthenticated probe"
                    elif code == 429:
                        status, severity = CheckStatus.DEGRADED, "medium"
                        summary = "Endpoint rate-limited the probe"
                    else:
                        status, severity = (
                            CheckStatus.UNHEALTHY,
                            "high" if code >= 500 else "medium",
                        )
                        summary = "Endpoint returned an unexpected HTTP status"
                    return CheckResult(
                        component=target.id,
                        check_type=CheckType.HTTP,
                        status=status,
                        severity=severity,
                        summary=summary,
                        latency_ms=elapsed,
                        evidence={
                            "hostname": url.host,
                            "http_status": code,
                            "redirect_count": hop,
                            "status_chain": statuses,
                            "probed_ip": addresses[0],
                            "expected_statuses": list(target.expected_statuses),
                        },
                    )
        except (TargetError, ResolutionError, TimeoutError, httpx.TimeoutException) as error:
            return self._failure(target, CheckType.HTTP, error)
        except httpx.RequestError:
            return CheckResult(
                component=target.id,
                check_type=CheckType.HTTP,
                status=CheckStatus.CHECK_FAILED,
                summary="HTTP probe could not connect or read response headers",
                evidence={"reason": "http_transport_failed"},
            )

    async def check_ssl(self, target: WebsiteTarget) -> CheckResult:
        url = parse_url(target.url)
        if url.scheme != "https":
            return CheckResult(
                component=target.id,
                check_type=CheckType.SSL,
                status=CheckStatus.UNKNOWN,
                summary="TLS is not configured for this HTTP target",
                evidence={"reason": "http_target"},
            )
        writer = None
        try:
            async with asyncio.timeout(self._timeout):
                addresses = await self._addresses(url.host)
                _, writer = await self._connector(
                    addresses[0],
                    443,
                    ssl=self._context,
                    server_hostname=url.host,
                    ssl_handshake_timeout=self._timeout,
                )
                connection = writer.get_extra_info("ssl_object")
                certificate = connection.getpeercert() if connection else None
                if not certificate or "notAfter" not in certificate:
                    raise TargetError("certificate_details_unavailable")
                expires_at = datetime.fromtimestamp(
                    ssl.cert_time_to_seconds(certificate["notAfter"]), UTC
                )
                days = (expires_at - datetime.now(UTC)).total_seconds() / 86400
                status = (
                    CheckStatus.UNHEALTHY
                    if days <= 0
                    else CheckStatus.DEGRADED
                    if days <= 30
                    else CheckStatus.HEALTHY
                )
                return CheckResult(
                    component=target.id,
                    check_type=CheckType.SSL,
                    status=status,
                    severity="high" if days <= 0 else "medium" if days <= 30 else "none",
                    summary="TLS certificate expired"
                    if days <= 0
                    else "TLS certificate expires soon"
                    if days <= 30
                    else "TLS certificate is valid",
                    evidence={
                        "hostname": url.host,
                        "probed_ip": addresses[0],
                        "expires_at": expires_at.isoformat(),
                        "days_remaining": round(days, 1),
                        "tls_version": connection.version(),
                    },
                )
        except ssl.SSLCertVerificationError as error:
            return CheckResult(
                component=target.id,
                check_type=CheckType.SSL,
                status=CheckStatus.UNHEALTHY,
                severity="high",
                summary="TLS certificate verification failed",
                evidence={
                    "reason": "certificate_verification_failed",
                    "verify_code": error.verify_code,
                },
            )
        except (TargetError, ResolutionError, TimeoutError) as error:
            return self._failure(target, CheckType.SSL, error)
        except (ssl.SSLError, OSError):
            return CheckResult(
                component=target.id,
                check_type=CheckType.SSL,
                status=CheckStatus.CHECK_FAILED,
                summary="TLS handshake could not complete",
                evidence={"reason": "tls_connection_failed"},
            )
        finally:
            if writer is not None:
                writer.close()
                try:
                    async with asyncio.timeout(1):
                        await writer.wait_closed()
                except (OSError, TimeoutError):
                    pass
