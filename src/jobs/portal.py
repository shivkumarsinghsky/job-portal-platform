"""Application service layer: wires companies, jobs, search, matching, applications and notifications."""

from __future__ import annotations

from jobs.applications import Application, ApplicationService, Status
from jobs.domain import CandidateProfile, Company, EmploymentType, Job, JobStatus, new_id
from jobs.matching import Match, match, recommend
from jobs.notifications import NotificationService, OutboxDispatcher
from jobs.search import Filters, JobIndex, SearchResult


class Portal:
    def __init__(self) -> None:
        self.companies: dict[str, Company] = {}
        self.jobs: dict[str, Job] = {}
        self.profiles: dict[str, CandidateProfile] = {}
        self.index = JobIndex()
        self.applications = ApplicationService()
        self.notifications = NotificationService(self.employer_of_job, lambda job_id: self.jobs[job_id].title)
        self.dispatcher = OutboxDispatcher(self.applications.outbox, [self.notifications.handle])

    # --- employers --------------------------------------------------------------------------------------------
    def create_company(self, owner: str, name: str) -> Company:
        c = Company(new_id("co"), name, owner)
        self.companies[c.id] = c
        return c

    def employer_of_job(self, job_id: str) -> str:
        return self.companies[self.jobs[job_id].company_id].owner

    def _own_company(self, user: str, company_id: str) -> Company:
        c = self.companies.get(company_id)
        if c is None:
            raise LookupError("company not found")
        if c.owner != user:
            raise PermissionError("not a recruiter of this company")
        return c

    def post_job(self, user: str, company_id: str, **fields: object) -> Job:
        self._own_company(user, company_id)
        smin, smax = fields.get("salary_min"), fields.get("salary_max")
        if isinstance(smin, int) and isinstance(smax, int) and smin > smax:
            raise ValueError("salary_min must not exceed salary_max")
        fields["employment_type"] = EmploymentType(fields.get("employment_type", "full_time"))
        job = Job(new_id("job"), company_id, **fields)  # type: ignore[arg-type]
        self.jobs[job.id] = job
        self.index.upsert(job)  # production: JobPosted event → indexer (seconds of lag)
        return job

    def close_job(self, user: str, job_id: str) -> Job:
        job = self.get_job(job_id)
        self._own_company(user, job.company_id)
        job.status = JobStatus.CLOSED
        self.index.upsert(job)  # removes it from search
        return job

    def get_job(self, job_id: str) -> Job:
        if job_id not in self.jobs:
            raise LookupError("job not found")
        return self.jobs[job_id]

    def applicants(self, user: str, job_id: str) -> list[tuple[Application, Match | None]]:
        job = self.get_job(job_id)
        self._own_company(user, job.company_id)
        rows = []
        for a in self.applications.for_job(job_id):
            profile = self.profiles.get(a.candidate)
            rows.append((a, match(profile, job) if profile else None))
        return sorted(rows, key=lambda r: -(r[1].score if r[1] else 0.0))

    def move(self, user: str, app_id: str, to: Status, expected_version: int) -> Application:
        app = self.applications.get(app_id)
        if app.candidate == user:
            result = self.applications.transition(app_id, to, user, False, expected_version)
        else:
            self._own_company(user, self.get_job(app.job_id).company_id)
            result = self.applications.transition(app_id, to, user, True, expected_version)
        self.dispatcher.dispatch()  # production: separate dispatcher process
        return result

    # --- candidates -------------------------------------------------------------------------------------------
    def save_profile(self, profile: CandidateProfile) -> None:
        self.profiles[profile.user] = profile

    def search(self, query: str, filters: Filters, offset: int = 0, limit: int = 10) -> SearchResult:
        return self.index.search(query, filters, offset, limit)

    def recommendations(self, user: str, limit: int = 10) -> list[Match]:
        profile = self.profiles.get(user)
        if profile is None:
            raise LookupError("create a profile first")
        # Candidate generation via the index (skills as the query), then scoring.
        found = self.index.search(" ".join(profile.skills), Filters(), 0, 200).hits
        return recommend(profile, [j for j, _ in found], limit)

    def apply(self, user: str, job_id: str, idempotency_key: str | None) -> tuple[Application, bool]:
        job = self.get_job(job_id)
        if job.status is not JobStatus.OPEN:
            raise ValueError("job is closed")
        if self.companies[job.company_id].owner == user:
            raise PermissionError("cannot apply to your own job")
        result = self.applications.apply(job_id, user, idempotency_key)
        self.dispatcher.dispatch()
        return result
