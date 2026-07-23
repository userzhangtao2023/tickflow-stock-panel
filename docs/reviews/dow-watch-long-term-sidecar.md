# Independent requirements-to-evidence review: Dow watch long-term sidecar

| Requirement | Implementation | Executable evidence | Review |
| --- | --- | --- | --- |
| `REQ-DOW-WATCH-LONG-CLIENT-001` | `dow_monitor_client.py`, `dow_monitor_service.py` | strict boolean/enum/date-time rejection, ISO JSON serialization, and complete persistence assertions | Authoritative enum fields are constrained while free-text names/evidence remain unconstrained. Complete sidecar is copied; no field is recomputed. |
| `REQ-DOW-WATCH-LONG-EVENT-001` | `dow_monitor_service.py` | simultaneous activation plus forming, provisional, null/empty/whitespace-line suppression | Eligibility exactly checks FINAL, non-provisional, trimmed non-empty line ID, lower-layer stage, and literal operation. Families are distinct and keys remain five-part. |
| `REQ-DOW-WATCH-LONG-RECOVERY-001` | `dow_monitor_service.py` | sustained dedupe, reactivation, first-state crash, existing-state crash with padded identity | State derives from public local snapshot or `chart.longTerm`; recovery scans immutable public notifications. Local and long-term sequence maxima and normalized identities are independent. |

Lower-layer authority was reviewed before this consumer: TickFlow does not
construct anchors, classify a long pattern, promote a provisional candidate,
or infer a stage. The full engine object is deep-copied into each notification,
so historical evidence cannot be mutated by later state.

Conclusion: all three active requirements have implementation, executable
tests, semantic acceptance, and independent review, subject to fresh focused
suite and specification-checker results in the Task 6b report.
