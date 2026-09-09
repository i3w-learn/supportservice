# support-service — see support-system-design.md

# backend/.env is loaded into every recipe, so .env.example is honest
# about what it does. Missing file is fine.
set dotenv-load := true
set dotenv-path := "backend/.env"
set dotenv-required := false

default:
    @just --list

# --- setup ---

install:
    cd backend && uv sync
    cd frontend && pnpm install

# --- backend ---

run:
    cd backend && uv run uvicorn support_service.main:app --reload --port 8088

lint:
    cd backend && uv run ruff check .
    cd backend && uv run ruff format --check .

fmt:
    cd backend && uv run ruff format .

types:
    cd backend && uv run pyright

# Offline. Pure logic only — no emulator, no network, no Java.
test-unit:
    cd backend && uv run pytest -m "not firestore"

# Everything. Requires `just emulators` in another shell; the env vars make
# firebase-admin talk to the emulator instead of real Firestore.
test:
    cd backend && \
      FIRESTORE_EMULATOR_HOST=localhost:8081 \
      FIREBASE_AUTH_EMULATOR_HOST=localhost:9099 \
      uv run pytest

check: lint types test dash-types dash-test

# Fast pre-commit gate — no emulator needed.
check-fast: lint types test-unit dash-types dash-test

build:
    cd backend && docker build -t support-service .

# --- emulators ---

# Java 21+ only — the Firestore emulator is a JVM program. brew installs
# openjdk@21 keg-only, so prefer it when present and otherwise fall back to
# whatever java is on PATH. Nothing but the emulator needs Java.
emulators:
    #!/usr/bin/env bash
    set -euo pipefail
    for candidate in /opt/homebrew/opt/openjdk@21 /usr/local/opt/openjdk@21; do
        if [ -d "$candidate" ]; then
            export JAVA_HOME="$candidate"
            export PATH="$candidate/bin:$PATH"
            break
        fi
    done
    if ! java -version 2>&1 | grep -qE '"(2[1-9]|[3-9][0-9])'; then
        echo "Need Java 21+ for the Firestore emulator. Found:" >&2
        java -version 2>&1 >&2 || echo "  no java on PATH" >&2
        echo "Install with: brew install openjdk@21" >&2
        exit 1
    fi
    firebase emulators:start --only firestore,auth --project ai-powered-479515

# --- frontend ---

dash:
    cd frontend && pnpm dev

dash-build:
    cd frontend && pnpm build

# Frontend unit tests — the §8 transition table and the 24-hour window rule.
dash-test:
    cd frontend && pnpm test

dash-types:
    cd frontend && npx tsc --noEmit -p tsconfig.app.json

# --- deploy ---

rules:
    firebase deploy --only firestore:rules,storage --project ai-powered-479515

indexes:
    firebase deploy --only firestore:indexes --project ai-powered-479515

hosting: dash-build
    firebase deploy --only hosting --project ai-powered-479515
