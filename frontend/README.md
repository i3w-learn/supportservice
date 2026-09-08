# frontend — support-service dashboard

React 18 · Vite · TypeScript · Tailwind. See `../support-system-design.md`.

**Reads** go straight to Firestore via `onSnapshot` (live updates, free).
**Writes** go to the REST API only — status rules and WhatsApp sending live
in one place (§1). Never write to Firestore from here; the rules deny it.

Copy `.env.example` to `.env.local` before running. Commands from the repo
root: `just dash`, `just dash-build`.
