# Kotwica

Home DDNS and certificate watch. A Latarnia Service App that keeps the Managed Record `home.stanham.com` (A, TTL 600) equal to the home Public IP through the GoDaddy API, and watches DNS and TLS certificates of the Watched Hosts `home.stanham.com:443` and `:8443`. Status shows up on the Latarnia dashboard (`/health`) and in Kotwica's UI resources (`status`, `hosts`, `updates`).

Spec and design: `docs/Projects/P-0001.md` and `docs/Projects/P-0001/`. System overview: `docs/SYSTEM.md`.

## Develop and test

```bash
python3.13 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python -m pytest -m "not integration"   # fakes only, no network
.venv/bin/python -m pytest                         # also the [int] tests (ENV=dev, real DNS/TLS/GoDaddy)
.venv/bin/python app.py --port 8150 --data-dir ./data   # ENV=dev by default
```

Never run anything with `ENV=prod` on a development machine. Configuration precedence: process environment, then `.env` (local only, see `.env.example`), then the defaults in `kotwica/config.py`. Local runs use the dev Managed Record `kotwica-dev.stanham.com`.

## Operator notes

### Dev Managed Record (once)

Kotwica never creates the Managed Record. Before running the `[int]` tests or a dev instance with a token:

1. At GoDaddy, create `kotwica-dev.stanham.com` as an A record, value `192.0.2.1`, TTL 3600 (any other record type under that name must not exist).
2. Put a GoDaddy Personal Access Token in `.env` as `DEV_GODADDY_API_TOKEN=...` (Bearer auth; the legacy `sso-key` format is not supported).
3. Run `.venv/bin/python -m pytest -m integration`. After one sync cycle the record must read the current Public IP with TTL 600, and a second cycle must not write.

### Production (Pi, Latarnia prd)

1. Add the token to `/opt/latarnia/prd/secrets.env` as `GODADDY_API_TOKEN='...'` (file mode 600). Latarnia injects it into the process; `ENV=prd` selects the Managed Record `home`.
2. Install the App under Latarnia prd and start it from the dashboard.
3. Check Kotwica on the dashboard: `/health` should be `good`. The first Record Update rewrites the `home` TTL from 3600 to 600 and is logged at WARNING.
4. Only prd manages `home`. tst runs Kotwica too and manages `home-tst.stanham.com` (see below).

### Tst Managed Record (once)

Latarnia tst on the Pi runs Kotwica against its own record, `home-tst.stanham.com`, the public name of the tst environment (Caddy and Latarnia tst serve it on :443, configured in Latarnia, not here):

1. At GoDaddy, create `home-tst.stanham.com` as an A record with the current Public IP, TTL 3600 (any other record type under that name must not exist). The first sync rewrites the TTL to 600.
2. Add the token to `/opt/latarnia/tst/secrets.env` as `GODADDY_API_TOKEN='...'` (file mode 600). Latarnia sets `ENV=tst`, which selects `home-tst`.
3. tst watches `home-tst.stanham.com:443`. Until Caddy serves a certificate for that name on :443, the TLS check reports it `unreachable` or `invalid` and `/health` is `error`; that is expected during the move.
4. The single-writer guard still refuses `home` anywhere but prd.

### Rotating the token

When the dashboard shows `GoDaddy token rejected`: create a new Personal Access Token at GoDaddy, replace `GODADDY_API_TOKEN` in `/opt/latarnia/prd/secrets.env`, restart Kotwica from the dashboard. The next sync cycle (within 5 minutes) clears the error.

### DNS propagation

The GoDaddy minimum TTL is 600 s. After a Record Update strict resolvers may serve the old IP for about 10 minutes, so Kotwica reports `DNS propagating` as a warning for up to 15 minutes after a successful update before treating a wrong answer as an error.

### Notes on the sync

- If GoDaddy holds more than one A record under the Managed Record name, Kotwica writes the single correct record over them (one Record Update, possibly with `old_ip == new_ip`).
- A GoDaddy 404 (for instance `UNKNOWN_DOMAIN`) is reported as `Managed Record ... missing`; the status code is shown in the `status` resource's `last_error`.
- With no Managed Record configured (watch-only, e.g. `TST_MANAGED_RECORD=none`) Kotwica still detects the Public IP, so the DNS watch can compare, but never calls GoDaddy.

### Checks that only run on the Pi

Kotwica checks TLS locally (`127.0.0.1` with the hostname as SNI) in tst and prd, so a good result does not prove the router's port forward works from the internet.

### CLI

`python app.py --port P --data-dir D` is how Latarnia launches it. Extra options: `--host` (default `127.0.0.1`) and `--env-file` (default `.env` next to `app.py`).
