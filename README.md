# HVAC AI Receptionist

A multi-tenant SaaS that gives small UK heating and boiler companies an AI phone receptionist. It answers inbound calls, explains the company's approved services and prices, qualifies the enquiry, books appointments or callbacks, handles gas/CO emergencies safely, and sends the owner a summary.

## Repository layout

| Path | Contents |
|---|---|
| `backend/` | FastAPI app, worker, models, migrations, tests |
| `frontend/` | React + Vite + TypeScript + Tailwind owner dashboard |
| `agent/` | Voice-agent prompts, tool schemas, conversation evaluations *(created in Phase 3)* |
| `automation/` | Optional n8n workflow exports for client-specific integrations *(created when needed)* |
| `infrastructure/` | Deployment configs *(created in Phase 9)* |
| `docs/` | Product and technical documentation, starting at [01_PRODUCT_REQUIREMENTS.md](docs/01_PRODUCT_REQUIREMENTS.md) |

## Local development (Windows)

Prerequisites: Python 3.13+, Node 24+. Docker is optional.

### Backend

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
copy .env.example .env      # then edit .env
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

API docs: http://localhost:8000/docs (disabled in production).

### Frontend

```powershell
cd frontend
npm install
npm run dev
```

Open http://localhost:5173. Requests to `/api` and `/health` are proxied to the backend.

### Checks (same as CI)

```powershell
# backend
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m ruff format --check .
.\.venv\Scripts\python.exe -m mypy app tests
.\.venv\Scripts\python.exe -m pytest

# frontend
npm run lint; npm run typecheck; npm run build
```

> **Windows Smart App Control** blocks mypy's compiled build. If `mypy` fails with "An Application Control policy has blocked this file", reinstall it as pure Python:
> `.\.venv\Scripts\python.exe -m pip install --force-reinstall --no-deps --no-binary mypy mypy`

### Optional: Docker

`docker compose up --build` starts a local Postgres (pgvector) and the backend.

## Environments

| Environment | Hosting | Cost |
|---|---|---|
| local | Your PC (+ Cloudflare tunnel for voice webhooks) | Free |
| staging | Free tiers (see [10_DEPLOYMENT_GUIDE.md](docs/10_DEPLOYMENT_GUIDE.md)) | Free |
| production | Paid tiers, created when the first customer signs | Paid |

## Roadmap

| Phase | Scope | Status |
|---|---|---|
| 0 | Repo, tooling, CI, docs | ✅ Done |
| 1 | Database, migrations, tenants + RLS, auth | — |
| 2 | Business onboarding: profile, services, packages, areas, engineers | — |
| 3 | Voice core: Vapi, tools, safety, transcripts, kill switch | — |
| 4 | Leads + outbox worker: post-call processing, notifications | — |
| 5 | Bookings, availability, calendar sync | — |
| 6 | Knowledge engine | — |
| 7 | Owner dashboard | — |
| 8 | Security + QA hardening | — |
| 9 | Production deployment + pilot | — |
