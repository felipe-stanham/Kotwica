# Memory Index

Persistent learnings for Kotwica. One line per entry; detail files go in `memory/`.

## Index

- **[2026-10-15] godaddy-pat-scope:** GoDaddy PAT minimum scope for GET+PUT on one A record is still open. A token with every DNS scope works (the `[int]` roundtrip passed). A token with only `domains.dns:update` returns HTTP 401 on the GET, so it cannot read. Not yet tested: `domains.dns:update` plus `domains.domain:read`. Scopes are chosen in the GoDaddy PAT page when generating the token.
- **[2026-10-15] int-roundtrip-needs-reset:** `test_int_dev_record_roundtrip` passes even when no PUT happens. To prove a token can PUT, first reset `kotwica-dev` at GoDaddy to A `192.0.2.1`, TTL 3600, then run `.venv/bin/python -m pytest -m integration`.
- **[2026-10-15] test-app-process-sigterm-flaky:** `tests/test_app_process.py::test_token_never_logged_at_debug` fails with a 5 s timeout on terminate, also on a clean `dev`. Pre-existing and unrelated to config changes; needs its own task.
- **[2026-10-15] env-per-record:** each environment owns one Managed Record: dev `kotwica-dev`, tst `home-tst` (watches `home-tst.stanham.com:443`), prod `home`. All three must exist at GoDaddy before Kotwica runs, because it never creates records.
