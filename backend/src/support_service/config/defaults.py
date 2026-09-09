"""Seed copy and products.

Written to Firestore once at setup, then edited there. This module is the
starting point, not the source of truth at runtime.
"""

from support_service.config.models import Category, ConfigSnapshot, Service
from support_service.models import Language

EN, HI, TE, TA = Language.EN, Language.HI, Language.TE, Language.TA

COPY: dict[Language, dict[str, str]] = {
    EN: {
        "ask_language": "Choose your language",
        "ask_service": "Which product has the problem?",
        "ask_name": "Please share your name",
        "ask_centre": "What is your Anganwadi centre called?",
        "ask_category": "What is the problem?",
        "ask_description": ("Describe the issue. You can send photos or video too, then tap Done."),
        "done_button": "Done",
        "invalid_choice": "Please tap one of the options above.",
        "invalid_text": "Please send this as a text message.",
        "ticket_created": "Thank you. Your report has been logged — {ticket_id}",
        "appended": "Added to your open report {ticket_id}. We are looking into it.",
        "ask_which_ticket": "Which one is this about?",
        "new_problem": "Report a new problem",
        "ask_recently_closed": (
            "Is this about your {service_name} report {ticket_id}, or a new problem?"
        ),
        "yes_same": "Same problem",
        "reopened": "Reopened {ticket_id}. We are looking into it again.",
    },
    HI: {
        "ask_language": "अपनी भाषा चुनें",
        "ask_service": "किस product में समस्या है?",
        "ask_name": "कृपया अपना नाम बताएं",
        "ask_centre": "आपकी आंगनवाड़ी का नाम क्या है?",
        "ask_category": "क्या समस्या है?",
        "ask_description": "समस्या बताएं। फोटो या वीडियो भी भेज सकते हैं, फिर Done दबाएं।",
        "done_button": "हो गया",
        "invalid_choice": "कृपया ऊपर दिए विकल्पों में से एक चुनें।",
        "invalid_text": "कृपया इसे टेक्स्ट में भेजें।",
        "ticket_created": "धन्यवाद। आपकी शिकायत दर्ज हो गई है — {ticket_id}",
        "appended": "आपकी शिकायत {ticket_id} में जोड़ दिया गया है।",
        "ask_which_ticket": "यह किस बारे में है?",
        "new_problem": "नई समस्या बताएं",
        "ask_recently_closed": "क्या यह आपकी {service_name} शिकायत {ticket_id} के बारे में है?",
        "yes_same": "वही समस्या",
        "reopened": "{ticket_id} फिर से खोल दी गई है।",
    },
}

SERVICES = [
    Service(
        id="anganwadi-vr",
        name={EN: "Anganwadi VR", HI: "आंगनवाड़ी VR", TE: "అంగన్‌వాడీ VR", TA: "அங்கன்வாடி VR"},
        order=1,
        categories=[
            Category(
                id="headset", label={EN: "Headset not working", HI: "हेडसेट चालू नहीं होता"}, order=1
            ),
            Category(
                id="controller",
                label={EN: "Controller not pairing", HI: "कंट्रोलर कनेक्ट नहीं होता"},
                order=2,
            ),
            Category(
                id="content", label={EN: "Content not loading", HI: "कंटेंट लोड नहीं होता"}, order=3
            ),
            Category(
                id="other",
                label={EN: "Something else", HI: "कुछ और"},
                order=99,
            ),
        ],
    ),
    Service(
        id="poshan-ai",
        name={EN: "Poshan AI", HI: "पोषण AI", TE: "పోషణ్ AI", TA: "போஷண் AI"},
        order=2,
        categories=[
            Category(
                id="data-loss",
                label={EN: "Data not saving", HI: "डेटा सेव नहीं होता"},
                order=1,
            ),
            Category(
                id="crash",
                label={EN: "App crashes", HI: "ऐप बंद हो जाता है"},
                order=2,
            ),
            Category(
                id="other",
                label={EN: "Something else", HI: "कुछ और"},
                order=99,
            ),
        ],
    ),
    Service(
        id="german-ai",
        name={EN: "German AI", HI: "जर्मन AI", TE: "జర్మన్ AI", TA: "ஜெர்மன் AI"},
        order=3,
        categories=[
            Category(
                id="audio",
                label={EN: "Audio not playing", HI: "आवाज़ नहीं आती"},
                order=1,
            ),
            Category(
                id="other",
                label={EN: "Something else", HI: "कुछ और"},
                order=99,
            ),
        ],
    ),
]


def seed() -> ConfigSnapshot:
    return ConfigSnapshot(services=SERVICES, strings=COPY)
