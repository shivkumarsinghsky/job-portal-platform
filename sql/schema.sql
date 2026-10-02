-- Job portal relational model (PostgreSQL 14+). Source of truth; the search index is derived from it via events.

CREATE TABLE IF NOT EXISTS users (
    id          text PRIMARY KEY,
    email       text NOT NULL UNIQUE,
    created_at  timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS companies (
    id          text PRIMARY KEY,
    name        text NOT NULL,
    created_at  timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS company_recruiters (
    company_id  text NOT NULL REFERENCES companies (id) ON DELETE CASCADE,
    user_id     text NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    role        text NOT NULL CHECK (role IN ('admin', 'recruiter')),
    PRIMARY KEY (company_id, user_id)
);

CREATE TABLE IF NOT EXISTS jobs (
    id               text PRIMARY KEY,
    company_id       text NOT NULL REFERENCES companies (id),
    title            text NOT NULL,
    description      text NOT NULL,
    location         text NOT NULL,
    remote           boolean NOT NULL DEFAULT false,
    employment_type  text NOT NULL CHECK (employment_type IN ('full_time', 'part_time', 'contract')),
    min_years        int NOT NULL DEFAULT 0 CHECK (min_years >= 0),
    salary_min       int CHECK (salary_min >= 0),
    salary_max       int,
    status           text NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'closed')),
    version          int NOT NULL DEFAULT 1,
    posted_at        timestamptz NOT NULL DEFAULT now(),
    CHECK (salary_max IS NULL OR salary_min IS NULL OR salary_max >= salary_min)
);
CREATE INDEX IF NOT EXISTS jobs_company_status ON jobs (company_id, status);

CREATE TABLE IF NOT EXISTS skills (
    id    serial PRIMARY KEY,
    name  text NOT NULL UNIQUE  -- normalised lower-case
);

CREATE TABLE IF NOT EXISTS job_skills (
    job_id    text NOT NULL REFERENCES jobs (id) ON DELETE CASCADE,
    skill_id  int NOT NULL REFERENCES skills (id),
    required  boolean NOT NULL,
    PRIMARY KEY (job_id, skill_id)
);

CREATE TABLE IF NOT EXISTS candidate_profiles (
    user_id         text PRIMARY KEY REFERENCES users (id) ON DELETE CASCADE,
    headline        text NOT NULL DEFAULT '',
    years           int NOT NULL CHECK (years >= 0),
    location        text NOT NULL,
    remote_ok       boolean NOT NULL DEFAULT true,
    desired_salary  int CHECK (desired_salary >= 0),
    resume_key      text,  -- object storage key; the file itself is never stored in the database
    updated_at      timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS candidate_skills (
    user_id   text NOT NULL REFERENCES candidate_profiles (user_id) ON DELETE CASCADE,
    skill_id  int NOT NULL REFERENCES skills (id),
    PRIMARY KEY (user_id, skill_id)
);

CREATE TABLE IF NOT EXISTS applications (
    id            text PRIMARY KEY,
    job_id        text NOT NULL REFERENCES jobs (id),
    candidate_id  text NOT NULL REFERENCES users (id),
    status        text NOT NULL DEFAULT 'applied'
                  CHECK (status IN ('applied', 'screening', 'interview', 'offer', 'hired', 'rejected', 'withdrawn')),
    version       int NOT NULL DEFAULT 1,
    created_at    timestamptz NOT NULL DEFAULT now(),
    UNIQUE (job_id, candidate_id)  -- one application per candidate per job
);
CREATE INDEX IF NOT EXISTS applications_candidate ON applications (candidate_id);

CREATE TABLE IF NOT EXISTS application_events (
    id              bigserial PRIMARY KEY,
    application_id  text NOT NULL REFERENCES applications (id) ON DELETE CASCADE,
    from_status     text,
    to_status       text NOT NULL,
    actor_id        text NOT NULL,
    at              timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS idempotency_keys (
    user_id     text NOT NULL,
    key         text NOT NULL,
    resource_id text NOT NULL,
    created_at  timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, key)
);

CREATE TABLE IF NOT EXISTS outbox (
    id            uuid PRIMARY KEY,
    type          text NOT NULL,
    payload       jsonb NOT NULL,
    created_at    timestamptz NOT NULL DEFAULT now(),
    published_at  timestamptz
);
CREATE INDEX IF NOT EXISTS outbox_unpublished ON outbox (created_at) WHERE published_at IS NULL;
