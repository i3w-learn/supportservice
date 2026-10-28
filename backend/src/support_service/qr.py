"""Make one WhatsApp QR code per Anganwadi centre, plus a print-ready sheet.

    uv run python -m support_service.qr data/centres.csv ../docs/qr

Each QR holds only a wa.me link that opens WhatsApp with the greeting
"Hi, I need support. Centre ID: NGP-AWC-017" already typed in. The id is
how the backend knows which centre the message came from, so nothing on the
server has to change when a QR is reprinted.

Output: `<out>/<centre_id>.png` per centre, `<out>/cards.html` with four
cards per A4 page, and `<out>/anganwadi-qr-codes.pdf` printed from it with
headless Chrome (set CHROME_BIN to point at the browser if it is not at the
macOS default). Chrome does the Marathi text shaping that Pillow cannot.
"""

from __future__ import annotations

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
    data = base64.b64encode(png).decode("ascii")
    e = html.escape
    pretty_number = f"+{number[:2]} {number[2:7]} {number[7:]}"
    return f"""
    <article class="card">
      <h1>Tech Support <span>by Infinity Learn</span></h1>
      <img src="data:image/png;base64,{data}" alt="QR for {e(centre["centre_id"])}">
      <p class="scan">मदतीसाठी स्कॅन करा · मदद के लिए स्कैन करें</p>
      <p class="village">{e(centre["village"])} <small>{e(centre["village_en"])}</small></p>
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
"""


def render_sheet(cards: list[str], per_page: int = 4) -> str:
    pages = [
        f'<section class="sheet">{"".join(cards[i : i + per_page])}</section>'
        for i in range(0, len(cards), per_page)
    ]
    return (
        '<!doctype html><html lang="mr"><head><meta charset="utf-8">'
        "<title>Anganwadi WhatsApp support QR codes</title>"
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


def make_qr_codes(csv_path: Path, out: Path, number: str = DEFAULT_NUMBER) -> int:
    out.mkdir(parents=True, exist_ok=True)
    cards: list[str] = []
    for centre in read_centres(csv_path):
        png = qr_png(wa_link(number, centre["centre_id"]))
        (out / f"{centre['centre_id']}.png").write_bytes(png)
        cards.append(_card(centre, png, number))

    html_path = out / "cards.html"
    html_path.write_text(render_sheet(cards), encoding="utf-8")
    print_pdf(html_path, out / "anganwadi-qr-codes.pdf")
    return len(cards)


if __name__ == "__main__":
    if len(sys.argv) not in (3, 4):
        print(
            "usage: python -m support_service.qr <centres.csv> <out-dir> [number]", file=sys.stderr
        )
        sys.exit(2)
    number = (
        sys.argv[3]
        if len(sys.argv) == 4
        else os.environ.get("GUPSHUP_SOURCE_NUMBER", DEFAULT_NUMBER)
    )
    count = make_qr_codes(Path(sys.argv[1]), Path(sys.argv[2]), number)
    print(f"Wrote {count} QR codes to {sys.argv[2]}")
