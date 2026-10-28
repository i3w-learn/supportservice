"""The QR holds a wa.me link whose pre-filled text names the centre."""

from __future__ import annotations

from pathlib import Path
from urllib.parse import parse_qs, urlparse

from support_service import qr
from support_service.conversation.centres import parse_centre_id


def test_the_link_opens_whatsapp_with_the_centre_greeting() -> None:
    link = qr.wa_link("918179921444", "NGP-AWC-017")

    parsed = urlparse(link)
    assert (parsed.scheme, parsed.netloc, parsed.path) == ("https", "wa.me", "/918179921444")
    text = parse_qs(parsed.query)["text"][0]
    assert text == "Hi, I need support. Centre ID: NGP-AWC-017"
    # The round trip: what the QR pre-fills is what the backend parses.
    assert parse_centre_id(text) == "NGP-AWC-017"


def test_writes_one_png_per_centre_and_a_print_sheet(tmp_path: Path, monkeypatch) -> None:
    sheet = tmp_path / "centres.csv"
    sheet.write_text(
        "centre_id,block,block_en,village,village_en\n"
        "NGP-AWC-001,रामटेक,Ramtek,शिवणीटोला,Shivanitola\n"
        "NGP-AWC-002,रामटेक,Ramtek,किरणापूर,Kiranapur\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(qr, "print_pdf", lambda html_path, pdf_path: False)

    count = qr.make_qr_codes(sheet, tmp_path / "out")

    assert count == 2
    assert (tmp_path / "out" / "NGP-AWC-001.png").stat().st_size > 0
    assert (tmp_path / "out" / "NGP-AWC-002.png").stat().st_size > 0
    html = (tmp_path / "out" / "cards.html").read_text(encoding="utf-8")
    assert "शिवणीटोला" in html and "NGP-AWC-002" in html
