"""Runs sql/schema.sql and sql/transition.sql on a real PostgreSQL. Skipped unless JOB_PORTAL_DATABASE_URL points at
a disposable database (tables are dropped and recreated)."""

import os
import uuid
from pathlib import Path

import pytest

psycopg = pytest.importorskip("psycopg")
URL = os.environ.get("JOB_PORTAL_DATABASE_URL")
SQL = Path(__file__).resolve().parents[1] / "sql"
pytestmark = pytest.mark.skipif(not URL, reason="JOB_PORTAL_DATABASE_URL not set")

TABLES = (
    "outbox, idempotency_keys, application_events, applications, candidate_skills, candidate_profiles, "
    "job_skills, skills, jobs, company_recruiters, companies, users"
)


@pytest.fixture
def conn():
    with psycopg.connect(URL, autocommit=True) as c:
        c.execute(f"DROP TABLE IF EXISTS {TABLES} CASCADE")
        c.execute((SQL / "schema.sql").read_text())
        c.execute("INSERT INTO users (id, email) VALUES ('rec', 'rec@example.test'), ('cand', 'cand@example.test')")
        c.execute("INSERT INTO companies (id, name) VALUES ('co', 'Example Co')")
        c.execute(
            "INSERT INTO jobs (id, company_id, title, description, location, employment_type)"
            " VALUES ('job', 'co', 'Engineer', 'Build things', 'Pune', 'full_time')"
        )
        c.execute("INSERT INTO applications (id, job_id, candidate_id) VALUES ('app', 'job', 'cand')")
        yield c


def transition(conn, frm: str, to: str, version: int):  # type: ignore[no-untyped-def]
    params = {"id": "app", "from": frm, "to": to, "version": version, "actor": "rec", "event_id": str(uuid.uuid4())}
    return conn.execute((SQL / "transition.sql").read_text(), params).fetchall()


def test_constraints(conn):
    with pytest.raises(psycopg.errors.UniqueViolation):
        conn.execute("INSERT INTO applications (id, job_id, candidate_id) VALUES ('app2', 'job', 'cand')")
    with pytest.raises(psycopg.errors.CheckViolation):
        conn.execute(
            "INSERT INTO jobs (id, company_id, title, description, location, employment_type, salary_min,"
            " salary_max) VALUES ('j2', 'co', 't', 'd', 'l', 'full_time', 10, 5)"
        )


def test_transition_is_atomic_and_optimistic(conn):
    assert transition(conn, "applied", "screening", 1) == [(2,)]
    assert transition(conn, "applied", "screening", 1) == []  # stale version: nothing changes
    assert transition(conn, "screening", "interview", 1) == []
    assert conn.execute("SELECT status, version FROM applications").fetchone() == ("screening", 2)
    assert conn.execute("SELECT count(*) FROM application_events").fetchone() == (1,)
    payload = conn.execute("SELECT type, payload FROM outbox").fetchone()
    assert payload[0] == "ApplicationStatusChanged" and payload[1]["status"] == "screening"
