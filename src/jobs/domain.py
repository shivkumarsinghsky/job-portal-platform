"""Core entities. Production storage is relational (see sql/schema.sql); here they are plain dataclasses."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from enum import Enum


class EmploymentType(str, Enum):
    FULL_TIME = "full_time"
    PART_TIME = "part_time"
    CONTRACT = "contract"


class JobStatus(str, Enum):
    OPEN = "open"
    CLOSED = "closed"


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


@dataclass
class Company:
    id: str
    name: str
    owner: str  # employer user id


@dataclass
class Job:
    id: str
    company_id: str
    title: str
    description: str
    location: str
    remote: bool
    employment_type: EmploymentType
    required_skills: list[str]
    nice_skills: list[str] = field(default_factory=list)
    min_years: int = 0
    salary_min: int | None = None
    salary_max: int | None = None
    status: JobStatus = JobStatus.OPEN


@dataclass
class CandidateProfile:
    user: str
    headline: str
    skills: list[str]
    years: int
    location: str
    remote_ok: bool = True
    desired_salary: int | None = None


def norm_skill(s: str) -> str:
    return s.strip().lower()
