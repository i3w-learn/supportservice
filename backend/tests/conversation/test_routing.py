"""Routing table (§6). Unit tests — no emulator, no network."""

from datetime import UTC, datetime, timedelta

from support_service.conversation.routing import (
    ContinueSession,
    OfferReturningOptions,
    StartReport,
    route,
)
from support_service.models import Contact, Flow, OpenTicket, Session, Step, TicketStatus

NOW = datetime(2026, 9, 16, 12, 0, tzinfo=UTC)


def contact(**kwargs) -> Contact:
    return Contact(wa_number="918827450192", **kwargs)


def ticket(ticket_id: str, *, created_ago: timedelta = timedelta(0)) -> OpenTicket:
    return OpenTicket(
        ticket_id=ticket_id,
        category_id="device",
        category_label="Device",
        status=TicketStatus.OPEN,
        created_at=NOW - created_ago,
    )


def session(step: Step = Step.CATEGORY) -> Session:
    return Session(flow=Flow.REPORT, step=step, started_at=NOW, last_activity_at=NOW)


def test_session_beats_an_open_ticket() -> None:
    """Rule 1 outranks rule 2 — a mid-flow answer is not a fresh hello."""
    decision = route(contact(session=session(), open_ticket_ids=["TKT-1"]), [ticket("TKT-1")])

    assert decision == ContinueSession()


def test_an_open_ticket_offers_the_choice() -> None:
    decision = route(contact(open_ticket_ids=["TKT-1"]), [ticket("TKT-1")])

    assert decision == OfferReturningOptions(ticket("TKT-1"))


def test_the_newest_open_ticket_is_the_one_offered() -> None:
    older = ticket("TKT-1", created_ago=timedelta(days=3))
    newer = ticket("TKT-2", created_ago=timedelta(hours=2))

    decision = route(contact(open_ticket_ids=["TKT-1", "TKT-2"]), [older, newer])

    assert decision == OfferReturningOptions(newer)


def test_no_context_at_all_starts_a_report() -> None:
    assert route(contact(), []) == StartReport()
