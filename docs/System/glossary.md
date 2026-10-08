# Glossary — Ubiquitous Language

This file is the single source of truth for domain vocabulary across this project. Every pitch, spec, doc, and code identifier must use the canonical terms defined here. If a concept does not yet have an entry, it is not yet part of the Ubiquitous Language — invoke the `glossary` skill to add it before using the term in artifacts.

Keep this file under ~200 lines. If it grows beyond that, push project-specific terminology into the relevant `docs/Projects/P-xxxx/spec.md` instead, and keep this file for system-wide concepts only.

---

## Domain Terms

### Public IP

**Definition:** The IPv4 address the internet sees for the home connection where the Pi runs. It is assigned by the ISP and changes without notice.
**Not to be confused with:** The Pi's local (LAN) address, which never appears in public DNS.

### Watched Host

**Definition:** A hostname and port pair that Kotwica checks from the outside view: its DNS name must resolve to the expected IP and the TLS certificate served on that port must be valid and not near expiry. Two Watched Hosts may share one hostname on different ports.
**Not to be confused with:** Health Check — Kotwica reports the state of its Watched Hosts through its own Health Check, but checking a Watched Host is not a Health Check.

---

## System Terms

Terms imported from the Latarnia platform, whose contract Kotwica implements. Latarnia's glossary is the authority for these; keep the meaning aligned.

### App

**Definition:** The fundamental deployable unit on the Latarnia platform: a self-contained folder with a Manifest and an entry point, discovered by the platform. Every App is either a Service App or a Streamlit App. Kotwica is an App.
**Not to be confused with:** The Latarnia platform process itself ("the platform").

### Health Check

**Definition:** An HTTP GET probe sent by the Latarnia platform to an App's `/health` endpoint, which answers one of `good`, `warning`, or `error` with a short message. The platform shows the result on its dashboard.
**Not to be confused with:** Watched Host checks, which Kotwica performs itself against external hostnames.

### Manifest

**Definition:** The `latarnia.json` file at the root of every App folder. Declares the App's name, type, version, capabilities, and required Secrets; the platform discovers and registers Apps based solely on this file.

### Secret

**Definition:** A runtime credential declared by an App in its Manifest under `requires_secrets`. The platform injects it into the App's process environment at launch and refuses to start the App if a declared Secret is missing.

### Service App

**Definition:** An App of type `"service"` in its Manifest. Runs as a long-running process managed by the platform and must implement `GET /health`.
**Not to be confused with:** Streamlit App.

---

## Deprecated

_None._
