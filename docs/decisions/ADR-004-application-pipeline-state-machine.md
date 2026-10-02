# ADR-004: Application Pipeline as a State Machine With Optimistic Concurrency and Outbox

- **Status:** Accepted
- **Date:** 2026-10-02

## Context

Several recruiters may work the same applicant list; candidates can withdraw at any time; every change must notify
someone and feed analytics. Free-form status updates lead to impossible states (hired after rejected) and lost updates.

## Decision

- Explicit transitions per actor: recruiters move applied → screening → interview → offer → hired, or reject at any
  active step; candidates may only withdraw; hired/rejected/withdrawn are terminal.
- Each change carries `expectedVersion`; a mismatch returns 409.
- The status update, history row and outbox event are written in one statement/transaction
  ([`sql/transition.sql`](../../sql/transition.sql)); notifications and analytics consume the events.

## Alternatives Considered

- **Pessimistic locking** — prevents conflicts but holds locks across user think-time.
- **Last write wins** — silently loses a colleague's decision.
- **Workflow engine** — useful for configurable per-company pipelines; heavier than needed for a fixed pipeline.

## Trade-offs

Clients must handle 409 by refreshing. Configurable per-company stages would require data-driven transitions.

## Consequences

The SQL transition is verified against PostgreSQL in tests (stale versions change nothing; history and outbox are
written together).
