# Deployments

One row per deployment, newest last. Appended by the `deployment-process` skill as its last step. Never put secrets or token values here.

| Date | Target | Env | Branch | Commit | Notes |
|------|--------|-----|--------|--------|-------|
| 2026-10-16 | homeserver | tst | tst | 36b6908 | First Kotwica deploy (T-0001 + P-0001 scopes 1-4). Regression via tester: all TESTS.md entries pass except the known SIGTERM-timeout test. Code rsynced to `/opt/latarnia/tst/apps/kotwica`, `dnspython` added to the tst platform venv, platform restarted, unit `latarnia-tst-kotwica.service` active on port 8100. Smoke: `/health` = error, as expected for now: `home-tst` A record not yet at GoDaddy (GET empty, authoritative NS has no record of any type) and Caddy has no certificate for `home-tst` (handshake alert `TLSV1_ALERT_INTERNAL_ERROR`, classified `invalid`, no crash). Token accepted (no auth error). |
| 2026-10-16 | homeserver | tst | tst | e22323a | Redeploy with T-0002 (prd watches :443 only; tst code path unchanged). Regression via tester on dev e22323a: all TESTS.md entries pass except the known SIGTERM-timeout test; extra non-registry `[int]` `tls_real_valid` failed because `latarnia-1.stanham.com:443` was unreachable from the Mac (Hetzner host, unrelated). rsync with --delete, app unit restarted. Smoke: unit active, `home-tst` record_ip = Public IP, TTL 600, no new Record Update (still 1), DNS `ok` on both resolvers; `/health` = error only because Caddy has no certificate for `home-tst` yet (`TLSV1_ALERT_INTERNAL_ERROR`). |
