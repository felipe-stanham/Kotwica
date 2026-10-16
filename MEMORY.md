# Memory Index

Persistent learnings for Kotwica. One line per entry; detail files go in `memory/`.

## Index

- **[2026-10-15] godaddy-pat-scope:** GoDaddy PAT minimum scope for GET+PUT on one A record is still open. A token with every DNS scope works (the `[int]` roundtrip passed). A token with only `domains.dns:update` returns HTTP 401 on the GET, so it cannot read. Not yet tested: `domains.dns:update` plus `domains.domain:read`. Scopes are chosen in the GoDaddy PAT page when generating the token.
- **[2026-10-15] int-roundtrip-needs-reset:** `test_int_dev_record_roundtrip` passes even when no PUT happens. To prove a token can PUT, first reset `kotwica-dev` at GoDaddy to A `192.0.2.1`, TTL 3600, then run `.venv/bin/python -m pytest -m integration`.
- **[2026-10-15] test-app-process-sigterm-flaky:** `tests/test_app_process.py::test_token_never_logged_at_debug` fails with a 5 s timeout on terminate, also on a clean `dev`. FIXED by T-0003: asyncio.to_thread workers (DNS/TLS timeouts up to 10 s) were joined by asyncio.run and interpreter exit; main() now runs Server.serve() on a plain loop and os._exit(0) after graceful shutdown.
- **[2026-10-16] caddy-no-cert-alert:** Caddy on 127.0.0.1:443 with an SNI it has no certificate for (home-tst.stanham.com) aborts the handshake with `TLSV1_ALERT_INTERNAL_ERROR`; Kotwica classifies it `invalid` with that reason and does not crash (real check from the Pi, tst).
- **[2026-10-16] tst-first-deploy:** Kotwica on Latarnia tst runs on port 8100, unit `latarnia-tst-kotwica.service`. First deploy needs `sudo systemctl restart latarnia-tst.service` so discovery registers it; the platform venv only needed `dnspython` added. Public IP seen from the Pi differs from the Mac's (Mac: dev only).
- **[2026-10-16] prd-first-deploy:** Kotwica prd runs on port 8150, unit `latarnia-prd-kotwica.service`, deployed from `main` e22323a on the Pi only (never on Hetzner: it would write its own IP into `home`). Before the first run `home` was a stale hand-set A (104.28.59.166, TTL 3600) and public HTTPS timed out; the router DDNS name stanham.tplinkdns.com reports the real Public IP and is a handy cross-check. Because the old TTL was 3600, prd health is warning (propagating) for 15 min and error until resolver caches expire (up to ~1 h) after the first Record Update.
- **[2026-10-15] env-per-record:** each environment owns one Managed Record: dev `kotwica-dev`, tst `home-tst` (watches `home-tst.stanham.com:443`), prod `home`. All three must exist at GoDaddy before Kotwica runs, because it never creates records.
