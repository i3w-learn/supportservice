"""Routing table (§6). Unit tests — no emulator, no network."""

from datetime import UTC, datetime, timedelta

import pytest

from support_service.conversation.routing import (
    AppendToTicket,
    AskAboutRecentlyClosed,
    ContinueSession,
    Disambiguate,
    ReopenTicket,
    StartReport,
    route,
)
from support_service.models import (
    ClosedTicketRef,
    Contact,
    Flow,
    InboundMessage,
    MessageType,
    OpenTicket,
    Session,
    Step,
)

NOW = datetime(2026, 9, 9, 12, 0, tzinfo=UTC)


def contact(**kwargs) -> Contact:
    return Contact(wa_number="918827450192", **kwargs)


def text(body: str = "hello", **kwargs) -> InboundMessage:
    return InboundMessage(
        provider_message_id="wamid.1",
        wa_number="918827450192",
        type=MessageType.TEXT,
        text=body,
        received_at=NOW,
        **kwargs,
    )


def ticket(ticket_id: str, service_id: str = "anganwadi-vr") -> OpenTicket:
    return OpenTicket(ticket_id=ticket_id, service_id=service_id, service_name="Anganwadi VR")


def closed(ticket_id: str, *, days_ago: float) -> ClosedTicketRef:
    return ClosedTicketRef(
        ticket_id=ticket_id,
        service_id="anganwadi-vr",
        closed_at=NOW - timedelta(days=days_ago),
    )


def session(step: Step = Step.NAME) -> Session:
    return Session(flow=Flow.REPORT, step=step, started_at=NOW, last_activity_at=NOW)


class TestFirstMatchWins:
    def test_reply_context_beats_an_active_session(self) -> None:
        """Rule 1 outranks rule 2 — an explicit reply is never a step answer."""
        decision = route(
            contact(session=session(), open_ticket_ids=["TKT-1"]),
            text(context_message_id="out-1"),
            [ticket("TKT-1")],
            now=NOW,
            ticket_id_for_outbound={"out-1": "TKT-1"},
        )
        assert decision == AppendToTicket("TKT-1")

    def test_session_beats_an_open_ticket(self) -> None:
        """Rule 2 outranks rule 3 — mid-flow answers must not be filed as chatter."""
        decision = route(
            contact(session=session(), open_ticket_ids=["TKT-1"]),
            text("Sunita Devi"),
            [ticket("TKT-1")],
            now=NOW,
        )
        assert decision == ContinueSession()

    def test_recently_closed_beats_starting_a_new_report(self) -> None:
        """Rule 5 must sit above rule 6, or every follow-up becomes a duplicate."""
        decision = route(
            contact(recently_closed=[closed("TKT-9", days_ago=3)]),
            text("still not working"),
            [],
            now=NOW,
        )
        assert decision == AskAboutRecentlyClosed(closed("TKT-9", days_ago=3))


class TestOpenTickets:
    def test_one_open_ticket_appends(self) -> None:
        decision = route(contact(), text(), [ticket("TKT-1")], now=NOW)
        assert decision == AppendToTicket("TKT-1")

    def test_two_open_tickets_disambiguate(self) -> None:
        options = [ticket("TKT-1"), ticket("TKT-2", "poshan-ai")]
        decision = route(contact(), text(), options, now=NOW)
        assert decision == Disambiguate(tuple(options))

    def test_no_context_at_all_starts_a_report(self) -> None:
        assert route(contact(), text(), [], now=NOW) == StartReport()


class TestReopenWindow:
    def test_reply_to_a_ticket_closed_yesterday_reopens_it(self) -> None:
        decision = route(
            contact(recently_closed=[closed("TKT-9", days_ago=1)]),
            text(context_message_id="out-9"),
            [],
            now=NOW,
            ticket_id_for_outbound={"out-9": "TKT-9"},
            closed_ticket_ids=frozenset({"TKT-9"}),
        )
        assert decision == ReopenTicket("TKT-9")

    def test_reply_to_a_ticket_closed_long_ago_starts_fresh(self) -> None:
        decision = route(
            contact(recently_closed=[closed("TKT-9", days_ago=30)]),
            text(context_message_id="out-9"),
            [],
            now=NOW,
            ticket_id_for_outbound={"out-9": "TKT-9"},
            closed_ticket_ids=frozenset({"TKT-9"}),
        )
        assert decision == StartReport()

    @pytest.mark.parametrize("days_ago", [0.1, 3.0, 6.9])
    def test_inside_seven_days_asks(self, days_ago: float) -> None:
        decision = route(
            contact(recently_closed=[closed("TKT-9", days_ago=days_ago)]),
            text(),
            [],
            now=NOW,
        )
        assert isinstance(decision, AskAboutRecentlyClosed)

    @pytest.mark.parametrize("days_ago", [7.1, 30.0])
    def test_outside_seven_days_starts_a_report(self, days_ago: float) -> None:
        decision = route(
            contact(recently_closed=[closed("TKT-9", days_ago=days_ago)]),
            text(),
            [],
            now=NOW,
        )
        assert decision == StartReport()

    def test_picks_the_most_recent_close(self) -> None:
        decision = route(
            contact(recently_closed=[closed("TKT-8", days_ago=5), closed("TKT-9", days_ago=1)]),
            text(),
            [],
            now=NOW,
        )
        assert decision == AskAboutRecentlyClosed(closed("TKT-9", days_ago=1))


class TestUnknownReplyContext:
    def test_reply_to_something_we_do_not_know_falls_through(self) -> None:
        """A stale reply must not crash or invent a ticket."""
        decision = route(
            contact(),
            text(context_message_id="out-unknown"),
            [],
            now=NOW,
            ticket_id_for_outbound={"out-1": "TKT-1"},
        )
        assert decision == StartReport()
