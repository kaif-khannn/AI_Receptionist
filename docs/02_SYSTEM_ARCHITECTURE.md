# 02 — System architecture

## Overview

```
Caller ──► Twilio UK number ──► Vapi (speech, turn-taking, LLM)
                 │ fallback           │  assistant-request / tool calls / events (signed webhooks)
                 ▼                    ▼
           Owner mobile /     FastAPI backend (modular monolith) ──► Postgres (Neon) + pgvector
           voicemail                  │                                   ▲
                                      ▼                                   │
                               Outbox table ──► Python worker ────────────┘
                                                   │ email, calendar sync, reports, retention
                                                   └──► optional signed webhooks ──► n8n (client extras)

Owner dashboard (React, Cloudflare Pages) ──► FastAPI REST API
```

## Components
| Component | Responsibility |
|---|---|
| **Twilio** | UK numbers, inbound routing, transfer, fallback forwarding when Vapi fails or the kill switch is on |
| **Vapi** | Real-time audio, STT/TTS, interruption handling, tool calls, end-of-call reports |
| **FastAPI backend** | Source of truth: tenants, auth, business data, voice tools, bookings, leads, webhooks |
| **Python worker** | Async jobs from the outbox: post-call processing, notifications, calendar sync, daily reports, data retention |
| **Postgres (Neon) + pgvector** | All relational data, RLS tenant isolation, knowledge embeddings, job queue |
| **React dashboard** | Owner/manager/engineer UI |
| **n8n (optional)** | Client-specific integrations only, fed by our signed webhooks |

## Key decisions
| # | Decision | Why |
|---|---|---|
| D1 | **Modular monolith** (one FastAPI codebase, API + worker processes) | Simple to build, deploy and debug for a small team |
| D2 | **Core automations in Python, not n8n** | Transactional with the DB, idempotent, tested in CI, versioned in git, one less service. n8n kept optional for client extras |
| D3 | **Transactional outbox + Postgres queue** (`SELECT … FOR UPDATE SKIP LOCKED`) | Events are written in the same transaction as the change; no lost or duplicate side effects; no Redis needed |
| D4 | **No Redis in V1** | Postgres covers queue, idempotency and rate-limit storage. Add Redis only if load requires |
| D5 | **One Vapi assistant template + per-call config** via `assistant-request` webhook | Tenant identified from the called number at call start; no per-tenant assistants to keep in sync |
| D6 | **Voice provider adapter** | Vapi-specific code isolated so Retell can replace it |
| D7 | **Deterministic emergency detection** before the LLM | Gas/CO safety must not depend on model judgement |
| D8 | **Double-booking prevented by a Postgres exclusion constraint** | Correct under concurrency regardless of application bugs |
| D9 | **UK/EU data residency** (Neon London, hosting in London/EU) | UK GDPR; simpler subprocessor story |
| D10 | **Free tiers for testing, paid tiers at first customer** | Pre-revenue cost control |

## Trust boundaries
1. **Public internet → API**: dashboard requests carry an auth cookie; tenant is derived server-side, never from the client.
2. **Vapi/Twilio → webhooks**: verified by shared secret/signature, timestamp and event-ID replay protection.
3. **LLM → tools**: model input is untrusted. Tools validate every argument, never accept a tenant ID from the model, and never expose secrets or internal IDs.
4. **App → database**: app connects as a non-owner role; RLS enforced with `FORCE ROW LEVEL SECURITY`.

## Failure behaviour
| Failure | Behaviour |
|---|---|
| Vapi down / errors | Twilio fallback forwards to owner mobile or voicemail; missed-call record + callback task |
| Backend tool call fails | Agent uses a safe fallback ("I'll have the team call you back") and creates a callback where possible |
| Worker / email down | Calls unaffected; outbox retries with backoff, then dead-letter + alert |
| Knowledge lookup fails | Agent does not guess; offers callback |
