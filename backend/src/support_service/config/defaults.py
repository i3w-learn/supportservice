"""Seed copy, categories and the approved template names.

Every prompt the bot sends is one of the WhatsApp templates below (the wording
lives in Gupshup, not here — see whatsapp-templates.md). The strings in COPY
are only for the handful of messages that are not templates: the nudge after an
unrecognised tap, and the regional-language list.
"""

from support_service.config.models import Category, ConfigSnapshot
from support_service.models import Language

EN, HI, MR, BN = Language.EN, Language.HI, Language.MR, Language.BN

# --- approved templates ---------------------------------------------------

WELCOME_LANGUAGE = "welcome_language_select"
ISSUE_CATEGORY = "new_user_issue_category"
RETURNING_OPTIONS = "returning_user_options"
UPLOAD_MEDIA = "upload_media_request"
TICKET_STATUS = "ticket_status_update"
TICKET_CREATED = "ticket_created_confirmation"
TICKET_RESOLVED = "ticket_resolved"

# --- button labels --------------------------------------------------------
#
# A template's quick reply comes back as the button's own text, so these must
# match the approved templates character for character.

REGIONAL = "regional"

#: The welcome template's three buttons. WhatsApp allows no more, so Marathi
#: and Bengali sit behind "Regional", which answers with a list — free, because
#: the contact wrote first.
LANGUAGE_BUTTONS: tuple[tuple[str, str], ...] = (
    (EN.value, "English"),
    (HI.value, "हिन्दी"),
    (REGIONAL, "Regional"),
)

LANGUAGE_LABELS = {EN: "English", HI: "हिन्दी", MR: "मराठी", BN: "বাংলা"}

REGIONAL_LANGUAGES = (MR, BN)

NEW_TICKET = "new"
PREVIOUS_TICKET = "previous"
UPLOAD_NOW = "upload"
SKIP = "skip"

COPY: dict[Language, dict[str, str]] = {
    EN: {
        "invalid_choice": "Please tap one of the buttons above.",
        "ask_regional": "Please select your language",
        "new_ticket_button": "New Ticket",
        "previous_ticket_button": "Previous Ticket",
        "upload_button": "Upload Now",
        "skip_button": "Skip",
        "status_open": "Open",
        "status_in_progress": "In Progress",
        "status_resolved": "Resolved",
        "status_closed": "Closed",
    },
    HI: {
        "invalid_choice": "कृपया ऊपर दिए बटनों में से एक दबाएं।",
        "ask_regional": "कृपया अपनी भाषा चुनें",
        "new_ticket_button": "नया टिकट",
        "previous_ticket_button": "पिछला टिकट",
        "upload_button": "अभी अपलोड करें",
        "skip_button": "छोड़ें",
        "status_open": "खुला",
        "status_in_progress": "काम जारी है",
        "status_resolved": "हल हो गया",
        "status_closed": "बंद",
    },
    MR: {
        "invalid_choice": "कृपया वरील बटणांपैकी एक दाबा.",
        "ask_regional": "कृपया तुमची भाषा निवडा",
        "new_ticket_button": "नवीन तिकीट",
        "previous_ticket_button": "मागील तिकीट",
        "upload_button": "आता पाठवा",
        "skip_button": "वगळा",
        "status_open": "उघडे",
        "status_in_progress": "काम सुरू आहे",
        "status_resolved": "सुटले",
        "status_closed": "बंद",
    },
    BN: {
        "invalid_choice": "অনুগ্রহ করে উপরের একটি বোতামে চাপ দিন।",
        "ask_regional": "অনুগ্রহ করে আপনার ভাষা নির্বাচন করুন",
        "new_ticket_button": "নতুন টিকিট",
        "previous_ticket_button": "আগের টিকিট",
        "upload_button": "এখনই পাঠান",
        "skip_button": "বাদ দিন",
        "status_open": "খোলা",
        "status_in_progress": "কাজ চলছে",
        "status_resolved": "সমাধান হয়েছে",
        "status_closed": "বন্ধ",
    },
}

CATEGORIES = [
    Category(
        id="device",
        label={EN: "Device", HI: "डिवाइस", MR: "डिव्हाइस", BN: "ডিভাইস"},
        order=1,
    ),
    Category(
        id="software",
        label={EN: "Software", HI: "सॉफ़्टवेयर", MR: "सॉफ्टवेअर", BN: "সফটওয়্যার"},
        order=2,
    ),
    Category(
        id="other",
        label={EN: "Other", HI: "अन्य", MR: "इतर", BN: "অন্যান্য"},
        order=3,
    ),
]


def seed() -> ConfigSnapshot:
    return ConfigSnapshot(categories=CATEGORIES, strings=COPY)
