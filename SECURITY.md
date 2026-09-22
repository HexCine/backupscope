# Security and evidence boundaries

The current release is an early 0.2.0. Offline `check` reads supplied evidence.
`verify` contacts the configured repository through an installed restic binary.
Inventory discovery invokes installed Docker with fixed argument vectors,
never a shell. Only Name/Mounts are requested. No secret store or telemetry is
present. Do not run arbitrary substituted Docker binaries from an untrusted PATH.

The same trust requirement applies to restic and `--restic`. Direct verification
uses a fixed argument vector, never a shell, with `--no-lock --no-cache` and
closed stdin. Restic inherits the process environment, including repository,
password-file/password-command and backend configuration. Restic may invoke
configured helpers such as ssh or rclone; those remain part of your trusted
setup. BackupScope does not store credentials or echo restic stdout/stderr on
failure. Consult restic directly for detailed authentication errors.

Captured stdout is buffered in bounded chunks into a private temporary file
(maximum 128 MiB), removed when the capture context closes. No report is emitted
until EOF, exit 0 and parsing succeed. Timeouts and capture-limit errors kill
and reap the direct restic process. Backend helper descendants are not managed
by BackupScope; configure their own timeouts if needed. Avoid concurrent prune
operations because `--no-lock` deliberately does not acquire a repository lock.

Listings and inventory can reveal infrastructure names and private file paths.
Keep operational exports private; the .gitignore covers `*.local.json` and
`*.local.jsonl`, but review all files before sharing. Reports contain paths and
metadata, not backup contents. HTML escapes text and has no JavaScript.

Inputs are bounded (see POLICY.md); this is not a hardened adversarial sandbox.
Leaf symlinks are rejected for input files and outputs use exclusive creation.
There is no defense against a concurrent local actor replacing parent paths or
changing files during reading. Work with stable exported files in a private
directory. Disk failure can leave a partial newly created output.

An unfiltered export with a successful restic exit is required. The checker
cannot authenticate a listing, detect every truncation at a valid line boundary,
or prove a capture covered every relevant host/container. Unmounted volumes and
container writable layers need separate policy. Never delete backups or approve
a risky migration solely because this checker returns 0.

For a sensitive report, use GitHub private vulnerability reporting if enabled;
otherwise request a private contact channel without posting the sensitive
details. No separate security mailbox is configured for this initial release.
