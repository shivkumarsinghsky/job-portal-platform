# Job Portal — Reference System Design and Prototype

[![CI](https://github.com/shivkumarsinghsky/job-portal-platform/actions/workflows/ci.yml/badge.svg)](https://github.com/shivkumarsinghsky/job-portal-platform/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/python-3.10%2B-blue)
![FastAPI](https://img.shields.io/badge/FastAPI-API-009688)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-schema-336791)
![License](https://img.shields.io/badge/license-MIT-green)

> **Reference system design inspired by publicly known product requirements of job portals.** It does not describe
> any company's internal architecture.

A scalable **job portal** architecture by **Shiv Kumar**. The product side covers candidates, recruiters, companies,
job postings, search, applications, resumes, notifications, recommendations and analytics. The design side covers
the system design: search indexing, matching, the application workflow, event-driven processing and scaling.

A Python/FastAPI prototype implements the parts that carry the design's correctness and relevance concerns:

- BM25 job search with filters and facets;
- explainable candidate–job matching;
- an application pipeline with idempotency, optimistic concurrency and a transactional outbox;
- idempotent notifications.

A PostgreSQL schema backs the relational model, and tests cover all of it.

## Overview

| Actor | Can |
|---|---|
| Candidate | Search jobs, keep a profile, get recommendations, apply, follow status, withdraw |
| Recruiter | Create a company, post and close jobs, review applicants ranked by match, move them through the pipeline |
| Platform | Index jobs for search, notify both sides, produce funnel analytics |

## Architecture

```mermaid
flowchart TB
    Users["Candidates / Recruiters"] --> GW["API Gateway"]
    GW --> Jobs["Job Service"]
    GW --> Search["Search Service"]
    GW --> Profiles["Profile Service"]
    GW --> Apps["Application Service"]
    GW --> Reco["Recommendation Service"]
    Jobs --> PG[("PostgreSQL<br/>source of truth")]
    Profiles --> PG
    Apps --> PG
    Profiles --> S3[("Object storage<br/>resumes")]
    PG -->|"outbox events"| Bus[["Event bus"]]
    Bus --> Indexer["Indexer"] --> Index[("Search index")]
    Search --> Index
    Reco --> Index
    Bus --> Notify["Notification Service"]
    Bus --> DW[("Analytics")]
```

Full design — requirements, capacity estimate, API, ER model, search and recommendation architecture, events,
notifications, caching, scaling, security, trade-offs: **[docs/architecture.md](docs/architecture.md)**.

## Key Capabilities

| Area | Prototype implementation |
|---|---|
| Job search | Inverted index with **BM25**, field boosts (title 3×, skills 2×, description 1×), synonyms (k8s → kubernetes), plural folding, filters (location, remote, type, salary, experience), facets, pagination (`search.py`) |
| Search indexing | Upsert/delete on job changes; closed jobs leave the index (`JobIndex.upsert`) |
| Recommendations | Candidate generation from the index + explainable weighted scoring with missing skills (`matching.py`) |
| Applicant ranking | Recruiters see applicants sorted by match score |
| Applications | State machine per actor, idempotent submission (key + unique pair), optimistic concurrency, status history (`applications.py`) |
| Event-driven processing | Transactional outbox and dispatcher; notifications idempotent by event id (`notifications.py`) |
| Authorization | Recruiters act only for their company; candidates only on their own applications; no applying to your own job |
| Data model | PostgreSQL schema with constraints, and an atomic transition + history + outbox statement (`sql/`) |

## Technology Stack

| Area | Choice |
|---|---|
| Prototype | Python 3.10+, FastAPI, pydantic v2 |
| Source of truth (design and SQL) | PostgreSQL |
| Search (design) | Elasticsearch / OpenSearch; prototype: in-process BM25 index |
| Messaging (design) | Kafka or RabbitMQ with a transactional outbox |
| Files (design) | Object storage with pre-signed URLs |
| Tests | pytest (unit, API, PostgreSQL), ruff, mypy |

## Repository Structure

```text
job-portal-platform/
├── docs/
│   ├── architecture.md      # full reference system design
│   └── decisions/           # ADR-001 … ADR-004
├── src/jobs/
│   ├── domain.py            # companies, jobs, candidate profiles
│   ├── search.py            # analyzer, BM25 index, filters, facets
│   ├── matching.py          # explainable candidate–job scoring
│   ├── applications.py      # pipeline state machine, idempotency, outbox
│   ├── notifications.py     # outbox dispatcher, idempotent notification service
│   ├── portal.py            # service layer and authorization
│   ├── api.py               # FastAPI endpoints
│   └── seed.py              # fictional sample jobs
├── sql/
│   ├── schema.sql           # relational model
│   └── transition.sql       # optimistic, atomic status transition with history and outbox
├── tests/                   # search, matching, applications, notifications, API, SQL
└── docker/  docker-compose.yml
```

## Getting Started

```bash
git clone https://github.com/shivkumarsinghsky/job-portal-platform.git
cd job-portal-platform
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest
python -m jobs --port 8000 --seed        # sample jobs owned by recruiter-1; or: docker compose up -d --build
```

Interactive API docs: <http://localhost:8000/docs>. The prototype keeps data in memory.

## Configuration

The prototype needs no configuration. `.env.example` documents `JOB_PORTAL_DATABASE_URL`, used only by the optional
SQL tests. No secrets are committed.

## API Examples

The `X-User` header stands in for the subject of a verified access token.

```http
GET /v1/jobs/search?q=k8s&remote=true
→ 200 { "total": 1, "items": [{ "title": "Platform Engineer", "score": 2.488, ... }],
        "facets": { "location": {...}, "employment_type": {...}, "remote": {...} } }

PUT /v1/candidates/me                      X-User: cand-1
{ "headline": "Backend developer", "skills": ["Python", "PostgreSQL", "Kafka"], "years": 6, "location": "Berlin" }

GET /v1/candidates/me/recommendations      X-User: cand-1
→ [{ "job": { "title": "Senior Backend Engineer", ... }, "score": 0.9,
     "components": { "required_skills": 1.0, "experience": 1.0, ... }, "missingSkills": [] }]

POST /v1/jobs/{jobId}/applications         X-User: cand-1   Idempotency-Key: 7c1e...
→ 201 (first time)   200 (retry with the same key, or a second click)

POST /v1/applications/{appId}/transition   X-User: recruiter-1
{ "to": "screening", "expectedVersion": 1 }
→ 200 { "status": "screening", "version": 2 }   409 on a stale version   422 on an invalid transition
```

## Testing

```bash
pytest                                   # 25 tests (SQL tests skip without a database)
ruff check . && ruff format --check . && mypy

docker compose up -d postgres
JOB_PORTAL_DATABASE_URL=postgresql://jobs:jobs-local-dev@localhost:5432/jobs pytest   # include SQL tests
```

| Suite | Verifies |
|---|---|
| `test_search.py` | Analyzer, title boost ranking, synonyms, filters, remote/location semantics, facets, pagination, closing and reindexing |
| `test_matching.py` | Weights, explainable components, missing skills, salary fit, recommendations |
| `test_applications.py` | Idempotent submission (incl. 20 concurrent requests), closed/own jobs, pipeline with optimistic concurrency, role-specific transitions, applicant ranking and access |
| `test_notifications.py` | Outbox → notifications, idempotent handling of redelivered events, dispatcher position |
| `test_api.py` | End-to-end hiring flow over HTTP and error mapping (403/404/409/422) |
| `test_sql.py` | Schema constraints and the atomic, optimistic transition on PostgreSQL |

## Docker

`docker compose up -d --build` starts the prototype API on port 8000 (seeded with sample jobs). It also starts a
PostgreSQL instance initialised with `sql/schema.sql` for the SQL tests and for exploring the model.

## Architecture Decisions

| ADR | Decision |
|---|---|
| [ADR-001](docs/decisions/ADR-001-search-index-as-derived-projection.md) | Search index as a derived projection fed by events |
| [ADR-002](docs/decisions/ADR-002-idempotent-applications-with-db-constraints.md) | Idempotent applications backed by database constraints |
| [ADR-003](docs/decisions/ADR-003-explainable-two-stage-matching.md) | Two-stage, explainable matching |
| [ADR-004](docs/decisions/ADR-004-application-pipeline-state-machine.md) | Application pipeline state machine with optimistic concurrency and outbox |

## Scalability Considerations

- Read-heavy (~50:1). Search and job pages are served by a sharded, replicated search index plus caches; PostgreSQL
  handles low-volume, correctness-critical writes.
- Stateless services scale horizontally; resume processing and notifications are asynchronous worker pools.
- The search index is rebuildable from PostgreSQL behind an alias for zero-downtime mapping changes.
- Applications can be hash-partitioned by job id and archived after the retention window.

## Reliability

Idempotent submission and consumers. Optimistic concurrency for pipeline changes. A transactional outbox instead of
dual writes. Versioned index upserts so older events cannot overwrite newer documents, plus a nightly
reconciliation. Graceful degradation when recommendations or search are unavailable.

## Security

- **Authorization in the service layer:** company-scoped recruiter actions; candidates only on their own
  applications; recruiters see resumes only of applicants to their jobs.
- **Input validation:** pydantic schemas (lengths, ranges, salary range, enums, header formats).
- **Resumes:** object storage with pre-signed URLs, scanning and encryption.
- **Abuse protection:** rate limits on applications and searches.
- **Not implemented in the prototype:** OIDC authentication (the `X-User` header is a stand-in) and resume upload.

## Observability

Search quality metrics (zero-result rate, click/apply-through by position), indexing lag, duplicate-submission and 409
rates, funnel conversion, and notification delivery — see [architecture](docs/architecture.md#observability). The
prototype exposes FastAPI's OpenAPI docs; metrics and tracing are described, not implemented.

## Future Improvements

Not implemented yet:

- Elasticsearch/OpenSearch indexer consuming outbox events; saved-search alerts (percolator queries).
- Resume upload, parsing and skill extraction; OIDC authentication.
- Learned ranking with behavioural signals and fairness evaluation.
- Persistence of the prototype on PostgreSQL (the schema and transition SQL exist and are tested).
- Analytics pipeline (funnel, time-to-hire) and recruiter dashboards.

## Related Projects

- [System Design Architecture](https://github.com/shivkumarsinghsky/system-design-architecture) — [job portal design](https://github.com/shivkumarsinghsky/system-design-architecture/blob/main/docs/designs/05-job-portal.md) and the capacity model
- [Event-Driven Platform](https://github.com/shivkumarsinghsky/event-driven-platform) — outbox, idempotent consumers, retries and DLQs
- [Microservices Patterns](https://github.com/shivkumarsinghsky/microservices-patterns) — idempotency, saga and outbox patterns
- [Social Media Platform](https://github.com/shivkumarsinghsky/social-media-platform) — feed, notifications and search at scale
- [RAG Enterprise Assistant](https://github.com/shivkumarsinghsky/rag-enterprise-assistant) — hybrid BM25 + vector retrieval

## Author

**Shiv Kumar** — Senior Software Engineer / Software Architect
GitHub: [github.com/shivkumarsinghsky](https://github.com/shivkumarsinghsky)

## License

[MIT](LICENSE)
