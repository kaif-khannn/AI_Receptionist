# 10 — Deployment guide

## Environments
| | Local | Staging (free) | Production (paid, at first customer) |
|---|---|---|---|
| Backend + worker | Your PC + Cloudflare tunnel | Oracle Cloud Always Free VM (London) with Docker, or local + tunnel | Fly.io / Railway / Render, London/EU, ≥2 instances |
| Database | Neon free or Docker Postgres | Neon free (branch) | Neon paid, London, point-in-time restore |
| Voice | Vapi browser calls (trial credit) | Same | Vapi paid + Twilio UK number with fallback |
| LLM / embeddings | Gemini free tier (test data only) | Same | Paid tier, no-training terms |
| Frontend | Vite dev server | Cloudflare Pages | Cloudflare Pages |
| Files | Local disk | Local disk | Cloudflare R2 |
| Email | Resend free | Resend free | Resend paid, own domain (SPF/DKIM) |
| Monitoring | Logs | Sentry free + UptimeRobot | Same + alerting |

## Upgrade checklist (when the first customer signs)
- [ ] Neon paid plan, London region, PITR enabled; restore tested
- [ ] Backend + worker on paid hosting, `FORWARDED_ALLOW_IPS` set to the platform proxy range
- [ ] `ENVIRONMENT=production` (disables API docs)
- [ ] Paid LLM tier with no-training terms
- [ ] Vapi paid; Twilio UK number (regulatory bundle approved) with fallback URL to the owner's mobile
- [ ] Email on own domain with SPF/DKIM/DMARC
- [ ] Sentry alerts and uptime checks on `/health/ready`
- [ ] DPAs signed with customer and subprocessors; privacy notice published
- [ ] Separate staging and production secrets

## CI/CD
GitHub Actions (`.github/workflows/ci.yml`): backend lint/types/tests, frontend lint/types/build, Docker image build. Deployment workflows are added in Phase 9.

## Backups and recovery
Neon PITR in production. Quarterly restore drill into a Neon branch. Document RPO/RTO in Phase 9.
