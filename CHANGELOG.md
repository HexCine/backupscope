# Changelog

## 0.2.1 — 2026-09-22

- Add a responsive, offline EN/RU first-run guide with copyable demo commands.
- Add a Russian quickstart, expected outcomes and troubleshooting links in the README.
- HTML reports distinguish incomplete evidence and suggest the next review action for each diagnostic.


## 0.2.0 — 2026-09-22

- `verify` checks a snapshot directly through installed restic, with automatic
  selection by policy host and all required tags, or a full explicit snapshot ID.
- Bounded private capture, timeout, no-cache/no-lock reads, and discarded partial
  output on every nonzero restic exit. Existing output files remain protected.
- Text, JSON and HTML reports distinguish observed capture completion from a
  supplied offline listing. Offline policy and exit-code behavior is preserved.
- Real child-process regression tests for errors, stalls and output floods;
  restic integration exercises host/tag selection and authentication failures.
- Direct verification and automation guide; wheel verifier follows package version.

## 0.1.0 — 2026-09-22

- Redacted read-only Docker mount inventory and explicit saved-export timestamp.
- Offline restic listing contracts, exact path mapping and shared-volume owners.
- Snapshot/inventory freshness, tags, required files and stale dump detection.
- Visible justified ignores, expiry, stale selectors and explicit unknowns.
- Text, JSON and script-free responsive HTML reports; dependency-free wheel.
- Regression suite, isolated wheel verifier and real local restic restore fixture.
