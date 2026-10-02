from jobs.applications import OutboxEvent, Status
from jobs.notifications import NotificationService, OutboxDispatcher

from .conftest import RECRUITER, job_by_title


def test_outbox_events_become_notifications(portal):
    job = job_by_title(portal, "Frontend Engineer")
    app, _ = portal.apply("cand-1", job.id, None)
    portal.move(RECRUITER, app.id, Status.SCREENING, expected_version=1)
    inbox = portal.notifications.inbox
    assert [n.text for n in inbox[RECRUITER]] == ["New application for Frontend Engineer"]
    assert [n.text for n in inbox["cand-1"]] == [
        "Your application for Frontend Engineer was received",
        "Your application for Frontend Engineer is now screening",
    ]
    assert len(portal.notifications.emails) == 2
    assert portal.dispatcher.position == len(portal.applications.outbox) == 2


def test_redelivered_events_are_processed_once():
    svc = NotificationService(lambda job: "employer", lambda job: "Engineer")
    event = OutboxEvent("e1", "ApplicationSubmitted", {"applicationId": "a", "jobId": "j", "candidate": "c"})
    assert svc.handle(event) is True
    assert svc.handle(event) is False  # at-least-once delivery from the outbox
    assert len(svc.inbox["c"]) == 1


def test_dispatcher_resumes_from_its_position():
    outbox: list[OutboxEvent] = []
    seen: list[str] = []
    d = OutboxDispatcher(outbox, [lambda e: seen.append(e.id) or True])
    outbox.append(OutboxEvent("1", "x", {}))
    assert d.dispatch() == 1
    outbox.append(OutboxEvent("2", "x", {}))
    assert d.dispatch() == 1 and d.dispatch() == 0
    assert seen == ["1", "2"]


def test_withdrawal_notifies_the_employer(portal):
    job = job_by_title(portal, "Frontend Engineer")
    app, _ = portal.apply("cand-1", job.id, None)
    portal.move("cand-1", app.id, Status.WITHDRAWN, expected_version=1)
    assert portal.notifications.inbox[RECRUITER][-1].text == "An applicant withdrew from Frontend Engineer"
