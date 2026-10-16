# Deployments

One row per deployment, newest last. Appended by the `deployment-process` skill as its last step. Never put secrets or token values here.

| Date | Target | Env | Branch | Commit | Notes |
|------|--------|-----|--------|--------|-------|
| 2026-10-16 | homeserver | tst | tst | 36b6908 | First Kotwica deploy (T-0001 + P-0001 scopes 1-4). Regression via tester: all TESTS.md entries pass except the known SIGTERM-timeout test. Code rsynced to `/opt/latarnia/tst/apps/kotwica`, `dnspython` added to the tst platform venv, platform restarted, unit `latarnia-tst-kotwica.service` active on port 8100. Smoke: `/health` = error, as expected for now: `home-tst` A record not yet at GoDaddy (GET empty, authoritative NS has no record of any type) and Caddy has no certificate for `home-tst` (handshake alert `TLSV1_ALERT_INTERNAL_ERROR`, classified `invalid`, no crash). Token accepted (no auth error). |
