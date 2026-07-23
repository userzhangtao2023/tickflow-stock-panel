# DOW realtime watch panel authority decision

- Date: 2026-07-23
- Decision: The user approved `docs/superpowers/specs/2026-07-23-dow-realtime-watch-panel-design.md` as the authoritative TickFlow specification for the DOW realtime watch panel.
- Scope: `SPEC-DOW-WATCH-001` is authoritative while its bounded implementation exception is active.
- Exception: `EXC-DOW-WATCH-IMPLEMENTATION-001` permits the empty indexed requirement list through the approved staged Tasks 2-12. Task 12 promotes all ten requirements only after backend, frontend, and 01347.HK semantic evidence exist; the exception ends at that promotion or on 2026-08-06, whichever comes first. See `docs/superpowers/plans/2026-07-23-dow-realtime-watch-panel.md` Task 12.
- Constraint: TickFlow consumes, and does not redefine, the lower-layer `longbridge-stock` DOW semantics.
