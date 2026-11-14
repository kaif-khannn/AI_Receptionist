# 03 — Database schema

Postgres (Neon) · SQLAlchemy 2 · Alembic · pgvector. *Full DDL is added in Phase 1; this doc records the design.*

## Rules
- Every business-owned table has `tenant_id` (FK → `tenants`), indexed.
- **RLS** on every tenant table, policy `tenant_id = app_current_tenant()` for both reads (`USING`) and writes (`WITH CHECK`).
- App connects as the **non-owner role `app_user`** (no `BYPASSRLS`), so RLS always applies to it. The app refuses to start if its role can bypass RLS. Migrations run as the owner (`neondb_owner`, which has `BYPASSRLS` on Neon).
- `FORCE ROW LEVEL SECURITY` is deliberately **not** used: the narrow `SECURITY DEFINER` lookup functions (e.g. `auth_lookup_user`, which returns only user and tenant IDs at login) run as the owner and need to see across tenants.
- Tenant set per transaction with `set_config('app.tenant_id', …, true)` from a SQLAlchemy `after_begin` hook, so it can't be forgotten and works with Neon's transaction-mode pooler.
- `audit_logs` is append-only for the app role (no `UPDATE`/`DELETE` grant).
- Primary keys: UUID (v7 where available, for index locality).
- Timestamps: `timestamptz` in UTC; displayed in the business timezone (default `Europe/London`).
- Phone numbers: E.164. Money: integer minor units (`price_minor`, pence) + `currency` (`GBP`).
- JSONB only for flexible metadata and extraction payloads, never for core fields.
- Integration credentials encrypted at the application layer.

## Tables
| Table | Key fields |
|---|---|
| tenants | id, name, slug, status, plan, ai_enabled (kill switch), created_at |
| users | id, tenant_id, email (unique platform-wide, case-insensitive), password_hash (Argon2id), role, status, failed_login_count, locked_until |
| auth_sessions | id, tenant_id, user_id, current_jti (rotating refresh token), expires_at, revoked_at |
| businesses | id, tenant_id, company_name, address, timezone, opening_hours, emergency_policy, transfer_number |
| phone_numbers | id, tenant_id, provider, number_e164 (unique), fallback_number, status |
| services | id, tenant_id, name, description, default_duration_min, active |
| packages | id, tenant_id, service_id, name, price_minor, currency, active |
| package_features | id, tenant_id, package_id, feature, included, conditions |
| service_areas | id, tenant_id, postcode_prefix (outward code / district), active |
| contacts | id, tenant_id, name, phone_e164, email, address, postcode |
| leads | id, tenant_id, contact_id, service_id, status, urgency, source_call_id |
| calls | id, tenant_id, contact_id, provider_call_id (unique), started_at, duration_s, outcome, cost_minor |
| transcripts | id, tenant_id, call_id, speaker, content, offset_ms |
| call_summaries | id, tenant_id, call_id, summary, extracted_data (JSONB) |
| engineers | id, tenant_id, name, phone_e164, capabilities, active |
| working_hours / time_off | id, tenant_id, engineer_id, … |
| bookings | id, tenant_id, lead_id, engineer_id, service_id, `during tstzrange`, status |
| slot_holds | id, tenant_id, engineer_id, `during`, call_id, expires_at |
| callbacks | id, tenant_id, contact_id, call_id, reason, due_at, status |
| knowledge_documents | id, tenant_id, title, category, version, status (draft/approved/archived), source |
| knowledge_chunks | id, tenant_id, document_id, content, embedding vector, metadata |
| outbox_events | id, tenant_id, type, payload, status, attempts, next_attempt_at, last_error |
| processed_webhooks | provider, event_id (PK), received_at — replay/idempotency |
| idempotency_keys | key, tenant_id, response, created_at |
| usage_records | id, tenant_id, call_id, kind (minutes/llm/tts/stt), quantity, cost_minor |
| integrations | id, tenant_id, provider, encrypted_credentials, status |
| audit_logs | id, tenant_id, actor_id, action, target, metadata, created_at |

## Double-booking prevention
```sql
CREATE EXTENSION IF NOT EXISTS btree_gist;
ALTER TABLE bookings ADD CONSTRAINT no_overlap
  EXCLUDE USING gist (engineer_id WITH =, during WITH &&)
  WHERE (status IN ('confirmed', 'pending'));
```

## Status values
- **Lead:** new → qualified → callback_required / quoted → booked → completed; or not_interested, lost, cancelled, duplicate.
- **Call outcome:** lead_created, booking_confirmed, callback_requested, transferred, emergency_escalated, information_only, missed, failed.

## Indexes
tenant_id on all tables; phone_numbers.number_e164; bookings (engineer_id, during); leads (tenant_id, status); calls.provider_call_id; outbox_events (status, next_attempt_at); knowledge_chunks embedding (HNSW).
