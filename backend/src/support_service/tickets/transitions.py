"""Status transition table (§8). Anything not listed here is a 409."""

from support_service.models import TicketStatus

LEGAL: dict[TicketStatus, list[TicketStatus]] = {
    TicketStatus.OPEN: [TicketStatus.IN_PROGRESS, TicketStatus.RESOLVED],
    TicketStatus.IN_PROGRESS: [TicketStatus.OPEN, TicketStatus.RESOLVED],
    TicketStatus.RESOLVED: [TicketStatus.CLOSED, TicketStatus.IN_PROGRESS],
    TicketStatus.CLOSED: [TicketStatus.OPEN],
}


def validate_transition(from_status: TicketStatus, to_status: TicketStatus) -> None:
    if to_status not in LEGAL.get(from_status, []):
        raise ValueError(f"{from_status} → {to_status} is not a legal transition")
