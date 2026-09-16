"""The step machine (§7). Unit tests — pure functions, no Firestore, no network.

Every prompt is an approved template, so the assertions are about which
template goes out with which values — not about wording, which lives in
Gupshup.
"""

from datetime import UTC, datetime

import pytest

from support_service.config import defaults
from support_service.config.defaults import seed
from support_service.conversation.steps import (
    Draft,
    SendList,
    SendTemplate,
    SendText,
    advance,
    begin,
    finish_idle,
    offer_returning,
)
from support_service.models import (
    Attachment,
    Contact,
    Flow,
    InboundMessage,
    Language,
    MessageType,
    OpenTicket,
    Session,
    Step,
    TicketStatus,
)

NOW = datetime(2026, 9, 16, 12, 0, tzinfo=UTC)
CONFIG = seed()
WA = "918827450192"


def tap(title: str, button_index: str | None = None) -> InboundMessage:
    """A template's quick reply: the button's text, with its index as the id."""
    return InboundMessage(
        provider_message_id="wamid.x",
        wa_number=WA,
        type=MessageType.INTERACTIVE,
        text=title,
        reply_id=button_index,
        received_at=NOW,
    )


def row(row_id: str) -> InboundMessage:
    """A row in a list we sent ourselves — those carry our own id."""
    return InboundMessage(
        provider_message_id="wamid.x",
        wa_number=WA,
        type=MessageType.INTERACTIVE,
        reply_id=row_id,
        received_at=NOW,
    )


def say(body: str) -> InboundMessage:
    return InboundMessage(
        provider_message_id="wamid.x",
        wa_number=WA,
        type=MessageType.TEXT,
        text=body,
        received_at=NOW,
    )


def photo() -> InboundMessage:
    return InboundMessage(
        provider_message_id="wamid.x",
        wa_number=WA,
        type=MessageType.IMAGE,
        attachment=Attachment(),
        received_at=NOW,
    )


def at(step: Step, **draft: str) -> Contact:
    language = Language(draft["language"]) if "language" in draft else None
    return Contact(
        wa_number=WA,
        language=language,
        session=Session(
            flow=Flow.REPORT, step=step, draft=draft, started_at=NOW, last_activity_at=NOW
        ),
    )


def only_template(turn) -> SendTemplate:
    template = turn.replies[-1]
    assert isinstance(template, SendTemplate)
    return template


class TestOpening:
    def test_new_contact_is_asked_for_a_language(self) -> None:
        turn = begin(Contact(wa_number=WA), CONFIG, now=NOW)

        assert only_template(turn).name == defaults.WELCOME_LANGUAGE
        # We don't know their language yet, so the first message is English.
        assert only_template(turn).language is Language.EN
        assert turn.session is not None
        assert turn.session.step is Step.LANGUAGE

    def test_known_language_skips_straight_to_the_categories(self) -> None:
        turn = begin(Contact(wa_number=WA, language=Language.MR), CONFIG, now=NOW)

        assert only_template(turn).name == defaults.ISSUE_CATEGORY
        assert only_template(turn).language is Language.MR
        assert turn.session is not None
        assert turn.session.step is Step.CATEGORY


class TestLanguageStep:
    @pytest.mark.parametrize(
        ("title", "expected"),
        [("English", Language.EN), ("हिन्दी", Language.HI)],
    )
    def test_a_language_button_is_learned(self, title: str, expected: Language) -> None:
        turn = advance(at(Step.LANGUAGE), tap(title), CONFIG, now=NOW)

        assert turn.learned_language is expected
        assert only_template(turn).name == defaults.ISSUE_CATEGORY
        assert only_template(turn).language is expected

    def test_the_button_index_works_when_the_text_does_not_come_back(self) -> None:
        turn = advance(at(Step.LANGUAGE), tap("", button_index="1"), CONFIG, now=NOW)

        assert turn.learned_language is Language.HI

    def test_regional_offers_the_remaining_languages_as_a_list(self) -> None:
        turn = advance(at(Step.LANGUAGE), tap("Regional"), CONFIG, now=NOW)

        reply = turn.replies[0]
        assert isinstance(reply, SendList)
        assert [r.id for r in reply.rows] == ["mr", "bn"]
        assert turn.session is not None
        assert turn.session.step is Step.LANGUAGE, "still waiting for a language"
        assert turn.learned_language is None

    def test_picking_from_that_list_is_learned(self) -> None:
        turn = advance(at(Step.LANGUAGE), row("bn"), CONFIG, now=NOW)

        assert turn.learned_language is Language.BN
        assert only_template(turn).language is Language.BN

    def test_anything_else_nudges_and_asks_again(self) -> None:
        turn = advance(at(Step.LANGUAGE), say("what?"), CONFIG, now=NOW)

        assert isinstance(turn.replies[0], SendText)
        assert only_template(turn).name == defaults.WELCOME_LANGUAGE
        assert turn.learned_language is None


class TestCategoryStep:
    def test_a_category_button_moves_on_to_the_photo(self) -> None:
        turn = advance(at(Step.CATEGORY, language="en"), tap("Software"), CONFIG, now=NOW)

        template = only_template(turn)
        assert template.name == defaults.UPLOAD_MEDIA
        assert template.params == ("Software",), "the template repeats the choice back"
        assert turn.session is not None
        assert turn.session.step is Step.MEDIA
        assert turn.session.draft["category_id"] == "software"

    def test_the_label_is_matched_in_the_contact_s_own_language(self) -> None:
        turn = advance(at(Step.CATEGORY, language="bn"), tap("ডিভাইস"), CONFIG, now=NOW)

        assert turn.session is not None
        assert turn.session.draft["category_id"] == "device"
        assert only_template(turn).params == ("ডিভাইস",)

    def test_an_unknown_answer_nudges_and_asks_again(self) -> None:
        turn = advance(at(Step.CATEGORY, language="en"), say("my headset broke"), CONFIG, now=NOW)

        assert isinstance(turn.replies[0], SendText)
        assert only_template(turn).name == defaults.ISSUE_CATEGORY
        assert turn.session is not None
        assert turn.session.step is Step.CATEGORY


