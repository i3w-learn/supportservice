"""The report flow's step machine (§7).

Pure: one turn in, replies and a new session out. Nothing here writes to
Firestore or calls Gupshup — the caller does that. The machine never holds
state in memory between messages, because Cloud Run kills idle containers.

Every prompt is an approved WhatsApp template. The only free text is the nudge
after an unrecognised tap, and the regional-language list.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from support_service.config import defaults
from support_service.config.models import ConfigSnapshot
from support_service.models import (
    Contact,
    Flow,
    InboundMessage,
    Language,
    OpenTicket,
    Session,
    Step,
)


@dataclass(frozen=True)
class Row:
    id: str
    label: str


@dataclass(frozen=True)
class SendText:
    body: str


@dataclass(frozen=True)
class SendList:
    body: str
    rows: tuple[Row, ...]


@dataclass(frozen=True)
class SendTemplate:
    """An approved template. `params` fill {{1}}, {{2}}… in order."""

    name: str
    language: Language
    params: tuple[str, ...] = ()


Reply = SendText | SendList | SendTemplate


@dataclass(frozen=True)
class Draft:
    """Everything gathered, ready for the ticket-creation transaction."""

    language: Language
    category_id: str
    description: str = ""


@dataclass(frozen=True)
class Turn:
    """The result of one inbound message."""

    replies: tuple[Reply, ...] = ()
    session: Session | None = None
    """Set only on the final step — the caller then runs the transaction."""
    create: Draft | None = None
    learned_language: Language | None = None


def begin(contact: Contact, config: ConfigSnapshot, *, now: datetime) -> Turn:
    """Open the report flow. Skips language once the contact has one."""
    if contact.language is None:
        return Turn(
            replies=(SendTemplate(defaults.WELCOME_LANGUAGE, Language.EN),),
            session=_session(Step.LANGUAGE, {}, now),
        )
    return _ask_category(contact.language, now=now, draft={"language": contact.language.value})


def offer_returning(ticket: OpenTicket, language: Language, *, now: datetime) -> Turn:
    """A contact with an open ticket chooses: a new one, or that one's status."""
    draft = {
        "language": language.value,
        "ticket_id": ticket.ticket_id,
        "category_label": ticket.category_label,
        "status": ticket.status.value,
        "raised_on": ticket.created_at.strftime("%d %b %Y"),
    }
    return Turn(
        replies=(SendTemplate(defaults.RETURNING_OPTIONS, language, (ticket.ticket_id,)),),
        session=_session(Step.RETURNING, draft, now),
    )


def advance(
    contact: Contact,
    message: InboundMessage,
    config: ConfigSnapshot,
    *,
    now: datetime,
) -> Turn:
    """Apply one message to the contact's current step."""
    session = contact.session
    if session is None:
        return begin(contact, config, now=now)

    draft = dict(session.draft)
    language = _draft_language(draft, contact)

    handlers = {
        Step.LANGUAGE: _on_language,
        Step.RETURNING: _on_returning,
        Step.CATEGORY: _on_category,
        Step.MEDIA: _on_media,
    }
    return handlers[session.step](contact, message, config, draft, language, now)


# --- steps ---------------------------------------------------------------


def _on_language(
    contact: Contact,
    message: InboundMessage,
    config: ConfigSnapshot,
    draft: dict[str, str],
    language: Language,
    now: datetime,
) -> Turn:
    regional = [
        (lang.value, defaults.LANGUAGE_LABELS[lang]) for lang in defaults.REGIONAL_LANGUAGES
    ]
    chosen = _pick(message, [*defaults.LANGUAGE_BUTTONS, *regional])

    if chosen == defaults.REGIONAL:
        rows = tuple(Row(value, label) for value, label in regional)
        return Turn(
            replies=(SendList(config.text("ask_regional", language), rows),),
            session=_session(Step.LANGUAGE, draft, now),
        )
    if chosen is None:
        return _retry(_welcome(now), config, language)

    picked = Language(chosen)
    draft["language"] = picked.value
    prompt = _ask_category(picked, now=now, draft=draft)
    return Turn(replies=prompt.replies, session=prompt.session, learned_language=picked)


def _on_returning(
    contact: Contact,
    message: InboundMessage,
    config: ConfigSnapshot,
    draft: dict[str, str],
    language: Language,
    now: datetime,
) -> Turn:
    chosen = _pick(
        message,
        [
            (defaults.NEW_TICKET, config.text("new_ticket_button", language)),
            (defaults.PREVIOUS_TICKET, config.text("previous_ticket_button", language)),
        ],
    )

    if chosen == defaults.NEW_TICKET:
        return _ask_category(language, now=now, draft={"language": language.value})

    if chosen == defaults.PREVIOUS_TICKET:
        status = config.text(f"status_{draft.get('status', '')}", language)
        params = (
            draft.get("ticket_id", ""),
            draft.get("category_label", ""),
            status,
            draft.get("raised_on", ""),
        )
        # The status answers the question, so the flow ends here.
        return Turn(replies=(SendTemplate(defaults.TICKET_STATUS, language, params),))

    return _retry(_offer_again(draft, language, now), config, language)


