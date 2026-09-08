# support-service

WhatsApp support and ticketing for i3w.ai products — Anganwadi VR, German AI,
Poshan AI. Field users on WhatsApp, one admin on a web dashboard.

Design: [`support-system-design.md`](./support-system-design.md).

## Layout

| Path | What |
|---|---|
| `backend/` | Python 3.12 · FastAPI · Cloud Run. Seven modules (§3) |
| `frontend/` | React · Vite · TypeScript · Tailwind. Admin dashboard |
| `firestore.rules` | The only wall in front of the data (§9) |
| `firestore.indexes.json` | Composite indexes from §8 |
| `storage.rules` | Deny-all — attachments go out via signed URLs |
| `infra/` | Pulumi (GCP project `ai-powered-479515`) |
| `rules-tests/` | Node tests for `firestore.rules` |

## Getting started

```sh
just install          # uv sync + pnpm install
just emulators        # Firestore :8081 · Auth :9099 · UI :4000 (needs Java 21+)
just test             # pytest against the emulator
just run              # API on :8088
just dash             # dashboard on :5173
```

Copy `backend/.env.example` → `backend/.env` and
`frontend/.env.example` → `frontend/.env.local` first.

## Before first deploy

Create one `admins/{uid}` document by hand. Without it the rules deny every
read, including yours — that is intentional (§9).

## Ports

| Port | What | Why not the default |
|---|---|---|
| 8088 | API (local dev) | 8080 and 8000 are taken by other projects on this machine |
| 8081 | Firestore emulator | same |
| 9099 | Auth emulator | |
| 4000 | Emulator UI | |
| 5173 | Dashboard (Vite) | |

The container still listens on `$PORT` (8080 default) — Cloud Run sets it.
Only local dev ports moved.
