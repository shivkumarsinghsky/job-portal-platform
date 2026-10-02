"""Candidate–job matching: an explainable weighted score, used for job recommendations and applicant ranking.

Production: candidate generation from the search index (skills/title query) followed by a learned ranking model;
the explainable features below are typical inputs to such a model.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from jobs.domain import CandidateProfile, Job, norm_skill

WEIGHTS = {"required_skills": 0.5, "nice_skills": 0.1, "experience": 0.2, "location": 0.15, "salary": 0.05}


@dataclass(frozen=True)
class Match:
    job_id: str
    score: float  # 0..1
    components: dict[str, float]
    missing_skills: list[str] = field(default_factory=list)


def match(candidate: CandidateProfile, job: Job) -> Match:
    have = {norm_skill(s) for s in candidate.skills}
    required = [norm_skill(s) for s in job.required_skills]
    nice = [norm_skill(s) for s in job.nice_skills]
    missing = [s for s in required if s not in have]
    comp = {
        "required_skills": (len(required) - len(missing)) / len(required) if required else 1.0,
        "nice_skills": sum(s in have for s in nice) / len(nice) if nice else 0.0,
        "experience": 1.0 if candidate.years >= job.min_years else candidate.years / max(1, job.min_years),
        "location": 1.0
        if (job.remote and candidate.remote_ok) or candidate.location.lower() == job.location.lower()
        else 0.0,
        "salary": 1.0
        if candidate.desired_salary is None or job.salary_max is None or job.salary_max >= candidate.desired_salary
        else 0.0,
    }
    score = sum(WEIGHTS[k] * v for k, v in comp.items())
    return Match(job.id, round(score, 4), comp, missing)


def recommend(candidate: CandidateProfile, jobs: list[Job], limit: int = 10, min_score: float = 0.4) -> list[Match]:
    scored = [m for m in (match(candidate, j) for j in jobs) if m.score >= min_score]
    return sorted(scored, key=lambda m: (-m.score, m.job_id))[:limit]
