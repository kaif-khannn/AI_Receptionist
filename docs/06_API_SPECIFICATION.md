# 06 — API specification

Interactive spec: `/docs` (non-production). The frontend's TypeScript client is generated from `/openapi.json`.

## Conventions
- Versioned under `/api/v1`. Provider webhooks under `/api/v1/voice/*` and `/api/v1/webhooks/*`, separate from dashboard routes.
- Auth: httpOnly secure cookies (access + rotating refresh token). Tenant derived from the session.
- Every response carries `x-request-id`.
- Mutating requests that may be retried accept an `Idempotency-Key` header.
- Errors: `{"error": {"code": "booking_conflict", "message": "…", "request_id": "…"}}`.
- Conflicts → `409`; validation → `422`; auth → `401/403`; rate limit → `429`.

## Endpoints
| Method | Path | Purpose | Phase |
|---|---|---|---|
| GET | /health/live, /health/ready | Probes | 0 ✅ |
| POST | /api/v1/auth/login, /logout, /refresh | Session | 1 |
| GET | /api/v1/me | Current user + tenant | 1 |
| GET/PATCH | /api/v1/business | Business profile | 2 |
| CRUD | /api/v1/services, /packages, /service-areas, /engineers | Catalogue + team | 2 |
| POST | /api/v1/voice/inbound | Vapi assistant-request | 3 |
| POST | /api/v1/voice/tool-calls | Vapi tool calls | 3 |
| POST | /api/v1/voice/events | Vapi status / end-of-call | 3 |
| GET | /api/v1/calls, /calls/{id} | Call history + transcript | 4 |
| GET/POST/PATCH | /api/v1/leads | Leads | 4 |
| GET/PATCH | /api/v1/callbacks | Callback tasks | 4 |
| POST | /api/v1/bookings/check | Availability | 5 |
| POST/PATCH | /api/v1/bookings | Create / reschedule / cancel | 5 |
| POST | /api/v1/integrations/calendar | Google Calendar OAuth | 5 |
| POST | /api/v1/knowledge/upload | Upload document | 6 |
| POST | /api/v1/knowledge/{id}/approve | Publish | 6 |
| GET | /api/v1/dashboard/overview, /reports | Stats | 7 |
