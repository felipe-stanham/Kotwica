# Glossary — Ubiquitous Language

This file is the single source of truth for domain vocabulary across this project. Every pitch, spec, doc, and code identifier must use the canonical terms defined here. If a concept does not yet have an entry, it is not yet part of the Ubiquitous Language — invoke the `glossary` skill to add it before using the term in artifacts.

Keep this file under ~200 lines. If it grows beyond that, push project-specific terminology into the relevant `docs/Projects/P-xxxx/spec.md` instead, and keep this file for system-wide concepts only.

---

## Domain Terms

<!--
Entities, roles, business concepts. Alphabetical.

Example:

### Customer

**Definition:** A person or organisation that holds an active subscription. Distinguished from prospects (no subscription) and former customers (cancelled, in grace period).
**Not to be confused with:** User — a Customer may have many Users (humans logging in on their behalf).
**Aliases (deprecated):** Client, Account holder.
-->

---

## System Terms

<!--
Architectural or technical concepts that are project-specific — not standard CS vocabulary. Alphabetical.

Example:

### Ingest Pipeline

**Definition:** The sequence of stages that pulls raw events from external sources, normalises them, and writes to the event store. Owned by the data platform team.
-->

---

## Deprecated

<!--
Terms that used to be in the glossary but were retired. One line each.

Example:

- ~~Client~~ — replaced by [Customer](#customer) on 2026-01-15.
-->
