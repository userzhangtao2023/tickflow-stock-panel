# Dow Watch Overview Loading

## REQ-DOW-WATCH-OVERVIEW-LOAD-001

The Dow-monitor overview API MUST load the persisted timeframe-state collection
at most once per request. It MUST NOT deserialize the complete state collection
again for each monitored symbol or timeframe.

Because state publication uses temporary files followed by atomic replacement,
the overview bulk read MUST consume a complete old-or-new snapshot without
waiting for the writer lock.

After the initial persisted snapshot has been loaded, overview reads MUST reuse
an in-process immutable snapshot instead of reparsing the state file. Successful
state writes and symbol removals MUST atomically publish the corresponding
updated in-process snapshot after the file replacement succeeds.

The bulk-read path MUST preserve the existing market filter, five-timeframe
state payloads, source timestamp, latest notification, runtime last-success
timestamp precedence, and persisted last-success fallback semantics.

For the current production monitor set, the authenticated Hong Kong and
all-market overview endpoints MUST complete within two seconds under the normal
production workload so that the page does not remain in its loading state.

## REQ-DOW-WATCH-OVERVIEW-LOAD-002

When the Dow-monitor page URL contains a supported `market` query value
(`all`, `cn`, `hk`, or `us`), the page MUST use that value for its initial
overview and notification requests and select the matching market tab. Invalid
or missing values MUST fall back to `all`.
