"""Inbound routing — first match wins (§6).

A pure function over the contact and its open tickets. No Firestore, no
network, no clock beyond what the caller passes in.
"""

from __future__ import annotations

from dataclasses import dataclass

from support_service.models import Contact, OpenTicket


@dataclass(frozen=True)
class ContinueSession:
    """Rule 1 — the message answers the step the contact is on."""


@dataclass(frozen=True)
class OfferReturningOptions:
    """Rule 2 — something is already open, so ask before starting another."""

    ticket: OpenTicket


@dataclass(frozen=True)
class StartReport:
    """Rule 3 — no context at all."""


Decision = ContinueSession | OfferReturningOptions | StartReport


def route(contact: Contact, open_tickets: list[OpenTicket]) -> Decision:
    """Decide what an inbound message means."""
    # 1. A running flow owns the next message, whatever it says.
    if contact.session is not None:
        return ContinueSession()

    # 2. Anything already open takes precedence over starting fresh. The
    #    newest one is the one the contact is most likely asking about.
    if open_tickets:
        return OfferReturningOptions(max(open_tickets, key=lambda t: t.created_at))

    # 3. Genuinely new.
    return StartReport()
