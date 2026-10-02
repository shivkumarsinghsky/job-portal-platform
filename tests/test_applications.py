import threading

import pytest

from jobs.applications import ApplicationService, ConflictError, Status, TransitionError

from .conftest import RECRUITER, job_by_title


def test_apply_is_idempotent_by_key_and_unique_per_job(portal):
    job = job_by_title(portal, "Frontend Engineer")
    first, created = portal.apply("cand-1", job.id, "key-1")
    again, created_again = portal.apply("cand-1", job.id, "key-1")
    without_key, created_3 = portal.apply("cand-1", job.id, None)
    assert created and not created_again and not created_3
    assert first.id == again.id == without_key.id
    assert len(portal.applications.for_job(job.id)) == 1


def test_concurrent_submissions_create_one_application():
    svc = ApplicationService()
    results = []
    threads = [threading.Thread(target=lambda: results.append(svc.apply("job", "cand", "k"))) for _ in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len({a.id for a, _ in results}) == 1 and sum(created for _, created in results) == 1
    assert [e.type for e in svc.outbox] == ["ApplicationSubmitted"]


def test_cannot_apply_to_closed_or_own_jobs(portal):
    job = job_by_title(portal, "Platform Engineer")
    with pytest.raises(PermissionError):
        portal.apply(RECRUITER, job.id, None)
    portal.close_job(RECRUITER, job.id)
    with pytest.raises(ValueError, match="closed"):
        portal.apply("cand-1", job.id, None)


def test_employer_pipeline_with_optimistic_concurrency(portal):
    job = job_by_title(portal, "Frontend Engineer")
    app, _ = portal.apply("cand-1", job.id, None)
    app = portal.move(RECRUITER, app.id, Status.SCREENING, expected_version=1)
    with pytest.raises(ConflictError):
        portal.move(RECRUITER, app.id, Status.INTERVIEW, expected_version=1)  # stale version
    for to in (Status.INTERVIEW, Status.OFFER, Status.HIRED):
        app = portal.move(RECRUITER, app.id, to, expected_version=app.version)
    assert app.status is Status.HIRED and app.version == 5
    assert [h[0] for h in app.history] == ["applied", "screening", "interview", "offer", "hired"]
    with pytest.raises(TransitionError):
        portal.move(RECRUITER, app.id, Status.REJECTED, expected_version=5)  # terminal


def test_role_specific_transitions(portal):
    job = job_by_title(portal, "Frontend Engineer")
    app, _ = portal.apply("cand-1", job.id, None)
    with pytest.raises(TransitionError):
        portal.move("cand-1", app.id, Status.SCREENING, expected_version=1)  # candidates can only withdraw
    with pytest.raises(PermissionError):
        portal.move("someone-else", app.id, Status.SCREENING, expected_version=1)
    withdrawn = portal.move("cand-1", app.id, Status.WITHDRAWN, expected_version=1)
    assert withdrawn.status is Status.WITHDRAWN


def test_only_the_company_recruiter_sees_applicants_ranked_by_match(portal, backend_dev):
    job = job_by_title(portal, "Senior Backend Engineer")
    portal.save_profile(backend_dev)
    from jobs.domain import CandidateProfile

    portal.save_profile(CandidateProfile("cand-2", "", ["python"], 1, "Pune", False))
    portal.apply("cand-2", job.id, None)
    portal.apply("cand-1", job.id, None)
    ranked = portal.applicants(RECRUITER, job.id)
    assert [a.candidate for a, _ in ranked] == ["cand-1", "cand-2"]
    with pytest.raises(PermissionError):
        portal.applicants("cand-1", job.id)


def test_salary_range_is_validated(portal):
    company = next(iter(portal.companies.values()))
    with pytest.raises(ValueError):
        portal.post_job(
            RECRUITER,
            company.id,
            title="X Engineer",
            description="d" * 20,
            location="Pune",
            remote=False,
            required_skills=[],
            salary_min=10,
            salary_max=5,
        )
