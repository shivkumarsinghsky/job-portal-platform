"""HTTP API of the prototype. `X-User` stands in for the subject of a verified access token."""

from __future__ import annotations

from typing import Annotated, Any, Literal

from fastapi import FastAPI, Header, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, model_validator

from jobs.applications import Application, ConflictError, Status, TransitionError
from jobs.domain import CandidateProfile, Job
from jobs.portal import Portal
from jobs.search import Filters

User = Annotated[str, Header(alias="X-User", pattern=r"^[a-z0-9_-]{1,40}$")]


class NewCompany(BaseModel):
    name: str = Field(min_length=1, max_length=120)


class NewJob(BaseModel):
    company_id: str
    title: str = Field(min_length=3, max_length=120)
    description: str = Field(min_length=10, max_length=20_000)
    location: str = Field(min_length=2, max_length=80)
    remote: bool = False
    employment_type: Literal["full_time", "part_time", "contract"] = "full_time"
    required_skills: list[str] = Field(default_factory=list, max_length=30)
    nice_skills: list[str] = Field(default_factory=list, max_length=30)
    min_years: int = Field(default=0, ge=0, le=40)
    salary_min: int | None = Field(default=None, ge=0)
    salary_max: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def salary_range(self) -> NewJob:
        if self.salary_min is not None and self.salary_max is not None and self.salary_min > self.salary_max:
            raise ValueError("salary_min must not exceed salary_max")
        return self


class Profile(BaseModel):
    headline: str = Field(max_length=200)
    skills: list[str] = Field(max_length=50)
    years: int = Field(ge=0, le=60)
    location: str = Field(min_length=2, max_length=80)
    remote_ok: bool = True
    desired_salary: int | None = Field(default=None, ge=0)


class Move(BaseModel):
    to: Status
    expected_version: int = Field(ge=1)


def job_out(j: Job) -> dict[str, Any]:
    return {
        "id": j.id,
        "companyId": j.company_id,
        "title": j.title,
        "location": j.location,
        "remote": j.remote,
        "employmentType": j.employment_type.value,
        "requiredSkills": j.required_skills,
        "niceSkills": j.nice_skills,
        "minYears": j.min_years,
        "salaryMin": j.salary_min,
        "salaryMax": j.salary_max,
        "status": j.status.value,
    }


def app_out(a: Application) -> dict[str, Any]:
    return {"id": a.id, "jobId": a.job_id, "candidate": a.candidate, "status": a.status.value, "version": a.version}


def create_app(portal: Portal | None = None) -> FastAPI:
    p = portal or Portal()
    app = FastAPI(title="Job Portal — reference prototype", version="1.0.0")

    def guard(fn: Any, *args: Any, **kwargs: Any) -> Any:
        try:
            return fn(*args, **kwargs)
        except LookupError as e:
            raise HTTPException(404, str(e)) from e
        except PermissionError as e:
            raise HTTPException(403, str(e)) from e
        except ConflictError as e:
            raise HTTPException(409, str(e)) from e
        except (TransitionError, ValueError) as e:
            raise HTTPException(422, str(e)) from e

    @app.post("/v1/companies", status_code=201)
    def create_company(body: NewCompany, user: User) -> dict[str, str]:
        c = p.create_company(user, body.name)
        return {"id": c.id, "name": c.name}

    @app.post("/v1/jobs", status_code=201)
    def post_job(body: NewJob, user: User) -> dict[str, Any]:
        fields = body.model_dump(exclude={"company_id"})
        return job_out(guard(p.post_job, user, body.company_id, **fields))

    @app.post("/v1/jobs/{job_id}/close")
    def close_job(job_id: str, user: User) -> dict[str, Any]:
        return job_out(guard(p.close_job, user, job_id))

    @app.get("/v1/jobs/search")
    def search(
        q: str = "",
        location: str | None = None,
        remote: bool | None = None,
        employment_type: Literal["full_time", "part_time", "contract"] | None = None,
        min_salary: Annotated[int | None, Query(ge=0)] = None,
        max_years: Annotated[int | None, Query(ge=0)] = None,
        page: Annotated[int, Query(ge=1, le=100)] = 1,
        size: Annotated[int, Query(ge=1, le=50)] = 10,
    ) -> dict[str, Any]:
        filters = Filters(location, remote, employment_type, min_salary, max_years)
        r = p.search(q, filters, (page - 1) * size, size)
        return {
            "total": r.total,
            "page": page,
            "items": [{**job_out(j), "score": round(s, 3)} for j, s in r.hits],
            "facets": r.facets,
        }

    @app.get("/v1/jobs/{job_id}")
    def get_job(job_id: str) -> dict[str, Any]:
        return job_out(guard(p.get_job, job_id))

    @app.put("/v1/candidates/me")
    def save_profile(body: Profile, user: User) -> dict[str, str]:
        p.save_profile(CandidateProfile(user, **body.model_dump()))
        return {"user": user}

    @app.get("/v1/candidates/me/recommendations")
    def recommendations(user: User) -> list[dict[str, Any]]:
        return [
            {
                "job": job_out(p.jobs[m.job_id]),
                "score": m.score,
                "components": m.components,
                "missingSkills": m.missing_skills,
            }
            for m in guard(p.recommendations, user)
        ]

    @app.post("/v1/jobs/{job_id}/applications")
    def apply(
        job_id: str,
        user: User,
        idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key", max_length=100)] = None,
    ) -> JSONResponse:
        application, created = guard(p.apply, user, job_id, idempotency_key)
        return JSONResponse(app_out(application), status_code=201 if created else 200)

    @app.get("/v1/jobs/{job_id}/applications")
    def applicants(job_id: str, user: User) -> list[dict[str, Any]]:
        return [
            {**app_out(a), "match": m.score if m else None, "missingSkills": m.missing_skills if m else []}
            for a, m in guard(p.applicants, user, job_id)
        ]

    @app.post("/v1/applications/{app_id}/transition")
    def move(app_id: str, body: Move, user: User) -> dict[str, Any]:
        return app_out(guard(p.move, user, app_id, body.to, body.expected_version))

    @app.get("/v1/applications/me")
    def my_applications(user: User) -> list[dict[str, Any]]:
        return [app_out(a) for a in p.applications.for_candidate(user)]

    @app.get("/v1/notifications")
    def notifications(user: User) -> list[str]:
        return [n.text for n in p.notifications.inbox.get(user, [])]

    return app
