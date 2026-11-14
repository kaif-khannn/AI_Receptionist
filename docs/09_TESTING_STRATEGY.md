# 09 — Testing strategy

## Layers
| Layer | Tool | Runs |
|---|---|---|
| Unit | pytest | CI, every push |
| API / integration (real Postgres) | pytest + Postgres service container | CI |
| Tenant isolation | pytest: every endpoint and tool called cross-tenant must be denied | CI |
| Concurrency | Parallel booking attempts on one slot | CI |
| Conversation evals | Scripted caller (LLM) vs agent prompt + real tools, graded against expectations | CI (nightly) + before release |
| Voice | Manual browser/phone calls: noise, interruptions, long turns, accents | Before release |
| Load | Concurrent tool-call load test | Before production |
| Restore | Restore a Neon backup to a branch and verify | Before production, then quarterly |

## Scenario suite
| Scenario | Expected |
|---|---|
| Boiler installation enquiry | Explains approved packages; asks relevant questions |
| Asks price | Approved price + conditions; never guesses |
| Asks about warranty | Approved terms only |
| Speaks at length | Not cut off |
| Interrupts the AI | AI stops and listens |
| Incomplete details | Targeted clarification |
| Postcode outside area | Explains; offers permitted next step |
| Requests appointment | Real availability; confirms only after backend success |
| Two callers, same slot | One succeeds, other offered alternatives |
| Gas smell / CO concern | Immediate safety script; no sales dialogue |
| Asks for a human | Transfer or callback |
| Voice provider unavailable | Fallback routing works |
| Worker / email unavailable | Calls continue; events retry later |
| Cross-tenant access | Denied and logged |

## Release gates
No cross-tenant exposure · no double bookings under concurrency · no invented prices/warranty · no false booking confirmations · no sales talk in emergencies · handover and fallback tested · lead extraction validated on labelled calls · p50/p95 voice latency measured · retried notifications never duplicate.
