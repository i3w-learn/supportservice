import pytest

from support_service.models import TicketStatus
from support_service.tickets.transitions import validate_transition


class TestLegalTransitions:
    @pytest.mark.parametrize(
        "from_status,to_status",
        [
            ("open", "in_progress"),
            ("open", "resolved"),
            ("in_progress", "open"),
            ("in_progress", "resolved"),
            ("resolved", "closed"),
            ("resolved", "in_progress"),
            ("closed", "open"),
        ],
    )
    def test_legal_transitions_pass(self, from_status: str, to_status: str) -> None:
        validate_transition(TicketStatus(from_status), TicketStatus(to_status))

    @pytest.mark.parametrize(
        "from_status,to_status",
        [
            ("open", "closed"),
            ("open", "open"),
            ("in_progress", "closed"),
            ("in_progress", "in_progress"),
            ("resolved", "open"),
            ("resolved", "resolved"),
            ("closed", "closed"),
            ("closed", "in_progress"),
            ("closed", "resolved"),
        ],
    )
    def test_illegal_transitions_raise(self, from_status: str, to_status: str) -> None:
        with pytest.raises(ValueError):
            validate_transition(TicketStatus(from_status), TicketStatus(to_status))
