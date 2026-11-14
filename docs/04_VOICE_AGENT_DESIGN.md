# 04 — Voice agent design

*Prompts and tool schemas live in `agent/` from Phase 3.*

## Call start
1. Twilio receives the call → Vapi.
2. Vapi sends `assistant-request` to `POST /api/v1/voice/inbound`.
3. Backend resolves the tenant from the **called number** (never from caller input).
4. If `ai_enabled` is false → return a transfer to the business's fallback number.
5. Otherwise return the shared assistant template filled with this tenant's name, greeting, hours, voice and tool server URL.

## Conversation states
Greeting (discloses it is an AI; recording notice if enabled) → Listening → Intent detection → Clarification → Explanation → Qualification → Recommendation → Booking → Escalation → Closing.

## Listening behaviour
- Barge-in on; agent stops promptly when interrupted.
- Endpointing tuned so normal pauses aren't treated as end of turn.
- British English voice, UK postcode and date/time conventions.
- **Read-back:** phone number and postcode are repeated for confirmation. Caller ID offered as default contact number.
- Low-confidence transcription never triggers a commitment.

## Tools
| Tool | Source of truth |
|---|---|
| get_business_info | SQL |
| search_services | SQL |
| get_service_price | SQL |
| compare_packages | SQL |
| check_service_area | postcodes.io + SQL |
| answer_question | pgvector (approved docs only) |
| check_availability | SQL; creates short slot holds |
| book_appointment | Transaction + exclusion constraint |
| create_lead | SQL (idempotent per call) |
| request_callback | SQL |
| transfer_to_human | Vapi transfer to business number |
| escalate_emergency | SQL + urgent outbox event |

All tools: authenticate Vapi, derive tenant from the call, validate input, record outcome, use idempotency keys, never return internal IDs or secrets. Tool errors return a safe message the agent can say.

## Safety (gas / carbon monoxide)
Detected by **keyword rules first** (e.g. "smell gas", "gas leak", "carbon monoxide", "CO alarm", "headache and dizzy near boiler"), then by the LLM.

- **Gas smell:** stop sales dialogue. Tell the caller to call the National Gas Emergency Service on **0800 111 999**; avoid ignition sources, open doors and windows, turn off gas at the meter only if they know how.
- **CO:** leave the affected area, get fresh air, call emergency services/0800 111 999; seek medical help if symptomatic.
- Never troubleshoot, diagnose, or instruct opening a boiler.
- Only claim Gas Safe registration if verified in business records.
- Post-call: urgent owner alert + incident record (worker).

## Post-call
`end-of-call-report` → verify → store transcript, summary, structured fields (name, phone, postcode, service, urgency, intent, next action) → outbox → contact/lead upsert → owner email.
