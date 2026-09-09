"""Inbound routing — first match wins (§6).

A pure function over the contact and the message. No Firestore, no network,
no clock beyond what the caller passes in. Everything this module decides is
reproducible from its arguments, which is why it can be tested offline.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from support_service.models import ClosedTicketRef, Contact, InboundMessage, OpenTicket

REOPEN_WINDOW = timedelta(days=7)


@dataclass(frozen=True)
class ContinueSession:
    """Rule 2 — the message answers the step the contact is on."""


@dataclass(frozen=True)
class AppendToTicket:
    """Rules 1 and 3 — the message belongs to a ticket that is already open."""

    ticket_id: str


@dataclass(frozen=True)
class ReopenTicket:
    """Rule 1 — reply-context pointed at a ticket closed inside 7 days."""

    ticket_id: str


@dataclass(frozen=True)
class Disambiguate:
    """Rule 4 — several tickets open, ask which one by product name."""

    options: tuple[OpenTicket, ...]


@dataclass(frozen=True)
class AskAboutRecentlyClosed:
    """Rule 5 — nothing open, but something closed recently. Ask, never assume."""

    closed: ClosedTicketRef


@dataclass(frozen=True)
class StartReport:
    """Rule 6 — no context at all."""


Decision = (
    ContinueSession
    | AppendToTicket
    | ReopenTicket
    | Disambiguate
    | AskAboutRecentlyClosed
    | StartReport
)


def route(
    contact: Contact,
    message: InboundMessage,
    open_tickets: list[OpenTicket],
    *,
    now: datetime,
    ticket_id_for_outbound: dict[str, str] | None = None,
    closed_ticket_ids: frozenset[str] = frozenset(),
) -> Decision:
    """Decide what an inbound message means.

    `ticket_id_for_outbound` maps our own outbound message ids to their ticket,
    so a reply-swipe can be resolved without the caller loading every message.
    `closed_ticket_ids` lets rule 1 tell a closed ticket from an open one.
    """
    # 1. Reply-context to one of our messages wins over everything, because the
    #    contact told us explicitly which conversation they meant.
    if message.context_message_id and ticket_id_for_outbound:
        ticket_id = ticket_id_for_outbound.get(message.context_message_id)
        if ticket_id:
            if ticket_id in closed_ticket_ids:
                closed = _find_recently_closed(contact, now, ticket_id=ticket_id)
                return ReopenTicket(ticket_id) if closed else StartReport()
            return AppendToTicket(ticket_id)

    # 2. A running flow owns the next message, whatever it says.
    if contact.session is not None:
        return ContinueSession()

    # 3 and 4. Anything already open takes precedence over starting fresh.
    if len(open_tickets) == 1:
        return AppendToTicket(open_tickets[0].ticket_id)
    if len(open_tickets) > 1:
        return Disambiguate(tuple(open_tickets))

    # 5. Nothing open — but a recent close is probably a follow-up. Ask.
    #    This rule must sit above rule 6: closing removes the ticket from
    #    openTicketIds, so without it every follow-up starts a duplicate.
    closed = _find_recently_closed(contact, now)
    if closed is not None:
        return AskAboutRecentlyClosed(closed)

    # 6. Genuinely new.
    return StartReport()


def _find_recently_closed(
    contact: Contact, now: datetime, *, ticket_id: str | None = None
) -> ClosedTicketRef | None:
    """Most recently closed ticket still inside the reopen window."""
    candidates = [
        entry
        for entry in contact.recently_closed
        if now - entry.closed_at <= REOPEN_WINDOW
        and (ticket_id is None or entry.ticket_id == ticket_id)
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda entry: entry.closed_at)
