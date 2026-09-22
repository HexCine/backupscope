# Direct snapshot verification

`backupscope verify` avoids a fragile two-step operation: redirecting a listing
and remembering to check restic's exit status. It captures metadata from restic,
waits for successful completion, validates the full listing, and applies exactly
the same policy as offline `check`. No runtime Python dependencies are added.

## First run

1. Install restic and configure access as you already do for backups. Environment
   variables such as `RESTIC_REPOSITORY` and `RESTIC_PASSWORD_FILE` are inherited.
   Do not paste passwords into policy files, reports or command arguments.
2. Capture Docker inventory and create a draft policy using the README commands.
3. Review mappings, host, required tags, dump freshness and explicit ignores.
4. Run:

```sh
backupscope verify --inventory inventory.local.json --policy policy.local.json --latest --format html --output coverage.html
```

`--latest` selects one snapshot with the policy host and every required tag.
Additional tags are allowed. With no required tags, the newest snapshot of that
host wins, regardless of its backup stream. Add tags when the host has multiple
independent backup jobs. Restic's `RESTIC_HOST` default does not replace the
explicit host from the policy. Freshness is evaluated after capture finishes;
this command has no frozen `--at` time option.

For a specific incident, use `--snapshot-id` followed by the full lowercase
64-character ID instead. A returned different ID is an error. Host or tag
mismatches remain unknowns, even when the listing command exits 0. Commas and
surrounding whitespace in policy tags need explicit-ID selection, because the
restic tag filter splits and trims tag values.

## What happens on failure

Restic runs with `--no-lock --no-cache ls --json`, without path filters. Its
stdout is streamed to private temporary storage, bounded at 128 MiB. The report
is produced only after EOF, exit 0 and successful parsing. The default capture
timeout is 300 seconds; set `--timeout SECONDS` up to 3600. All existing parser
limits still apply. A local or network repository is supported by restic;
BackupScope does not implement backend protocols.

| Outcome | BackupScope exit | Report |
| --- | --- | --- |
| Listing completed; policy met | 0 | Yes |
| Listing completed; missing paths or stale evidence | 1 | Yes |
| Listing completed; unknowns such as wrong identity | 2 | Yes, with diagnostics |
| Restic failure, timeout, malformed/oversized listing | 2 | No |
| Existing output path or invalid local configuration | 2 | No replacement |

Every nonzero restic code is a failure, including codes this version has not
seen before. Errors include the exit code but withhold raw restic stderr to avoid
exposing credentials or backend details. Run restic directly for diagnostics.
No password prompt is available: stdin is closed. See [security](../SECURITY.md)
for backend helpers, process termination, temporary files and concurrent prune.

## Running after a backup

Refresh inventory each time; otherwise a recently added mount can be absent
from the evidence itself. Keep the reviewed policy between runs. This POSIX
shell example writes each run into its own private directory and propagates
the check's exit code:

```sh
#!/bin/sh
set -eu
umask 077
run_dir=$(mktemp -d "${TMPDIR:-/tmp}/backupscope.XXXXXXXX")
backupscope inventory --host homebox --output "$run_dir/inventory.json"
set +e
backupscope verify --inventory "$run_dir/inventory.json" \
  --policy /etc/backupscope/policy.json --latest \
  --format html --output "$run_dir/report.html"
status=$?
set -e
printf 'BackupScope exit %s; run directory: %s\n' "$status" "$run_dir"
exit "$status"
```

Use your scheduler's existing logging/alerting for exits 1 and 2. Some exit-2
failures intentionally leave no report, so monitoring must check the process
status. Configure retention for these run directories. The example does not
delete old evidence or set up a scheduler. Use a fixed snapshot ID from your
backup job when overlapping jobs would make `--latest` ambiguous.

Capture completion does not prove that all intended files were backed up, that
their bytes are intact, or that a database can be restored. Preserve integrity
checks and restore drills. Offline checks are still useful when repository
access cannot be given to the machine running BackupScope.

Primary references: [restic exit codes and JSON](https://restic.readthedocs.io/en/stable/075_scripting.html)
and [restic tag parsing](https://github.com/restic/restic/blob/v0.19.1/internal/data/tag_list.go).
