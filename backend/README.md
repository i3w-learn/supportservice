# backend — support-service

Python 3.12 · FastAPI · Cloud Run. See `../support-system-design.md`.

## Modules (§3)

| Package | Owns |
|---|---|
| `channel` | Gupshup payloads, signature check, dedupe, send, receipts |
| `media` | Fetch from expiring URLs, write to Storage, signed URLs |
| `conversation` | Bot step machine, inbound routing, contact identity |
| `tickets` | Lifecycle, transitions, numbering, events, SLA |
| `admin_api` | REST surface, token verification, validation |
| `jobs` | 2-min media + idle pass · hourly sweep |
| `config` | Products, categories, languages, copy, thresholds |

**Rule:** `conversation` and `tickets` never import Gupshup types.

## Commands

Run from the repo root: `just run`, `just test`, `just check`.
