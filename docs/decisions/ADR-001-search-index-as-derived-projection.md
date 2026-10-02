# ADR-001: Search Index as a Derived Projection Fed by Events

- **Status:** Accepted
- **Date:** 2026-10-02

## Context

Job search needs full-text relevance, synonyms, structured filters and facets at low latency. PostgreSQL full-text
search can cover small catalogues, but relevance tuning, facets and scaling reads are easier in a search engine. Two
stores raise the question of which one is authoritative and how they stay in sync.

## Decision

PostgreSQL is the source of truth. A search index (Elasticsearch/OpenSearch) is a **derived projection**: the job
service writes an outbox event in the same transaction as the job change; an indexer consumes events, denormalises
the job and upserts the document using the job **version** as external version. A nightly reconciliation repairs
drift; mapping changes rebuild a new index behind an alias.

## Alternatives Considered

- **PostgreSQL full-text search only** — one store, transactional freshness; weaker relevance tooling and facets, and
  search load competes with writes.
- **Dual writes from the service** — simple, but a failure between the two writes leaves them inconsistent.
- **Change data capture (Debezium) instead of an outbox** — no application changes; harder to shape business events.

## Trade-offs

Search results are eventually consistent (seconds). Operating a search cluster and reindexing is additional work.

## Consequences

Closed jobs disappear from search shortly after closing; the job page and applications always use PostgreSQL. The
prototype's in-process `JobIndex` models the same upsert/delete semantics.
