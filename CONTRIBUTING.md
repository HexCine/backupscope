# Contributing

Start with a small sanitized inventory, policy and listing that reproduce a
problem. Replace hostnames, usernames and private path components consistently.
Never attach credentials, full Docker inspect output or backup file contents.

Run the README's development commands. Add a regression that demonstrates the
behavior independently of the implementation. Changes to verdicts need a model
explanation and, where possible, evidence from real Docker/restic behavior.

Keep unknowns explicit, preserve known findings in incomplete reports, and avoid
executing user-supplied shell commands. Runtime dependencies require a clear
installation/security tradeoff. Documentation must distinguish fixture results
from actual user adoption and restore guarantees.

Useful first contributions: small versioned fixtures from different restic
versions; anonymized containerized-restic path mappings; examples of monitoring
integration that check restic's exit status before consuming a listing.
