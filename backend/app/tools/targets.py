import ipaddress
import re

import httpx

HOST_PATTERN = re.compile(r"^(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z0-9-]{2,63}$")


class TargetError(ValueError):
    """Safe validation category, without raw URL or DNS payloads."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(f"Website target rejected ({code})")


def parse_url(value: str) -> httpx.URL:
    try:
        url = httpx.URL(value)
    except (httpx.InvalidURL, ValueError):
        raise TargetError("invalid_url") from None
    if url.scheme not in {"http", "https"} or not url.host:
        raise TargetError("invalid_url")
    if url.userinfo or url.query or url.fragment:
        raise TargetError("credentials_query_or_fragment_not_allowed")
    if url.port not in {None, 80 if url.scheme == "http" else 443}:
        raise TargetError("port_not_allowed")
    if url.host.endswith((".localhost", ".local", ".internal", ".lan", ".home.arpa")):
        raise TargetError("hostname_not_allowed")
    if len(url.host) > 253 or not HOST_PATTERN.fullmatch(url.host):
        raise TargetError("hostname_not_allowed")
    try:
        ipaddress.ip_address(url.host)
    except ValueError:
        return url
    raise TargetError("literal_ip_not_allowed")


def validate_addresses(addresses: list[str]) -> list[str]:
    if not addresses or len(addresses) > 32:
        raise TargetError("invalid_dns_addresses")
    parsed = []
    for address in addresses:
        try:
            ip = ipaddress.ip_address(address)
        except ValueError:
            raise TargetError("invalid_dns_addresses") from None
        # Reject mapped/transition IPv6, private, local, multicast and reserved destinations.
        if (
            not ip.is_global
            or ip.is_multicast
            or (
                isinstance(ip, ipaddress.IPv6Address)
                and (
                    ip not in ipaddress.ip_network("2000::/3")
                    or ip.ipv4_mapped
                    or ip.sixtofour
                    or ip.teredo
                )
            )
        ):
            raise TargetError("non_public_destination")
        parsed.append(ip)
    return [str(ip) for ip in sorted(set(parsed), key=lambda ip: (ip.version, int(ip)))]


class PinnedTransport(httpx.AsyncBaseTransport):
    """Connect to a validated numeric IP while preserving Host and TLS SNI."""

    def __init__(self, ip: str, inner: httpx.AsyncBaseTransport):
        self._ip = ip
        self._inner = inner

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        pinned = httpx.Request(
            request.method,
            request.url.copy_with(host=self._ip),
            headers=request.headers,
            stream=request.stream,
            extensions={**request.extensions, "sni_hostname": request.url.host},
        )
        return await self._inner.handle_async_request(pinned)

    async def aclose(self) -> None:
        await self._inner.aclose()
