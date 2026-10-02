import pytest

from jobs.domain import CandidateProfile
from jobs.portal import Portal
from jobs.seed import load_sample_jobs

RECRUITER = "recruiter-1"


@pytest.fixture
def portal() -> Portal:
    p = Portal()
    load_sample_jobs(p, RECRUITER)
    return p


@pytest.fixture
def backend_dev() -> CandidateProfile:
    return CandidateProfile("cand-1", "Backend developer", ["Python", "PostgreSQL", "Kafka"], 6, "Berlin", True, 85000)


def job_by_title(p: Portal, title: str):  # type: ignore[no-untyped-def]
    return next(j for j in p.jobs.values() if j.title == title)
