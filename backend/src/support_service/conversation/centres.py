"""Reading the Anganwadi centre out of a QR-code greeting.

Each centre's QR opens WhatsApp with a pre-filled message such as
"Hi, I need support. Centre ID: NGP-AWC-017". Only that id is trusted; the
rest of the message is free text the user may well have edited.
"""

from __future__ import annotations

import re

# "Centre ID: NGP-AWC-017", also "Center Id - ngp-awc-17" and the like.
_CENTRE_ID = re.compile(
    r"cent(?:re|er)\s*id\s*[:\-–]?\s*([A-Za-z]{2,5}-[A-Za-z]{2,5}-\d{1,4})",
    re.IGNORECASE,
)


def parse_centre_id(text: str | None) -> str | None:
    """The centre id in a message, normalised to NGP-AWC-017 form, or None."""
    if not text:
        return None
    match = _CENTRE_ID.search(text)
    if match is None:
        return None
    prefix, block, number = match.group(1).rsplit("-", 2)
    return f"{prefix.upper()}-{block.upper()}-{int(number):03d}"
