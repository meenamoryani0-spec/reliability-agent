# Phase 3 — website checks

Verified on 10 October 2026. All new source, dependencies, certificates, caches,
temporary files, and logs were written to D:.

## Implemented

- HTTP health/endpoint checks, configurable expected success codes, and latency.
- DNS A/AAAA checks with separate confirmed failures and resolver/check failures.
- TLS chain/hostname verification, expiry warning, and negotiated version.
- Normalized statuses and safe evidence; no response bodies or raw exception messages.
- Operator-registered target IDs with public-address validation and IP pinning.
- Bounded same-host redirects, no HTTPS downgrade, total deadlines, no retries.
- `GET /services/websites` and `POST /checks/websites/{target_id}?kind=http|dns|ssl`.
- Optional application DNS override and `scripts/website-smoke.ps1`.

Implementation is under `backend/app/tools/`, with routes in
`backend/app/api/checks.py`. Tests are in `backend/tests/test_website.py` and
`backend/tests/test_website_live.py`. Setup remains `scripts/setup.ps1`;
dnspython is a runtime dependency and cryptography is a development dependency
used to generate disposable test certificates.

## Validation

Commands from the repository root:

```powershell
.\scripts\test.ps1
.\scripts\smoke.ps1
```

Final results: **138 tests passed**, Ruff lint passed, formatting passed, and
the live Uvicorn smoke test passed. This includes 84 new website tests, with
12 tests using real local HTTP/TLS/UDP DNS sockets. Tests also use mocked failure responses.
Coverage includes HTTP 200/500, delayed response headers, original Host/SNI
preservation after IP pinning, valid/expiring/expired certificates, wrong
hostnames, untrusted CAs, NXDOMAIN, empty answers, DNS timeouts, private/mixed
DNS destinations, redirect limits, blocked redirects, and normalized API results.

The Uvicorn smoke test starts a real backend process, checks health/docs/OpenAPI,
the empty registry, 404 for an unconfigured target, and 422 for an unsupported
check type, then stops the process.

## Public smoke evidence

The checker was run against `https://example.com/` using the operator registry
in temporary process environment variables; the repository's real `.env` was
not changed. No API key was used.

```powershell
$env:WEBSITE_TARGETS = '[{"id":"example","url":"https://example.com/"}]'
$env:WEBSITE_DNS_NAMESERVERS = '["1.1.1.1"]'
.\scripts\website-smoke.ps1 -TargetId example
```

Observed at approximately 15:58 UTC on 10 October 2026:

| Check | Observed result |
| --- | --- |
| DNS | HEALTHY; public A and AAAA addresses returned |
| HTTP | HEALTHY; HTTP 200; measured latency 225.05 ms |
| TLS | HEALTHY; TLSv1.3; certificate expiry 25 December 2026 at 22:56:35 UTC |
| Command | PASS; exit code 0 |

These are single observations. They are not claims of continued availability.
An earlier run with the default resolver failed because dnspython found zero
OS nameservers in the execution sandbox. An intermediate override run had a
DNS timeout on the TLS probe. Both were reported as CHECK_FAILED, without
claiming a site outage. The final single-resolver smoke run passed all checks.

## Limits and next phase

No real customer website is configured. Only one selected address per HTTP/TLS
check is probed. These checks cannot prove that forms, booking, or other business
flows work. Authenticated endpoints, cross-host redirects, query-string targets,
nonstandard ports, and private-network websites are deliberately outside this
phase. Scheduling, persistence, deployment authentication, and incident diagnosis
remain future work. Real Nebius connectivity is still unverified.

Next: Phase 4, Playwright navigation, console errors, and one healthy/one
intentionally failing business flow, verified locally without API credentials.

## Official documentation checked

- [HTTPX transports](https://www.python-httpx.org/advanced/transports/)
- [HTTPX SNI extension](https://www.python-httpx.org/advanced/extensions/)
- [HTTPX timeout behavior](https://www.python-httpx.org/advanced/timeouts/)
- [Python 3.12 SSL](https://docs.python.org/3.12/library/ssl.html)
- [Python asyncio streams](https://docs.python.org/3.12/library/asyncio-stream.html)
- [dnspython asynchronous resolver](https://dnspython.readthedocs.io/en/stable/async-resolver-class.html)
- [dnspython OS configuration and nameservers](https://dnspython.readthedocs.io/en/stable/resolver-class.html)
- [cryptography disposable certificate construction](https://cryptography.io/en/stable/x509/tutorial/)
