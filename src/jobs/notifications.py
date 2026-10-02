"""Outbox dispatcher and notification service (idempotent by event id)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from jobs.applications import OutboxEvent


@dataclass(frozen=True)
class Notification:
    recipient: str
    text: str
    event_id: str


class NotificationService:
    def __init__(self, employer_of_job: Callable[[str], str], job_title: Callable[[str], str]) -> None:
        self._employer_of_job = employer_of_job
        self._job_title = job_title
        self._seen: set[str] = set()
        self.inbox: dict[str, list[Notification]] = {}
        self.emails: list[Notification] = []  # production: email/push provider behind a queue

    def handle(self, event: OutboxEvent) -> bool:
        """Returns False for an already-processed event (at-least-once delivery from the outbox)."""
        if event.id in self._seen:
            return False
        self._seen.add(event.id)
        p = event.payload
        title = self._job_title(p["jobId"])
        if event.type == "ApplicationSubmitted":
            self._send(self._employer_of_job(p["jobId"]), f"New application for {title}", event.id, email=False)
            self._send(p["candidate"], f"Your application for {title} was received", event.id, email=True)
        elif event.type == "ApplicationStatusChanged":
            if p["status"] == "withdrawn":
                self._send(self._employer_of_job(p["jobId"]), f"An applicant withdrew from {title}", event.id)
            else:
                self._send(p["candidate"], f"Your application for {title} is now {p['status']}", event.id, email=True)
        return True

    def _send(self, recipient: str, text: str, event_id: str, email: bool = False) -> None:
        n = Notification(recipient, text, event_id)
        self.inbox.setdefault(recipient, []).append(n)
        if email:
            self.emails.append(n)


class OutboxDispatcher:
    """Polls the outbox from the last published position. Production: SELECT ... FOR UPDATE SKIP LOCKED."""

    def __init__(self, outbox: list[OutboxEvent], handlers: list[Callable[[OutboxEvent], bool]]) -> None:
        self._outbox = outbox
        self._handlers = handlers
        self.position = 0

    def dispatch(self) -> int:
        sent = 0
        while self.position < len(self._outbox):
            event = self._outbox[self.position]
            for h in self._handlers:
                h(event)
            self.position += 1
            sent += 1
        return sent
