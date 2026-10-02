"""Application workflow: state machine, idempotent submission, optimistic concurrency and a transactional outbox.

In production all writes below happen in one PostgreSQL transaction (see sql/schema.sql): the application row,
its status history and the outbox row commit together; a dispatcher publishes outbox rows to the event bus.
"""

from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class Status(str, Enum):
    APPLIED = "applied"
    SCREENING = "screening"
    INTERVIEW = "interview"
    OFFER = "offer"
    HIRED = "hired"
    REJECTED = "rejected"
    WITHDRAWN = "withdrawn"


EMPLOYER_TRANSITIONS: dict[Status, set[Status]] = {
    Status.APPLIED: {Status.SCREENING, Status.REJECTED},
    Status.SCREENING: {Status.INTERVIEW, Status.REJECTED},
    Status.INTERVIEW: {Status.OFFER, Status.REJECTED},
    Status.OFFER: {Status.HIRED, Status.REJECTED},
}
CANDIDATE_TRANSITIONS: dict[Status, set[Status]] = {
    s: {Status.WITHDRAWN} for s in (Status.APPLIED, Status.SCREENING, Status.INTERVIEW, Status.OFFER)
}
TERMINAL = {Status.HIRED, Status.REJECTED, Status.WITHDRAWN}


class TransitionError(ValueError):
    pass


class ConflictError(Exception):
    pass


@dataclass
class Application:
    id: str
    job_id: str
    candidate: str
    status: Status = Status.APPLIED
    version: int = 1
    history: list[tuple[Status, str, datetime]] = field(default_factory=list)


@dataclass(frozen=True)
class OutboxEvent:
    id: str
    type: str
    payload: dict[str, Any]


class ApplicationService:
    def __init__(self) -> None:
        self._apps: dict[str, Application] = {}
        self._by_pair: dict[tuple[str, str], str] = {}  # UNIQUE (job_id, candidate)
        self._idempotency: dict[tuple[str, str], str] = {}  # (candidate, Idempotency-Key) → application id
        self.outbox: list[OutboxEvent] = []
        self._lock = threading.Lock()  # stands in for the database transaction

    def _emit(self, type_: str, app: Application, **extra: Any) -> None:
        payload = {"applicationId": app.id, "jobId": app.job_id, "candidate": app.candidate, **extra}
        self.outbox.append(OutboxEvent(str(uuid.uuid4()), type_, payload))

    def apply(self, job_id: str, candidate: str, idempotency_key: str | None = None) -> tuple[Application, bool]:
        """Returns (application, created). Retries with the same key, or re-applying, return the existing one."""
        with self._lock:
            if idempotency_key and (candidate, idempotency_key) in self._idempotency:
                return self._apps[self._idempotency[(candidate, idempotency_key)]], False
            existing = self._by_pair.get((job_id, candidate))
            if existing:
                return self._apps[existing], False
            app = Application("app_" + uuid.uuid4().hex[:12], job_id, candidate)
            app.history.append((Status.APPLIED, candidate, datetime.now(timezone.utc)))
            self._apps[app.id] = app
            self._by_pair[(job_id, candidate)] = app.id
            if idempotency_key:
                self._idempotency[(candidate, idempotency_key)] = app.id
            self._emit("ApplicationSubmitted", app)
            return app, True

    def get(self, app_id: str) -> Application:
        if app_id not in self._apps:
            raise LookupError("application not found")
        return self._apps[app_id]

    def transition(self, app_id: str, to: Status, actor: str, as_employer: bool, expected_version: int) -> Application:
        with self._lock:
            app = self.get(app_id)
            if app.version != expected_version:
                raise ConflictError(f"version is {app.version}, expected {expected_version}")
            allowed = (EMPLOYER_TRANSITIONS if as_employer else CANDIDATE_TRANSITIONS).get(app.status, set())
            if to not in allowed:
                raise TransitionError(f"cannot move from {app.status.value} to {to.value}")
            previous = app.status
            app.status = to
            app.version += 1
            app.history.append((to, actor, datetime.now(timezone.utc)))
            self._emit("ApplicationStatusChanged", app, previous=previous.value, status=to.value)
            return app

    def for_job(self, job_id: str) -> list[Application]:
        return [a for a in self._apps.values() if a.job_id == job_id]

    def for_candidate(self, candidate: str) -> list[Application]:
        return [a for a in self._apps.values() if a.candidate == candidate]
