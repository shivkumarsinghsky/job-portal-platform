"""Small, fictional sample data set for demos and tests."""

from __future__ import annotations

from jobs.domain import Job
from jobs.portal import Portal

SAMPLE_JOBS: list[dict[str, object]] = [
    {
        "title": "Senior Backend Engineer",
        "description": "Design and build Python services on PostgreSQL and Kafka. Own reliability of the job pipeline.",
        "location": "Berlin",
        "remote": False,
        "required_skills": ["python", "postgresql", "kafka"],
        "nice_skills": ["kubernetes"],
        "min_years": 5,
        "salary_min": 80000,
        "salary_max": 100000,
    },
    {
        "title": "Platform Engineer",
        "description": "Run Kubernetes clusters, Terraform and observability for product teams.",
        "location": "London",
        "remote": True,
        "required_skills": ["kubernetes", "terraform"],
        "nice_skills": ["go", "python"],
        "min_years": 3,
        "salary_min": 70000,
        "salary_max": 90000,
    },
    {
        "title": "Frontend Engineer",
        "description": "Build accessible React and TypeScript interfaces for the candidate experience.",
        "location": "Berlin",
        "remote": True,
        "required_skills": ["react", "typescript"],
        "min_years": 2,
        "salary_min": 60000,
        "salary_max": 75000,
    },
    {
        "title": "Data Engineer (Contract)",
        "description": "Six-month contract building Python and Spark pipelines into the analytics warehouse.",
        "location": "Remote",
        "remote": True,
        "employment_type": "contract",
        "required_skills": ["python", "spark", "sql"],
        "min_years": 4,
    },
    {
        "title": "Junior Python Developer",
        "description": "Join the backend team; mentoring provided. Python, SQL and testing basics.",
        "location": "Pune",
        "remote": False,
        "required_skills": ["python", "sql"],
        "min_years": 0,
        "salary_min": 15000,
        "salary_max": 20000,
    },
]


def load_sample_jobs(portal: Portal, owner: str = "recruiter-1") -> list[Job]:
    company = portal.create_company(owner, "Example Hiring Co")
    return [portal.post_job(owner, company.id, **dict(j)) for j in SAMPLE_JOBS]
