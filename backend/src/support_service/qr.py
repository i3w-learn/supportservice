"""Make one WhatsApp QR code per centre or school, plus a print-ready sheet.

    uv run python -m support_service.qr data/centres.csv ../docs/qr
    uv run python -m support_service.qr data/schools.csv ../docs/qr-schools \\
        --per-page 1 --pdf-name school-qr-codes.pdf --title "School WhatsApp support QR codes"

Each QR holds only a wa.me link that opens WhatsApp with the greeting
"Hi, I need support. Centre ID: NGP-AWC-017" already typed in. The id is
how the backend knows which centre the message came from, so nothing on the
server has to change when a QR is reprinted.

Output: `<out>/<centre_id>.png` per row, `<out>/cards.html` with four cards
per A4 page (or one full-page card with `--per-page 1`), and a PDF printed
from it with headless Chrome (set CHROME_BIN to point at the browser if it
is not at the macOS default). Chrome does the Marathi text shaping that
Pillow cannot.
"""

from __future__ import annotations

import argparse
import base64
import html
import io
import os
import subprocess
import sys
from pathlib import Path
from typing import Any
from urllib.parse import quote

import qrcode
from qrcode.constants import ERROR_CORRECT_M

from support_service.centres import read_centres

GREETING = "Hi, I need support. Centre ID: {centre_id}"
DEFAULT_NUMBER = "918179921444"
DEFAULT_CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
DEFAULT_PDF_NAME = "anganwadi-qr-codes.pdf"
DEFAULT_TITLE = "Anganwadi WhatsApp support QR codes"


def wa_link(number: str, centre_id: str) -> str:
    """The link a QR holds. `safe=""` so the space and colon are encoded too."""
    return f"https://wa.me/{number}?text={quote(GREETING.format(centre_id=centre_id), safe='')}"


def qr_png(link: str) -> bytes:
    code = qrcode.QRCode(error_correction=ERROR_CORRECT_M, box_size=10, border=2)
    code.add_data(link)
    buffer = io.BytesIO()
    # The Pillow image factory writes PNG; its stub lacks the format kwarg.
    code.make_image().get_image().save(buffer, "PNG")
    return buffer.getvalue()


def _card(centre: dict[str, Any], png: bytes, number: str) -> str:
    """One card. A school prints its full name; a centre prints its village.

    The small English line under the name is only there to translate a
    Marathi name. When the sheet has English only, printing it twice would
    look like a mistake, so it is left out.
    """
    data = base64.b64encode(png).decode("ascii")
    e = html.escape
    pretty_number = f"+{number[:2]} {number[2:7]} {number[7:]}"
    name = centre.get("school_name") or centre["village"]
    translation = centre["village_en"] if centre["village_en"] != centre["village"] else ""
    small = f" <small>{e(translation)}</small>" if translation else ""
    return f"""
    <article class="card">
      <h1>Tech Support <span>by Infinity Learn</span></h1>
      <img src="data:image/png;base64,{data}" alt="QR for {e(centre["centre_id"])}">
      <p class="scan">मदतीसाठी स्कॅन करा · मदद के लिए स्कैन करें</p>
      <p class="village">{e(name)}{small}</p>
      <p class="block">{e(centre["block"])} · {e(centre["block_en"])}</p>
      <p class="id">{e(centre["centre_id"])}</p>
      <p class="phone">WhatsApp {e(pretty_number)}</p>
    </article>"""


