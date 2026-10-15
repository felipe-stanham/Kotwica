# P-0001 Architecture — Kotwica

## Component architecture

These module names are the implementation targets.

```mermaid
flowchart TB
    subgraph Kotwica["Kotwica (Service App, single process)"]
        APP["app.py<br/>CLI args, logging, FastAPI app, lifespan"]
        CFG["kotwica/config.py<br/>Config, per-env DEFAULTS, single-writer guard"]
        ST["kotwica/state.py<br/>State dataclasses, StateStore (load / atomic save)"]
        SCH["kotwica/scheduler.py<br/>sync task + watch task (asyncio)"]
        PIP["kotwica/public_ip.py<br/>two echo services, must agree"]
        GDC["kotwica/godaddy.py<br/>GET/PUT one A record, error kinds"]
        RS["kotwica/record_sync.py<br/>sync job: compare + Record Update"]
        DW["kotwica/dns_watch.py<br/>per-resolver A queries"]
        TW["kotwica/tls_watch.py<br/>TLS handshake, cert expiry"]
        HL["kotwica/health.py<br/>Health Rules → /health payload"]
        UI["kotwica/ui_api.py<br/>/ui, /api/status|hosts|updates"]
    end

    APP --> CFG
    APP --> ST
    APP --> SCH
    APP --> HL
    APP --> UI
    SCH --> RS
    SCH --> DW
    SCH --> TW
    RS --> PIP
    RS --> GDC
    RS --> ST
    DW --> ST
    TW --> ST
    HL --> ST
    UI --> ST
    UI --> HL
```

**Dependency rule:** only `app.py` wires concrete clients. `record_sync`, `dns_watch`, and `tls_watch` receive their clients (httpx client, resolver factory, TLS connect function) as arguments so tests can pass fakes. `health.py` is a pure function of `(State, Config, now)`.

## Repository layout

```
Kotwica/
├── latarnia.json          # Manifest (cap-001)
├── requirements.txt       # fastapi, uvicorn, httpx, dnspython, python-dotenv
├── app.py                 # entry point
├── kotwica/
│   ├── __init__.py
│   ├── config.py
│   ├── state.py
│   ├── scheduler.py
│   ├── public_ip.py
│   ├── godaddy.py
│   ├── record_sync.py
│   ├── dns_watch.py
│   ├── tls_watch.py
│   ├── health.py
│   └── ui_api.py
├── tests/                 # pytest; fakes for HTTP / DNS / TLS
├── .env                   # local dev only, gitignored
└── README.md              # operator notes
```

## Deployment topology

```mermaid
flowchart TB
    subgraph Internet
        GD["GoDaddy DNS API<br/>api.godaddy.com"]
        NS["GoDaddy authoritative NS<br/>zone stanham.com"]
        G8["Google 8.8.8.8"]
        CF["Cloudflare 1.1.1.1"]
        ECHO["api.ipify.org<br/>icanhazip.com"]
    end

    subgraph Home["Home network (dynamic Public IP)"]
        RT["Router<br/>port-forward 443 / 8443"]
        subgraph Pi["Raspberry Pi — homeserver"]
            CAD["Caddy<br/>:443 prd, :8443 tst<br/>ACME client (owns TLS)"]
            subgraph PRD["Latarnia prd"]
                LP["Latarnia platform"]
                K["Kotwica<br/>port allocated 8150–8199<br/>data: /opt/latarnia/prd/data/kotwica/"]
            end
            LT["Latarnia tst<br/>Kotwica (manages kotwica-tst)"]
            SEC["/opt/latarnia/prd/secrets.env<br/>GODADDY_API_TOKEN (mode 600)"]
        end
    end

    RT --> CAD
    CAD --> LP
    CAD --> LT
    SEC -. injected at launch .-> K
    LP -- "GET /health, /ui, /api/*" --> K
    K -- "GET/PUT A record (Bearer)" --> GD
    GD --> NS
    K -- "A? home.stanham.com" --> G8
    K -- "A? home.stanham.com" --> CF
    G8 & CF -.-> NS
    K -- "what is my IP" --> ECHO
    K -- "TLS 127.0.0.1:443/8443<br/>SNI home.stanham.com" --> CAD
```

## External interactions

| System | Direction | Protocol | Used by | Failure handling |
|---|---|---|---|---|
| GoDaddy API `api.godaddy.com` | out | HTTPS, `Authorization: Bearer` | `godaddy.py` | 401/403 → `auth` (error); empty → `missing` (error); 429/5xx/timeout → `transient` (warning) |
| `api.ipify.org`, `icanhazip.com` | out | HTTPS GET, 5 s | `public_ip.py` | either fails or they disagree → Public IP unknown (warning) |
| `8.8.8.8`, `1.1.1.1` | out | DNS/UDP 53, direct, 5 s | `dns_watch.py` | timeout → `failed` for that resolver |
| Caddy on `127.0.0.1:443/8443` | local | TLS with SNI | `tls_watch.py` | verify error → `invalid`; refused/timeout → `unreachable` |
| Latarnia platform | in | HTTP on allocated port | `app.py`, `health.py`, `ui_api.py` | n/a |

## Data flow

```mermaid
flowchart LR
    ECHO[echo services] -->|Public IP| RS[record_sync]
    GD[(GoDaddy A record)] <-->|GET / PUT| RS
    RS -->|record state, Record Updates| ST[(State<br/>memory + state.json)]
    RES[resolvers] -->|answers| DW[dns_watch]
    ST -->|Public IP| DW
    DW -->|dns_status, resolutions| ST
    CAD[Caddy] -->|cert| TW[tls_watch]
    TW -->|cert_status, days_left| ST
    ST --> HL[health] -->|/health| LAT[Latarnia dashboard]
    ST --> UI[ui_api] -->|/ui, /api/*| LAT
```

## Environment matrix

| | dev (Mac) | tst (Pi) | prod (Pi) |
|---|---|---|---|
| Deployed | local `python app.py` | yes | yes |
| `ENV` source | `.env` / default | Latarnia `ENV=tst` | Latarnia `ENV=prd` → `prod` |
| Managed Record | `kotwica-dev.stanham.com` | `kotwica-tst.stanham.com` | `home.stanham.com` |
| TLS connect host | the hostname (public path) | `127.0.0.1` | `127.0.0.1` |
| Token source | `.env` `DEV_GODADDY_API_TOKEN` | Latarnia Secret `GODADDY_API_TOKEN` | Latarnia Secret `GODADDY_API_TOKEN` |
| Log level | DEBUG | WARNING | WARNING |
