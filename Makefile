# EarnScore developer commands. On Windows use `mingw32-make` (or run the commands directly).
ifeq ($(OS),Windows_NT)
PY := backend/.venv/Scripts/python.exe
else
PY := backend/.venv/bin/python
endif
BE := cd backend &&
BPY := $(abspath $(PY))

.PHONY: install migrate seed generate simulate data dev-api dev-web build test test-backend test-frontend e2e up down purge

install:            ## create the venv and install backend + frontend dependencies
	python -m venv backend/.venv
	$(PY) -m pip install -r backend/requirements-dev.txt
	cd frontend && npm ci && npx playwright install chromium

migrate:
	$(BE) $(BPY) -m app.cli migrate

seed:               ## role accounts from SEED_* env vars (see .env.example)
	$(BE) $(BPY) -m app.cli seed

generate:           ## generated workers + cohort population through the upload pipeline
	$(BE) $(BPY) -m app.cli generate

simulate:           ## validation simulator (5,000 workers) + EBM v2
	$(BE) $(BPY) -m app.cli simulate --workers 5000

data: migrate generate simulate seed

purge:
	$(BE) $(BPY) -m app.cli purge

dev-api:
	$(BE) $(BPY) -m uvicorn app.main:app --reload --port 8000

dev-web:
	cd frontend && npm run dev

build:
	cd frontend && npm run build

test: test-backend test-frontend e2e

test-backend:
	$(BE) $(BPY) -m pytest -q

test-frontend:
	cd frontend && npx vitest run

e2e:                ## Playwright end-to-end flow against E2E_BASE_URL (default http://127.0.0.1:8000)
	cd frontend && npx playwright test

up:
	docker compose up --build -d

down:
	docker compose down