class TestMediaStep:
    def base(self) -> Contact:
        return at(Step.MEDIA, language="en", category_id="device")

    def test_a_photo_files_the_report(self) -> None:
        turn = advance(self.base(), photo(), CONFIG, now=NOW)

        assert turn.create == Draft(language=Language.EN, category_id="device", description="")
        assert turn.session is None

    def test_skip_files_the_report_too(self) -> None:
        turn = advance(self.base(), tap("Skip"), CONFIG, now=NOW)

        assert turn.create is not None
        assert turn.session is None

    def test_upload_now_just_waits(self) -> None:
        turn = advance(self.base(), tap("Upload Now"), CONFIG, now=NOW)

        assert turn.create is None
        assert turn.replies == (), "the nudge is the template that was already sent"
        assert turn.session is not None
        assert turn.session.step is Step.MEDIA

    def test_typed_text_becomes_the_description(self) -> None:
        contact = self.base()
        turn = advance(contact, say("headset dead"), CONFIG, now=NOW)
        contact = contact.model_copy(update={"session": turn.session})
        turn = advance(contact, say("red light stays on"), CONFIG, now=NOW)

        assert turn.session is not None
        assert turn.session.draft["description"] == "headset dead\nred light stays on"

    def test_a_photo_after_text_keeps_the_description(self) -> None:
        contact = self.base()
        turn = advance(contact, say("headset dead"), CONFIG, now=NOW)
        contact = contact.model_copy(update={"session": turn.session})
        turn = advance(contact, photo(), CONFIG, now=NOW)

        assert turn.create is not None
        assert turn.create.description == "headset dead"


class TestReturningContacts:
    def ticket(self) -> OpenTicket:
        return OpenTicket(
            ticket_id="TKT-20260916-0042",
            category_id="software",
            category_label="Software",
            status=TicketStatus.IN_PROGRESS,
            created_at=datetime(2026, 9, 14, 8, 0, tzinfo=UTC),
        )

    def test_the_open_ticket_is_offered_with_its_id(self) -> None:
        turn = offer_returning(self.ticket(), Language.EN, now=NOW)

        template = only_template(turn)
        assert template.name == defaults.RETURNING_OPTIONS
        assert template.params == ("TKT-20260916-0042",)
        assert turn.session is not None
        assert turn.session.step is Step.RETURNING

    def test_new_ticket_starts_the_categories_again(self) -> None:
        session = offer_returning(self.ticket(), Language.EN, now=NOW).session
        contact = Contact(wa_number=WA, language=Language.EN, session=session)

        turn = advance(contact, tap("New Ticket"), CONFIG, now=NOW)

        assert only_template(turn).name == defaults.ISSUE_CATEGORY
        assert turn.session is not None
        assert turn.session.step is Step.CATEGORY
        assert "ticket_id" not in turn.session.draft, (
            "the old ticket must not leak into the new one"
        )

    def test_previous_ticket_answers_with_its_status_and_ends(self) -> None:
        session = offer_returning(self.ticket(), Language.EN, now=NOW).session
        contact = Contact(wa_number=WA, language=Language.EN, session=session)

        turn = advance(contact, tap("Previous Ticket"), CONFIG, now=NOW)

        template = only_template(turn)
        assert template.name == defaults.TICKET_STATUS
        assert template.params == ("TKT-20260916-0042", "Software", "In Progress", "14 Sep 2026")
        assert turn.session is None, "the question is answered, so the flow is over"

    def test_the_status_is_written_in_the_contact_s_language(self) -> None:
        session = offer_returning(self.ticket(), Language.HI, now=NOW).session
        contact = Contact(wa_number=WA, language=Language.HI, session=session)

        turn = advance(contact, tap("पिछला टिकट"), CONFIG, now=NOW)

        assert only_template(turn).params[2] == "काम जारी है"

    def test_anything_else_nudges_and_offers_again(self) -> None:
        session = offer_returning(self.ticket(), Language.EN, now=NOW).session
        contact = Contact(wa_number=WA, language=Language.EN, session=session)

        turn = advance(contact, say("hello?"), CONFIG, now=NOW)

        assert isinstance(turn.replies[0], SendText)
        assert only_template(turn).name == defaults.RETURNING_OPTIONS
        assert turn.session is not None
        assert turn.session.step is Step.RETURNING


class TestIdleRescue:
    """Cloud Run has no timers between requests, so a delayed Cloud Task finishes these."""

    def session(self, step: Step = Step.MEDIA, **draft: str) -> Session:
        return Session(
            flow=Flow.REPORT, step=step, draft=draft, started_at=NOW, last_activity_at=NOW
        )

    def test_a_category_is_enough_to_file_the_report(self) -> None:
        """They chose a category and then went quiet — that is still a report."""
        draft = finish_idle(self.session(language="hi", category_id="device"))

        assert draft == Draft(language=Language.HI, category_id="device", description="")

    def test_a_typed_description_is_kept(self) -> None:
        draft = finish_idle(
            self.session(language="en", category_id="other", description="door broken")
        )

        assert draft is not None
        assert draft.description == "door broken"

    def test_an_earlier_step_is_not_rescued(self) -> None:
        assert finish_idle(self.session(step=Step.CATEGORY, language="en")) is None

    def test_no_category_means_nothing_to_file(self) -> None:
        assert finish_idle(self.session(language="en")) is None
