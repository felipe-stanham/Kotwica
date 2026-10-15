# System: Kotwica

## What This System Does

Kotwica is a Latarnia Service App that runs on the Raspberry Pi (`homeserver`). It keeps one DNS A record, the Managed Record `home.stanham.com`, equal to the home Public IP through the GoDaddy API. It also watches the Watched Hosts (`home.stanham.com:443` and `:8443`): DNS must resolve to the expected IP through public resolvers, and the TLS certificate served by Caddy must be valid and not near expiry. State is exposed through the Latarnia Health Check (`/health`) and Latarnia-rendered UI resources (`/ui`, `/api/*`).

## Stack

- **Language:** Python 3.11+ (developed on 3.13)
- **Framework:** FastAPI + uvicorn; `httpx` (GoDaddy, echo services), `dnspython` (direct resolver queries), stdlib `ssl`/`socket` (TLS)
- **Database:** None. One JSON state file, `{data-dir}/state.json`, written atomically
- **Infrastructure:** Latarnia prd on the Pi. Latarnia runs `python app.py --port {port} --data-dir {dir}` and sets `ENV=prd` and the Secret `GODADDY_API_TOKEN`

## Architecture Principles

- **Latarnia Service App contract is binding:** Manifest `latarnia.json`, `GET /health`, clean exit 0 on SIGTERM, logs to stdout, no declared port, no routes under `/b/`, no HTML (the platform renders the UI from `/ui` and `/api/*`).
- **One writer, one record:** Kotwica writes only the Managed Record, only through GET/PUT `/v1/domains/{domain}/records/A/{name}`. Each environment manages its own record (dev `kotwica-dev`, tst `home-tst`, prod `home`); only `ENV=prod` may manage `home` (single-writer guard). It never creates the record.
- **Config precedence:** process environment > `.env` (local dev only, never deployed) > committed per-env defaults in `kotwica/config.py`. `prd` maps to `prod`.
- **External clients are injected** so tests run with fakes. Only `app.py` wires concrete clients. `health.py` is a pure function of `(State, Config, now)`.
- **Public IP is known only when two echo services agree.** Otherwise no GoDaddy call that cycle. The next cycle is the retry; no in-cycle retries.
- Never log the token, Authorization headers, or full API responses.

## Cross-Project Constraints

- Never run anything with `ENV=prod` outside the Pi. Integration tests use `ENV=dev` and `kotwica-dev.stanham.com` only.
- No alerting, IPv6, certificate issuance, Caddy changes, database, Redis, or provider abstraction.

## Subsystems / Components

- App shell (`app.py`) — CLI args, logging, FastAPI app, lifespan
- Config (`kotwica/config.py`) — env resolution, per-env defaults, single-writer guard
- State store (`kotwica/state.py`) — State dataclasses, atomic JSON persistence
- Scheduler (`kotwica/scheduler.py`) — sync and watch asyncio tasks
- Record sync (`kotwica/public_ip.py`, `godaddy.py`, `record_sync.py`) — Public IP detection and Managed Record updates
- Host watch (`kotwica/dns_watch.py`, `tls_watch.py`) — per-resolver DNS and TLS certificate checks
- Health and UI (`kotwica/health.py`, `ui_api.py`) — Health Rules and Latarnia UI resources

## Logging

- **Framework:** Python `logging`, to stdout
- **Format:** `YYYY-MM-DD HH:MM:SS [LEVEL] module: message`
- **dev level:** DEBUG | **prod level:** WARNING (Record Updates and startup are logged at WARNING so they reach journald)

## Work Artifact Indexes

- Pitches: [docs/Pitches/INDEX.md](Pitches/INDEX.md)
- Tasks: [docs/Tasks/INDEX.md](Tasks/INDEX.md)
- Projects: [docs/Projects/INDEX.md](Projects/INDEX.md)

## Deployment

- Targets and procedures: see `docs/local/deployment.md` (gitignored — not committed).
- Secrets: see `.deploy-secrets` (gitignored — not committed).
- Do NOT inline target details, hostnames, or credentials here.

## Current State

P-0001 (Kotwica v1): all four scopes are implemented on `dev`. Scope 3's real GoDaddy round trip passed on 2026-10-15 (`kotwica-dev`); it stays open only for the minimum token scope check. T-0001 (tst manages `home-tst`) is merged. Not yet deployed.
