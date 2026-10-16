# TESTS.md — Regression Test Registry

Curated critical-path tests only. Each entry describes **what to verify**, the **concrete input(s)**, and the **expected output**. The `tester` agent generates a verification script from the spec, runs it, and reports pass/fail.

**Format:**

```
- **test_name:** [What to do, with concrete input] → [Expected result, with concrete output]
```

A vague verb is not enough. Always include real sample values — actual JSON, an actual URL with parameters, an actual file path, a precise status code or output string. If the description could be satisfied by two different implementations, it's too vague.

---

## How Caching Works

The `tester` agent caches generated scripts under `tests/cache/<test_name>.<ext>` alongside `tests/cache/<test_name>.hash` (SHA-256 of the test entry below). On each run:

- If the cached hash matches the current entry → reuse the cached script (no regeneration, no token cost).
- If the hash differs (the entry was edited) or no cache exists → regenerate the script and update the hash.
- If a cached script fails on unchanged spec → treat as a real regression first; only regenerate if you can show the script itself is broken (e.g., dependency renamed).

`tests/cache/` is committed to git — it's the project's accumulated test logic.

---

## Running notes

- Always `ENV=dev`. Never run with `ENV=prod`/`prd` on the Mac. Entries that start the real process use `DEV_MANAGED_RECORD=none` so no request reaches GoDaddy, unless the entry says `[int]`.
- Entries marked `[int]` use the real network and, for the record roundtrip, the dev token in `.env` and the operator-created `kotwica-dev.stanham.com`. They write only `kotwica-dev`.
- The repo's pytest suite (`.venv/bin/python -m pytest -m "not integration"`) already implements these entries with injected fakes; the `tester` agent may call it, but must report each entry by name.
- Known failure, pre-existing and unrelated: `tests/test_app_process.py::test_token_never_logged_at_debug` times out on SIGTERM (see `MEMORY.md`). Report it, do not count it as a regression of the change under test.

---

## Tests

### Service App contract (P-0001 Scope 1)

- **manifest_valid:** Load `latarnia.json` → JSON with `type == "service"`, `main_file == "app.py"`, `config.data_dir == true`, `config.has_UI == true`, `config.requires_secrets == ["GODADDY_API_TOKEN"]`, no `port` field, and non-empty `name`, `version`, `description`, `author`.
- **starts_and_serves_health:** Run `DEV_MANAGED_RECORD=none python app.py --port 18150 --data-dir /tmp/kotwica-test --env-file /nonexistent.env` → within 5 s `GET http://127.0.0.1:18150/health` returns HTTP 200 with JSON whose `health` is one of `good`, `warning`, `error` and a `message` string of at most 100 characters.
- **sigterm_clean_exit:** Send SIGTERM to the process from `starts_and_serves_health` → it exits with code 0 within 5 s.
- **env_prd_maps_to_prod:** Load config with process env `ENV=prd` and no `.env` → `env == "prod"`, `managed_record == "home"`, `tls_connect_host == "127.0.0.1"`.
- **guard_home_outside_prod:** Load config with `ENV=dev` and `.env` containing `DEV_MANAGED_RECORD=home` → startup fails with a message containing `single-writer guard`; same with `ENV=tst` and `TST_MANAGED_RECORD=home`.
- **tst_manages_own_record:** Load config with `ENV=tst` and no overrides → `managed_record == "home-tst"`, `watched_hosts == [("home-tst.stanham.com", 443)]`, `tls_connect_host == "127.0.0.1"`.
- **prd_watches_443_only:** Load config with process env `ENV=prd` and no `.env` → `watched_hosts == [("home.stanham.com", 443)]`.
- **token_never_logged:** Start with `GODADDY_API_TOKEN=gd_pat_SENTINEL123` at DEBUG and run one sync cycle → captured stdout and stderr do not contain `SENTINEL123`.

### Health and UI (P-0001 Scope 2)

- **health_priority:** State with a GoDaddy auth failure, a certificate expiring in 10 days and DNS `partial` → `health == "error"`, message starts with `GoDaddy token rejected` and ends with `(+2 more)`.
- **health_startup:** Empty state, no cycle finished → `{"health": "warning", "message": "Starting: checks not completed yet"}`.
- **api_item_by_id:** With two Watched Hosts, `GET /api/hosts/2` → the second host (`name` of the form `host:port`); `GET /api/hosts/99` → HTTP 404 with JSON keys `error` and `message`.
- **api_no_secrets:** With `GODADDY_API_TOKEN=gd_pat_SENTINEL123`, the full JSON of `/health`, `/api/status`, `/api/hosts`, `/api/updates` → none contains `SENTINEL123`.

### Record sync (P-0001 Scope 3)

- **ip_disagree:** Echo A returns `203.0.113.7`, echo B returns `198.51.100.2` → Public IP unknown, reason contains `disagree`, zero GoDaddy requests in the cycle.
- **sync_updates_on_ip_change:** Public IP `203.0.113.7`, GoDaddy GET returns `[{"data":"198.51.100.2","ttl":600}]` → exactly one PUT to `/v1/domains/stanham.com/records/A/{name}` with body `[{"data":"203.0.113.7","ttl":600}]` and header `Authorization: Bearer <token>`, and one Record Update with `old_ip=198.51.100.2`, `new_ip=203.0.113.7`, `outcome=ok`.
- **sync_missing_record:** GoDaddy GET returns `[]` → no PUT, `/health` is `error` with message `Managed Record {name}.stanham.com missing at GoDaddy`.
- **sync_auth_rejected:** GoDaddy GET returns HTTP 401 → no PUT, `/health` is `error` with message starting `GoDaddy token rejected`.
- **sync_only_one_path:** Run 10 sync cycles with mixed fake responses → every GoDaddy request is GET or PUT on exactly `/v1/domains/stanham.com/records/A/{managed_record}`.
- **[int] dev_record_roundtrip:** `ENV=dev`, operator-created `kotwica-dev.stanham.com` (A, any value), dev token in `.env` → after one sync cycle the record at GoDaddy has `data == <current Public IP>` and `ttl == 600`; a second cycle produces no new Record Update.

### Host watch (P-0001 Scope 4)

- **dns_wrong_in_grace:** Both resolvers answer `[198.51.100.2]`, Public IP `203.0.113.7`, a Record Update with `outcome=ok` happened 5 minutes ago → `/health` is `warning` with a message containing `propagating`.
- **tls_expiring_error:** Fake certificate for `home.stanham.com:443` with `not_after` = now + 2 days → `/health` is `error` with message `home.stanham.com:443 cert expires in 2 days`.
- **tls_sni_and_target:** `tls_connect_host=127.0.0.1`, Watched Host `home.stanham.com:8443` → the TCP connect goes to `127.0.0.1:8443` and the TLS `server_hostname == "home.stanham.com"`.
- **[int] tls_real_expired:** `ENV=dev`, Watched Host `expired.badssl.com:443` → certificate status `invalid` with a reason containing `expired`.
