# Changelog

## [1.0.0] - 2026-10-02

### Added

- Job portal reference system design: requirements, capacity, architecture, API, relational model, search,
  recommendation, event-driven processing, notifications, caching, scaling, reliability, security, trade-offs.
- Python prototype: BM25 job search with field boosts, synonyms, filters and facets; explainable candidate–job
  matching; application pipeline with idempotent submission, optimistic concurrency and an outbox; idempotent
  notifications; FastAPI API.
- PostgreSQL schema and atomic status transition SQL.
- Tests (search, matching, applications, notifications, API, SQL), Dockerfile, docker compose, CI, ADR-001 to ADR-004.
