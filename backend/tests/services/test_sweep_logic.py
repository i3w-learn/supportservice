"""Hourly sweep — unit tests, no emulator, no network.

Firestore (`get_db`) is monkeypatched at the point `sweep.py` imports it, same
convention as media/test_urls.py and admin_api/test_routes.py. Cutoffs are
computed from the real clock (via `config.defaults.seed()`'s default
`Settings`) rather than freezing time, so these tests exercise the real
comparison logic instead of a mocked one.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

import pytest

from support_service.config.defaults import seed
from support_service.services import sweep_service as sweep_module
from support_service.services.sweep_service import run_sweep

SETTINGS = seed().settings


def _doc(data: dict[str, object]) -> MagicMock:
    doc = MagicMock()
    doc.to_dict.return_value = data
    return doc


@pytest.fixture
def mock_db(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    db = MagicMock()
    monkeypatch.setattr(sweep_module, "get_db", lambda: db)
    return db


def _tickets_query(mock_db: MagicMock) -> MagicMock:
    return mock_db.collection.return_value.where.return_value.where.return_value.limit.return_value


def _contacts_query(mock_db: MagicMock) -> MagicMock:
    return mock_db.collection.return_value.where.return_value.limit.return_value


class TestFlagSla:
    def test_ticket_past_breach_cutoff_is_flagged_breached(self, mock_db: MagicMock) -> None:
        created = datetime.now(UTC) - timedelta(hours=SETTINGS.sla_breach_hours + 1)
        ticket = _doc({"createdAt": created, "slaState": "ok"})
        _tickets_query(mock_db).get.return_value = [ticket]

        count = sweep_module._flag_sla()

        assert count == 1
        ticket.reference.update.assert_called_once()
        (updates,) = ticket.reference.update.call_args.args
        assert updates["slaState"] == "breached"
        ticket.reference.collection.assert_called_once_with("events")
        event_ref = ticket.reference.collection.return_value.document.return_value
        event_ref.set.assert_called_once()
        (event,) = event_ref.set.call_args.args
        assert event["type"] == "sla_flagged"
        assert event["to"] == "breached"
        assert event["from"] == "ok"

    def test_ticket_past_reminder_cutoff_is_flagged_reminder_due(self, mock_db: MagicMock) -> None:
        created = datetime.now(UTC) - timedelta(hours=SETTINGS.sla_reminder_hours + 1)
        ticket = _doc({"createdAt": created, "slaState": "ok"})
        _tickets_query(mock_db).get.return_value = [ticket]

        count = sweep_module._flag_sla()

        assert count == 1
        (updates,) = ticket.reference.update.call_args.args
        assert updates["slaState"] == "reminder_due"

    def test_ticket_within_reminder_window_is_untouched(self, mock_db: MagicMock) -> None:
        created = datetime.now(UTC) - timedelta(hours=1)
        ticket = _doc({"createdAt": created, "slaState": "ok"})
        _tickets_query(mock_db).get.return_value = [ticket]

        count = sweep_module._flag_sla()

        assert count == 0
        ticket.reference.update.assert_not_called()

    def test_already_reminder_due_is_not_reflagged(self, mock_db: MagicMock) -> None:
        created = datetime.now(UTC) - timedelta(hours=SETTINGS.sla_reminder_hours + 1)
        ticket = _doc({"createdAt": created, "slaState": "reminder_due"})
        _tickets_query(mock_db).get.return_value = [ticket]

        count = sweep_module._flag_sla()

        assert count == 0
        ticket.reference.update.assert_not_called()

    def test_ticket_missing_created_at_is_skipped(self, mock_db: MagicMock) -> None:
        ticket = _doc({"slaState": "ok"})
        _tickets_query(mock_db).get.return_value = [ticket]

        count = sweep_module._flag_sla()

        assert count == 0
        ticket.reference.update.assert_not_called()


class TestClearExpiredSessions:
    def test_expired_session_is_cleared(self, mock_db: MagicMock) -> None:
        contact = _doc({"session": {"step": "description"}})
        _contacts_query(mock_db).get.return_value = [contact]

        count = sweep_module._clear_expired_sessions()

        assert count == 1
        contact.reference.update.assert_called_once()
        (updates,) = contact.reference.update.call_args.args
        assert updates["session"] is None

    def test_already_cleared_session_is_not_recounted(self, mock_db: MagicMock) -> None:
        contact = _doc({"session": None})
        _contacts_query(mock_db).get.return_value = [contact]

        count = sweep_module._clear_expired_sessions()

        assert count == 0
        contact.reference.update.assert_not_called()

    def test_mixed_batch_only_counts_active_sessions(self, mock_db: MagicMock) -> None:
        active = _doc({"session": {"step": "name"}})
        cleared = _doc({"session": None})
        _contacts_query(mock_db).get.return_value = [active, cleared]

        count = sweep_module._clear_expired_sessions()

        assert count == 1
        active.reference.update.assert_called_once()
        cleared.reference.update.assert_not_called()


class TestPruneRecentlyClosed:
    def test_stale_entries_are_pruned(self, mock_db: MagicMock) -> None:
        stale = {
            "ticketId": "TKT-1",
            "serviceId": "svc",
            "closedAt": datetime.now(UTC) - timedelta(days=10),
        }
        fresh = {
            "ticketId": "TKT-2",
            "serviceId": "svc",
            "closedAt": datetime.now(UTC) - timedelta(days=2),
        }
        contact = _doc({"recentlyClosed": [stale, fresh]})
        _contacts_query(mock_db).get.return_value = [contact]

        count = sweep_module._prune_recently_closed()

        assert count == 1
        contact.reference.update.assert_called_once()
        (updates,) = contact.reference.update.call_args.args
        assert updates["recentlyClosed"] == [fresh]

    def test_all_fresh_entries_leaves_contact_untouched(self, mock_db: MagicMock) -> None:
        fresh = {
            "ticketId": "TKT-2",
            "serviceId": "svc",
            "closedAt": datetime.now(UTC) - timedelta(days=1),
        }
        contact = _doc({"recentlyClosed": [fresh]})
        _contacts_query(mock_db).get.return_value = [contact]

        count = sweep_module._prune_recently_closed()

        assert count == 0
        contact.reference.update.assert_not_called()


class TestRunSweep:
    def test_aggregates_all_three_passes(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(sweep_module, "_flag_sla", lambda: 3)
        monkeypatch.setattr(sweep_module, "_clear_expired_sessions", lambda: 2)
        monkeypatch.setattr(sweep_module, "_prune_recently_closed", lambda: 1)

        result = run_sweep()

        assert result == {
            "sla_flagged": 3,
            "sessions_expired": 2,
            "recently_closed_pruned": 1,
        }
