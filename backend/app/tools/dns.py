import socket

import dns.asyncresolver
import dns.exception
import dns.resolver


class ResolutionError(Exception):
    def __init__(self, code: str, *, confirmed: bool = False):
        self.code = code
        self.confirmed = confirmed
        super().__init__(code)


async def resolve_addresses(
    host: str, timeout: float, *, nameservers: tuple[str, ...] = ()
) -> list[str]:
    try:
        resolver = dns.asyncresolver.Resolver(configure=not bool(nameservers))
        if nameservers:
            resolver.nameservers = list(nameservers)
        if not resolver.nameservers:
            raise ResolutionError("dns_resolver_not_configured")
        answers = await resolver.resolve_name(
            host, family=socket.AF_UNSPEC, lifetime=timeout, search=False
        )
        return list(answers.addresses())
    except dns.resolver.NXDOMAIN:
        raise ResolutionError("dns_nxdomain", confirmed=True) from None
    except dns.resolver.NoAnswer:
        raise ResolutionError("dns_no_address_records", confirmed=True) from None
    except dns.exception.Timeout:
        raise ResolutionError("dns_timeout") from None
    except (dns.exception.DNSException, OSError):
        raise ResolutionError("dns_resolver_failed") from None
