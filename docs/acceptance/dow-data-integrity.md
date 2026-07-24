# Dow monitor data integrity acceptance

Date: 2026-07-24

Status: pending implementation and production verification.

Required semantic evidence:

- a closed HK session ending at 13:15 is classified as `SESSION_GAP` and
  reports the missing 13:16-15:59 tail;
- a complete closed HK session remains `LIVE`;
- every overview mini chart renders the latest 80 bars and only signals inside
  that window;
- production ClickHouse and the Dow overview show a complete 01347.HK session.