def _on_category(
    contact: Contact,
    message: InboundMessage,
    config: ConfigSnapshot,
    draft: dict[str, str],
    language: Language,
    now: datetime,
) -> Turn:
    options = [
        (category.id, config.category_label(category.id, language))
        for category in config.enabled_categories()
    ]
    chosen = _pick(message, options)
    if chosen is None:
        return _retry(_ask_category(language, now=now, draft=draft), config, language)

    draft["category_id"] = chosen
    label = config.category_label(chosen, language)
    return Turn(
        replies=(SendTemplate(defaults.UPLOAD_MEDIA, language, (label,)),),
        session=_session(Step.MEDIA, draft, now),
    )


def _on_media(
    contact: Contact,
    message: InboundMessage,
    config: ConfigSnapshot,
    draft: dict[str, str],
    language: Language,
    now: datetime,
) -> Turn:
    """A photo or Skip files the ticket. Typed text becomes its description."""
    chosen = _pick(
        message,
        [
            (defaults.UPLOAD_NOW, config.text("upload_button", language)),
            (defaults.SKIP, config.text("skip_button", language)),
        ],
    )

    if chosen == defaults.SKIP:
        return Turn(create=_to_draft(draft))

    if message.attachment is not None:
        draft["has_media"] = "yes"
        return Turn(create=_to_draft(draft))

    # "Upload Now" is a nudge, not an answer — wait for the file itself.
    if chosen is None and message.text:
        existing = draft.get("description", "")
        draft["description"] = f"{existing}\n{message.text}".strip() if existing else message.text

    return Turn(session=_session(Step.MEDIA, draft, now))


def finish_idle(session: Session) -> Draft | None:
    """File a report left waiting at the media step past the idle window.

    Called by a delayed Cloud Task, not by a message. Cloud Run freezes the
    CPU between requests, so a timer inside the process would never fire.
    """
    if session.step is not Step.MEDIA:
        return None
    if not session.draft.get("category_id"):
        return None
    return _to_draft(session.draft)


# --- prompts -------------------------------------------------------------


def _welcome(now: datetime) -> Turn:
    return Turn(
        replies=(SendTemplate(defaults.WELCOME_LANGUAGE, Language.EN),),
        session=_session(Step.LANGUAGE, {}, now),
    )


def _offer_again(draft: dict[str, str], language: Language, now: datetime) -> Turn:
    return Turn(
        replies=(
            SendTemplate(defaults.RETURNING_OPTIONS, language, (draft.get("ticket_id", ""),)),
        ),
        session=_session(Step.RETURNING, draft, now),
    )


def _ask_category(language: Language, *, now: datetime, draft: dict[str, str]) -> Turn:
    return Turn(
        replies=(SendTemplate(defaults.ISSUE_CATEGORY, language),),
        session=_session(Step.CATEGORY, draft, now),
    )


# --- helpers -------------------------------------------------------------


def _session(step: Step, draft: dict[str, str], now: datetime) -> Session:
    return Session(flow=Flow.REPORT, step=step, draft=draft, started_at=now, last_activity_at=now)


def _pick(message: InboundMessage, options: list[tuple[str, str]]) -> str | None:
    """Work out which button was tapped.

    A template's quick reply comes back as the button's own text, with the
    button index as its id — neither is an id we chose. Rows in lists we send
    ourselves do carry our id, so all three are accepted.
    """
    typed = (message.text or "").strip().casefold()
    for option_id, label in options:
        if message.reply_id == option_id:
            return option_id
        if typed and typed == label.strip().casefold():
            return option_id

    if message.reply_id and message.reply_id.isdigit():
        index = int(message.reply_id)
        if 0 <= index < len(options):
            return options[index][0]
    if typed.isdigit():
        index = int(typed) - 1
        if 0 <= index < len(options):
            return options[index][0]
    return None


def _retry(prompt: Turn, config: ConfigSnapshot, language: Language) -> Turn:
    """Re-send the same prompt with a nudge in front of it."""
    return Turn(
        replies=(SendText(config.text("invalid_choice", language)), *prompt.replies),
        session=prompt.session,
    )


def _draft_language(draft: dict[str, str], contact: Contact) -> Language:
    raw = draft.get("language")
    if raw:
        return Language(raw)
    return contact.language or Language.EN


def _to_draft(draft: dict[str, str]) -> Draft:
    return Draft(
        language=Language(draft.get("language", Language.EN.value)),
        category_id=draft["category_id"],
        description=draft.get("description", ""),
    )


__all__ = [
    "Draft",
    "Reply",
    "Row",
    "SendList",
    "SendTemplate",
    "SendText",
    "Turn",
    "advance",
    "begin",
    "finish_idle",
    "offer_returning",
]
