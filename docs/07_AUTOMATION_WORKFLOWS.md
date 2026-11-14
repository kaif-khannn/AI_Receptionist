# 07 — Automation workflows

> Replaces the blueprint's `07_N8N_WORKFLOWS.md`. Core automations run in the **Python worker** (decision D2 in [02](02_SYSTEM_ARCHITECTURE.md)). n8n is optional, for client-specific integrations only.

## Mechanism
1. A business change and its event are written **in the same transaction**: e.g. insert `bookings` row + insert `outbox_events(type='booking.created')`.
2. Worker loop claims due events with `SELECT … FOR UPDATE SKIP LOCKED`.
3. Handler runs; on success → `done`. On failure → `attempts += 1`, `next_attempt_at` with exponential backoff + jitter.
4. After max attempts → `dead` + Sentry alert; replayable from an admin action.
5. Handlers are **idempotent** (keyed by event ID), so a retry never sends a duplicate email or creates a duplicate record.
6. Scheduled jobs (cron-style) run inside the same worker.

## Workflows
| # | Trigger | Steps |
|---|---|---|
| 1 | Call starts (`assistant-request`) | Synchronous in FastAPI: resolve tenant → kill-switch check → return config |
| 2 | `call.ended` | Store transcript + summary → upsert contact → create/update lead → owner email. Call outcome saved even with no lead |
| 3 | `booking.created` / `updated` | Customer confirmation email → owner notification → Google Calendar sync → record delivery status |
| 4 | `emergency.escalated` | Safety response already given live; worker sends urgent owner alert, records incident, creates follow-up task |
| 5 | Missed / failed call | Missed-call record → owner email → callback task |
| 6 | Daily 07:00 Europe/London | Owner report: calls, answered/failed, leads, bookings, callbacks, emergencies |
| 7 | Daily | Retention: purge transcripts/recordings past the tenant's retention period |
| 8 | Hourly | Release expired slot holds; aggregate usage and cost per tenant |

## Optional n8n integration
Backend sends HMAC-signed webhooks (event type, event ID, minimal payload) to a tenant-configured URL. n8n workflows for that client live in `automation/` as versioned exports. Check the n8n Sustainable Use License before relying on it commercially.