_STYLE = """
  @page { size: A4; margin: 10mm; }
  * { box-sizing: border-box; }
  body { margin: 0; font-family: "Helvetica Neue", Arial, "Kohinoor Devanagari",
         "Devanagari Sangam MN", sans-serif; color: #111; }
  .sheet { display: grid; grid-template-columns: 1fr 1fr; gap: 8mm;
           page-break-after: always; }
  .sheet:last-child { page-break-after: auto; }
  .card { border: 0.6mm solid #111; border-radius: 4mm; padding: 6mm 5mm;
          height: 133mm; display: flex; flex-direction: column; align-items: center;
          text-align: center; break-inside: avoid; }
  h1 { font-size: 15pt; margin: 0 0 3mm; letter-spacing: 0.02em; }
  h1 span { display: block; font-size: 9pt; font-weight: normal; color: #444; }
  img { width: 62mm; height: 62mm; image-rendering: pixelated; }
  .scan { font-size: 10pt; margin: 3mm 0 2mm; }
  .village { font-size: 16pt; font-weight: bold; margin: 0; line-height: 1.3; }
  .village small { display: block; font-size: 10pt; font-weight: normal; color: #444; }
  .block { font-size: 10pt; margin: 1.5mm 0 0; color: #333; }
  .id { font-family: Menlo, monospace; font-size: 12pt; font-weight: bold;
        margin: 3mm 0 0; letter-spacing: 0.08em; }
  .phone { font-size: 9pt; color: #444; margin: 1.5mm 0 0; }

  /* One card per A4 page: same layout, roughly double the size. */
  .single { grid-template-columns: 1fr; }
  .single .card { height: 270mm; padding: 16mm 12mm; justify-content: center; }
  .single h1 { font-size: 30pt; margin-bottom: 8mm; }
  .single h1 span { font-size: 16pt; }
  .single img { width: 120mm; height: 120mm; }
  .single .scan { font-size: 18pt; margin: 8mm 0 5mm; }
  .single .village { font-size: 28pt; }
  .single .village small { font-size: 16pt; }
  .single .block { font-size: 18pt; margin-top: 4mm; }
  .single .id { font-size: 22pt; margin-top: 8mm; }
  .single .phone { font-size: 16pt; margin-top: 4mm; }
"""


def render_sheet(cards: list[str], per_page: int = 4, title: str = DEFAULT_TITLE) -> str:
    section_class = "sheet single" if per_page == 1 else "sheet"
    pages = [
        f'<section class="{section_class}">{"".join(cards[i : i + per_page])}</section>'
        for i in range(0, len(cards), per_page)
    ]
    return (
        '<!doctype html><html lang="mr"><head><meta charset="utf-8">'
        f"<title>{html.escape(title)}</title>"
        f"<style>{_STYLE}</style></head><body>{''.join(pages)}</body></html>"
    )


def print_pdf(html_path: Path, pdf_path: Path) -> bool:
    chrome = os.environ.get("CHROME_BIN", DEFAULT_CHROME)
    if not Path(chrome).exists():
        print(f"Chrome not found at {chrome}; open {html_path} and print it", file=sys.stderr)
        return False
    subprocess.run(
        [
            chrome,
            "--headless=new",
            "--disable-gpu",
            "--no-pdf-header-footer",
            f"--print-to-pdf={pdf_path}",
            html_path.resolve().as_uri(),
        ],
        check=True,
        capture_output=True,
    )
    return True


def make_qr_codes(
    csv_path: Path,
    out: Path,
    number: str = DEFAULT_NUMBER,
    per_page: int = 4,
    pdf_name: str = DEFAULT_PDF_NAME,
    title: str = DEFAULT_TITLE,
) -> int:
    out.mkdir(parents=True, exist_ok=True)
    cards: list[str] = []
    for centre in read_centres(csv_path):
        png = qr_png(wa_link(number, centre["centre_id"]))
        (out / f"{centre['centre_id']}.png").write_bytes(png)
        cards.append(_card(centre, png, number))

    html_path = out / "cards.html"
    html_path.write_text(render_sheet(cards, per_page, title), encoding="utf-8")
    print_pdf(html_path, out / pdf_name)
    return len(cards)


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="python -m support_service.qr", description=__doc__)
    parser.add_argument("csv", type=Path, help="centres.csv or schools.csv")
    parser.add_argument("out", type=Path, help="directory for the PNGs, cards.html and PDF")
    parser.add_argument(
        "--number",
        default=os.environ.get("GUPSHUP_SOURCE_NUMBER", DEFAULT_NUMBER),
        help="support WhatsApp number, digits only (default: GUPSHUP_SOURCE_NUMBER)",
    )
    parser.add_argument(
        "--per-page", type=int, choices=(1, 4), default=4, help="cards per A4 page (default 4)"
    )
    parser.add_argument("--pdf-name", default=DEFAULT_PDF_NAME, help="file name of the PDF")
    parser.add_argument("--title", default=DEFAULT_TITLE, help="title of the print sheet")
    return parser.parse_args(argv)


if __name__ == "__main__":
    args = _parse_args(sys.argv[1:])
    count = make_qr_codes(args.csv, args.out, args.number, args.per_page, args.pdf_name, args.title)
    print(f"Wrote {count} QR codes to {args.out}")
