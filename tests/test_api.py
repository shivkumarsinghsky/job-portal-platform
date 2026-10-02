from fastapi.testclient import TestClient

from jobs.api import create_app

from .conftest import RECRUITER, job_by_title

R = {"X-User": RECRUITER}
C = {"X-User": "cand-1"}


def test_end_to_end_hiring_flow(portal):
    c = TestClient(create_app(portal))
    co = c.post("/v1/companies", json={"name": "Acme"}, headers=R).json()
    job = c.post(
        "/v1/jobs",
        headers=R,
        json={
            "company_id": co["id"],
            "title": "Site Reliability Engineer",
            "description": "Run Kubernetes and SLOs.",
            "location": "Pune",
            "remote": True,
            "required_skills": ["kubernetes", "python"],
            "min_years": 3,
            "salary_min": 30000,
            "salary_max": 45000,
        },
    )
    assert job.status_code == 201
    job_id = job.json()["id"]

    found = c.get("/v1/jobs/search", params={"q": "k8s reliability", "remote": True}).json()
    assert found["items"][0]["id"] == job_id and "facets" in found

    assert (
        c.put(
            "/v1/candidates/me",
            headers=C,
            json={"headline": "SRE", "skills": ["Kubernetes", "Python"], "years": 4, "location": "Pune"},
        ).status_code
        == 200
    )
    recs = c.get("/v1/candidates/me/recommendations", headers=C).json()
    assert recs[0]["job"]["id"] == job_id and recs[0]["missingSkills"] == []

    first = c.post(f"/v1/jobs/{job_id}/applications", headers={**C, "Idempotency-Key": "abc-1"})
    retry = c.post(f"/v1/jobs/{job_id}/applications", headers={**C, "Idempotency-Key": "abc-1"})
    assert (first.status_code, retry.status_code) == (201, 200) and first.json()["id"] == retry.json()["id"]
    app_id = first.json()["id"]

    assert c.get(f"/v1/jobs/{job_id}/applications", headers=C).status_code == 403
    applicants = c.get(f"/v1/jobs/{job_id}/applications", headers=R).json()
    assert applicants[0]["candidate"] == "cand-1" and applicants[0]["match"] > 0.8

    moved = c.post(f"/v1/applications/{app_id}/transition", headers=R, json={"to": "screening", "expected_version": 1})
    assert moved.json()["version"] == 2
    stale = c.post(f"/v1/applications/{app_id}/transition", headers=R, json={"to": "interview", "expected_version": 1})
    assert stale.status_code == 409
    invalid = c.post(f"/v1/applications/{app_id}/transition", headers=R, json={"to": "hired", "expected_version": 2})
    assert invalid.status_code == 422

    assert c.get("/v1/applications/me", headers=C).json()[0]["status"] == "screening"
    assert (
        "Your application for Site Reliability Engineer is now screening"
        in c.get("/v1/notifications", headers=C).json()
    )


def test_validation_and_errors(portal):
    c = TestClient(create_app(portal))
    assert c.post("/v1/companies", json={"name": "x"}).status_code == 422  # missing X-User
    assert c.post("/v1/companies", json={"name": "x"}, headers={"X-User": "Bad User!"}).status_code == 422
    other_company = job_by_title(portal, "Frontend Engineer").company_id
    body = {"company_id": other_company, "title": "Hacker", "description": "Not my company at all", "location": "X1"}
    assert c.post("/v1/jobs", json=body, headers=C).status_code == 403
    assert c.post("/v1/jobs", json={**body, "salary_min": 9, "salary_max": 1}, headers=R).status_code == 422
    assert c.get("/v1/jobs/job_missing").status_code == 404
    assert c.get("/v1/candidates/me/recommendations", headers=C).status_code == 404
    assert c.get("/v1/jobs/search", params={"size": 500}).status_code == 422
