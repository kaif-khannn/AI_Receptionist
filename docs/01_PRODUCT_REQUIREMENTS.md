# 01 — Product requirements

## Product promise
Never lose an HVAC enquiry because nobody answered the phone. The AI receptionist listens, understands the heating/boiler requirement, explains the company's real services and packages, qualifies the enquiry, books an appointment or callback, and sends the owner a useful summary.

## Target customer
- UK domestic heating and boiler companies, 1–5 engineers.
- Owner is usually on a job and cannot answer the phone.
- Inbound calls only in V1.

## Personas
| Persona | Needs |
|---|---|
| **Caller** (homeowner/landlord) | Quick, clear answers; a booked visit or a promised callback; safety help in an emergency |
| **Owner** | No missed leads; accurate info given to callers; summaries on their phone; control of the AI |
| **Manager** | Manage bookings, leads and engineers |
| **Engineer** | See their own bookings (read-mostly) |
| **Platform operator** (us) | Onboard businesses, monitor health, track usage and margin |

## V1 scope
| Capability | V1 |
|---|---|
| Inbound AI calls, natural conversation, barge-in | ✅ |
| Explain services, packages, approved prices, warranty | ✅ |
| Lead qualification and detail capture (read-back) | ✅ |
| Postcode / service-area check | ✅ |
| Appointment booking and callback requests | ✅ |
| Owner notifications and call summaries | ✅ (email) |
| Human transfer and gas/CO safety escalation | ✅ |
| Transcripts; recording (off by default) | ✅ |
| Per-tenant kill switch and fallback routing | ✅ |
| Usage metering per tenant | ✅ |
| Outbound calls, SMS/WhatsApp, route optimisation, mobile app | Later |

## Enquiry categories
Boiler repair · boiler installation/replacement · servicing (incl. landlord gas safety where offered) · heating systems · air conditioning/other (only if the company offers it) · emergencies (safety-first, never sales).

## Product principles
1. **Listen first, sell second.**
2. **Never fabricate.** Only approved company data; otherwise offer a callback.
3. **Understand before recommending.**
4. **Never overpromise.** No guaranteed diagnosis, price or slot unless verified by the backend.

## Definition of success (first vertical slice)
A caller speaks naturally with the AI, gets accurate answers grounded in the test business's approved catalogue, requests a service, and the enquiry reliably appears in the owner's system with correct details and a clear next action.

Acceptance criteria and release gates: see [09_TESTING_STRATEGY.md](09_TESTING_STRATEGY.md).
