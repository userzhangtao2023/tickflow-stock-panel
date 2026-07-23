# Independent requirements-to-evidence review: Dow watch long-term sidecar

| Requirement | Implementation | Executable evidence | Review |
| --- | --- | --- | --- |
| `REQ-DOW-WATCH-LONG-CLIENT-001` | `dow_monitor_client.py`, `dow_monitor_service.py` | strict parsing plus complete persistence assertions | Complete sidecar is copied; no field is recomputed. Local response members retain their existing paths. |
| `REQ-DOW-WATCH-LONG-EVENT-001` | `dow_monitor_service.py` | simultaneous local/long activation and forming suppression | Eligibility exactly checks FINAL, line ID, lower-layer stage, and literal operation. Families are distinct and keys remain five-part. |
| `REQ-DOW-WATCH-LONG-RECOVERY-001` | `dow_monitor_service.py` | sustained dedupe, reactivation, first-state crash | State derives from public local snapshot or `chart.longTerm`; recovery scans immutable public notifications. Local and long-term sequence maxima are filtered independently. |

Lower-layer authority was reviewed before this consumer: TickFlow does not
construct anchors, classify a long pattern, promote a provisional candidate,
or infer a stage. The full engine object is deep-copied into each notification,
so historical evidence cannot be mutated by later state.

Conclusion: all three active requirements have implementation, executable
tests, semantic acceptance, and independent review, subject to fresh focused
suite and specification-checker results in the Task 6b report.
