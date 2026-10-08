# P-0001 Workflows — Kotwica

The diagrams reference capabilities (`cap-XXX`) and key flows (`flow-XX`) from [spec.md](spec.md). Flows 01–04 are in the spec; this file adds the startup, config, and component-level detail.

## W-1 — Startup and shutdown [cap-001, cap-002, cap-003]

```mermaid
sequenceDiagram
    participant L as Latarnia (systemd unit)
    participant A as app.py
    participant C as config
    participant S as StateStore
    participant J as scheduler
    L->>A: python app.py --port P --data-dir D (env: ENV=prd, GODADDY_API_TOKEN)
    A->>C: load(args, os.environ, .env)
    alt single-writer guard violated
        C-->>A: ConfigError
        A->>A: log ERROR "single-writer guard" and exit(1)
    end
    C-->>A: Config
    A->>S: load(D/state.json)
    S-->>A: State (empty on missing/corrupt, WARNING if corrupt)
    A->>J: lifespan start: create sync task + watch task
    J->>J: run sync now, then every sync_interval_s
    J->>J: run watch now, then every watch_interval_s
    Note over A: uvicorn serves /health, /ui, /api/*
    L->>A: SIGTERM
    A->>J: lifespan exit: cancel tasks
    J-->>A: cancelled (in-flight state write completes)
    A->>A: exit(0)
```

## W-2 — Config resolution [cap-002]

```mermaid
flowchart TD
    A[Start] --> B{ENV in process env?}
    B -- yes --> E[raw = process ENV]
    B -- no --> C{ENV in .env?}
    C -- yes --> E2[raw = .env ENV]
    C -- no --> E3[raw = dev]
    E & E2 & E3 --> F{raw}
    F -- prd / prod --> G[env = prod]
    F -- tst --> H[env = tst]
    F -- dev --> I[env = dev]
    F -- other --> X[ConfigError: unknown ENV]
    G & H & I --> J[defaults = DEFAULTS env]
    J --> K[apply .env overrides with prefix DEV_/TST_/PROD_]
    K --> L{token: process GODADDY_API_TOKEN?}
    L -- yes --> M[use it]
    L -- no --> N[use PREFIX_GODADDY_API_TOKEN from .env, or None]
    M & N --> O{managed_record == 'home' and env != prod?}
    O -- yes --> Y[ConfigError: single-writer guard]
    O -- no --> P[Config ready]
```

## W-3 — Sync job internals [cap-004, cap-005, flow-01]

```mermaid
sequenceDiagram
    participant J as scheduler
    participant RS as record_sync
    participant IP as public_ip
    participant E1 as api.ipify.org
    participant E2 as icanhazip.com
    participant GD as godaddy client
    participant API as api.godaddy.com
    participant S as StateStore
    J->>RS: run_sync()
    RS->>IP: detect()
    par
        IP->>E1: GET (5 s)
        IP->>E2: GET (5 s)
    end
    IP-->>RS: Public IP or unknown(reason)
    alt unknown or no Managed Record
        RS->>S: update public_ip/error, last_sync_at
    else known
        RS->>GD: get_a(domain, name)
        GD->>API: GET /v1/domains/stanham.com/records/A/{name}  (Bearer)
        API-->>GD: 200 [..] | 401/403 | 429/5xx
        GD-->>RS: Record | AuthError | Missing | Transient
        opt ip != Public IP or ttl != 600
            RS->>GD: put_a(domain, name, ip, 600)
            GD->>API: PUT same path [{"data": ip, "ttl": 600}]
            API-->>GD: 200 | error
            RS->>S: append RecordUpdate(outcome)
        end
        RS->>S: update record state, last_sync_at
    end
    S->>S: atomic write state.json
```

## W-4 — Watch job internals [cap-006, cap-007, flow-02]

```mermaid
sequenceDiagram
    participant J as scheduler
    participant DW as dns_watch
    participant TW as tls_watch
    participant R as resolvers 8.8.8.8 / 1.1.1.1
    participant T as tls_connect_host:port (Caddy)
    participant S as StateStore
    J->>J: for each Watched Host
    J->>DW: check(host, public_ip)
    loop each resolver
        DW->>R: A? host (5 s, direct)
        R-->>DW: answer | NXDOMAIN | timeout
    end
    DW-->>J: dns_status + resolutions
    J->>TW: check(host, port, connect_host)
    TW->>T: TCP connect + TLS (SNI=host, verify, 10 s)
    T-->>TW: cert | verify error | refused/timeout
    TW-->>J: cert_status, not_after, days_left, issuer, error
    J->>S: replace WatchedHostState
    J->>S: last_watch_at = now; atomic write
```

## W-5 — Health evaluation [cap-008, flow-03]

```mermaid
flowchart TD
    A[GET /health] --> B[Read in-memory State + Config + now]
    B --> C[Evaluate Health Rules 1..13 in order]
    C --> D[matches = rules whose condition holds]
    D --> E{matches empty?}
    E -- yes --> F[good: DNS ip ok; certs min_days+ days]
    E -- no --> G[level = worst of matches]
    G --> H[message = first match + ' (+N more)' if N>0]
    H --> I[truncate to 100 chars]
    F & I --> J[extra_info: public_ip, record_ip, last_sync, last_watch, host:port → days_left]
    J --> K[200 JSON]
```

## W-6 — Latarnia UI rendering [cap-009]

```mermaid
sequenceDiagram
    participant U as Operator (browser)
    participant L as Latarnia dashboard
    participant K as Kotwica
    U->>L: open Kotwica UI
    L->>K: GET /ui
    K-->>L: ["status","hosts","updates"]
    L->>K: GET /api/hosts
    K-->>L: [{id, name, dns_status, cert_status, days_left, date_cert_expires, resolutions:[...]}, ...]
    L-->>U: table rendered by platform (date_* as dates, arrays as tables)
    U->>L: open item
    L->>K: GET /api/hosts/1
    K-->>L: {id:1, ...} or 404 {"error","message"}
```

## W-7 — Operator: token rotation [cap-005, cap-008]

```mermaid
flowchart LR
    A[Dashboard: Kotwica error<br/>'GoDaddy token rejected'] --> B[Create new PAT at GoDaddy]
    B --> C[Edit /opt/latarnia/prd/secrets.env<br/>GODADDY_API_TOKEN='...']
    C --> D[Restart Kotwica from dashboard]
    D --> E[Next sync tick: GET 200 → health recovers]
```
