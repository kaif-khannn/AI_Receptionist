# 05 — HVAC knowledge engine

*Built in Phase 6.*

## Two retrieval paths
| Information | Source of truth |
|---|---|
| Prices, package inclusions, hours, postcode coverage, availability | Structured SQL (never vector search) |
| FAQs, service explanations, brochures, approved warranty text | pgvector, filtered by tenant + approved status |
| Booking confirmation | Transactional booking API only |

## Ingestion flow
1. Owner uploads PDF / DOCX / CSV or uses forms.
2. Text extracted, cleaned, chunked; commercial facts (prices, warranty terms) proposed as **drafts**.
3. Owner reviews and approves. Nothing is used by the AI until approved.
4. Approved chunks embedded (Gemini embeddings in testing) and stored with version and provenance.
5. When a document or price changes, old chunks are archived and caches invalidated.

## Owner-configurable categories
Business profile · services · packages · warranty and policies · sales guidance (incl. discount limits) · operations (postcodes, engineer capabilities, appointment types, escalation rules).

## Guardrails
- Retrieval always filtered by `tenant_id` and `status = approved`.
- Missing or conflicting info → agent says it will confirm with the team and creates a callback.
- Dashboard includes a "test the AI's answer" screen showing the retrieved sources.
