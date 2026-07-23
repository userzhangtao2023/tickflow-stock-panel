# Decision: bridge the authoritative long-term Dow sidecar

- Decision ID: `DEC-DOW-WATCH-LONG-001`
- Date: 2026-07-23
- Owner: alwinzhang
- Status: approved

The watch panel will consume the complete `longTerm` object from the
Longbridge external-bar adapter. It will preserve that object for display and
will treat only lower-layer FINAL `TRIGGER`/`CONFIRMED` buy/sell triggers with
a line ID as independent notification activations.

Local and long-term families share the fixed five-part event-key shape but
have independent activation sequence and crash recovery. TickFlow does not
copy or reinterpret `DOW-LONG-001`.
