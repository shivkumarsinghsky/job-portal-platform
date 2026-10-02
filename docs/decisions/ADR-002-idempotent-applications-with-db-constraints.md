# ADR-002: Idempotent Application Submission Backed by Database Constraints

- **Status:** Accepted
- **Date:** 2026-10-02

## Context

Applying is the most important write. Mobile retries, double clicks and gateway timeouts produce duplicate requests;
duplicate applications confuse recruiters and skew analytics.

## Decision

- Clients send an `Idempotency-Key`; the service stores `(user, key) → application id`.
- The database enforces `UNIQUE (job_id, candidate_id)`, so even requests with different keys cannot create two
  applications for the same job.
- A repeated request returns the existing application with `200` instead of `201`.

## Alternatives Considered

- **Idempotency keys only** — fails when the client generates a new key per click.
- **Unique constraint only** — correct, but the client cannot distinguish "created" from "already existed" and other
  retried fields (cover letters) may be applied inconsistently.

## Trade-offs

Re-applying after withdrawal needs an explicit rule (reopen the same application rather than creating a new row).

## Consequences

Tests submit the same application 20 times concurrently and verify that one application and one event exist.
