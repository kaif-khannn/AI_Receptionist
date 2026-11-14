# 08 — Security and compliance

*Technical planning summary, not legal advice. Get professional advice on UK GDPR and processing agreements before launch.*

## Security controls
| Area | Control |
|---|---|
| Authentication | Argon2id hashing; httpOnly secure cookies; short-lived access + rotating refresh tokens; login rate limit |
| Authorisation | Roles: owner, manager, engineer, platform_admin; checked on every route |
| Tenant isolation | Backend scoping + Postgres RLS (`FORCE`), non-owner DB role; automated cross-tenant tests |
| Webhooks | Secret/signature verification, timestamp window, event-ID replay protection |
| LLM boundary | Model never supplies tenant IDs; tools validate all input; no secrets/internal IDs returned |
| API | Schema validation, rate limiting, secure headers, CORS allow-list, docs off in production |
| Secrets | Env vars on hosting platform; integration credentials encrypted at rest; rotation process |
| Logging | Structured logs with request IDs; no PII in logs; Sentry with `send_default_pii=False` |
| Data | TLS everywhere; Neon encryption at rest; backups + tested restore |
| Audit | Audit log for config, booking and sensitive data access |
| Kill switch | Per-tenant `ai_enabled`; calls go to fallback number |

## Privacy (UK GDPR)
- AI disclosure at the start of every call; recording/transcription notice where used.
- **Recording off by default.** Transcripts retained 90 days by default (tenant-configurable), then purged by the worker.
- Data minimisation: collect only what the enquiry needs.
- Data-subject requests: export and delete by contact.
- Data-processing agreements with each business customer (we are processor) and with subprocessors (Twilio, Vapi, LLM provider, Neon, email, hosting).
- UK/EU hosting regions; document any transfers (e.g. US-based voice/LLM providers).
- **Free-tier LLM APIs may use data for training → test data only.** Production uses paid tiers with no-training terms.

## Gas and CO safety
See [04_VOICE_AGENT_DESIGN.md](04_VOICE_AGENT_DESIGN.md#safety-gas--carbon-monoxide). Gas Safe and F-gas claims only when verified in onboarding records.
