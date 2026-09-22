# BackupScope

[![CI](https://github.com/HexCine/backupscope/actions/workflows/ci.yml/badge.svg)](https://github.com/HexCine/backupscope/actions/workflows/ci.yml)

**Find Docker data paths missing from your restic snapshot before you need them.**

You add a volume, move an application to a bind mount, or rename a stack. The
backup job still succeeds. The new data may not be in the backup at all.
BackupScope compares a redacted Docker mount inventory with an actual restic
file listing and an explicit path-presence policy. It works alongside your
existing backup tool, offline, without a server, account or paid API.

Version **0.1.0**, an early release seeking real-world workflow feedback.
No claim of universal backup coverage or production validation.

## A reproducible reason to use it

The integration fixture creates a real restic repository, excludes one folder,
and successfully runs `restic check --read-data`. BackupScope still catches the
missing path. After a complete backup, the contract passes; the fixture then
restores a generated file and compares its bytes. See [validation](docs/VALIDATION.md).

The two checks answer different questions: repository integrity does not tell
you whether every data source you intended to include was selected.

## Try it

Python 3.11+; no runtime dependencies. From this source directory:

```sh
git clone https://github.com/HexCine/backupscope.git
cd backupscope
python -m pip install .
backupscope check --inventory examples/inventory.json --snapshot examples/missing.jsonl --policy examples/policy.json --at 2026-09-22T13:00:00Z
```

Expected exit **1**: an absent documents mount and an old database dump. Replace
`missing.jsonl` with `present.jsonl` for exit **0**. `--at` freezes time for these
fixtures; omit it for current operational checks.

For a portable report, add `--format html --output coverage.html`. The HTML has
no scripts or remote assets and includes expandable JSON evidence. Output files
are created exclusively; existing files are never overwritten by `--output`.
The module form `python -m backupscope` is equivalent to the console command.
An already generated [example report](examples/report.html) is included; download
or open it locally in a browser. It uses only the public synthetic fixtures.

## Use your own Docker + restic setup

On a Docker host with Linux-container mount paths:

```sh
backupscope inventory --host homebox --output inventory.local.json
backupscope init --inventory inventory.local.json --output policy.local.json
```

Discovery uses only `docker container ls` and `docker container inspect` with a
Name/Mounts projection. It includes stopped containers and read-only mounts;
read-only application data can still need backup. `--project NAME` explicitly
restricts discovery to that Compose project. Credentials, environment values,
commands and Docker labels are not included in the exported inventory.

**Review the generated policy.** Use the exact restic snapshot hostname for
`host`. Add tags identifying your backup stream. Adjust `snapshot_path` if
restic runs in a container, or if a database volume maps to a logical dump.
Automatic fallback is the exact host source path, never a guessed volume name.

Export one full snapshot listing using your existing restic authentication:

```sh
restic ls --json --host homebox --tag daily latest > snapshot.local.jsonl
backupscope check --inventory inventory.local.json --snapshot snapshot.local.jsonl --policy policy.local.json --format html --output coverage.html
```

**Only use the listing if restic exited 0.** Do not filter its paths, splice
listings, or evaluate a partially written file. For monitoring, finish the
export into a temporary file, check the exit status, then replace your local
listing atomically before invoking BackupScope. A listing is supplied evidence,
not an authenticated or signed attestation. Prefer a full snapshot ID instead
of `latest` for a reproducible incident report.

BackupScope itself never reads backup file contents, performs a restore,
stops containers, or mutates a backup repository. The restic export accesses
whichever repository you have already configured. On PowerShell 7, redirecting
native stdout preserves suitable UTF-8 output; ensure UTF-8 on other shells.

## What it checks

- Every discovered bind mount or named/anonymous volume has regular-file
  evidence at its exact mapped path, or an explicit ignore with a reason.
- Snapshot and inventory freshness, matching host identity and required tags.
- Optional minimum file/byte counts and required relative files, including
  dump size and modification-age requirements.
- New mounts, stale policy selectors, expired ignores and shared-volume users.
- Unknowns remain visible: symlinks, special mount types, empty directories,
  mismatched identities and missing freshness information never become green.

See [policy and diagnostic reference](docs/POLICY.md). JSON report schema is 1.

| Exit | Meaning |
| --- | --- |
| 0 | Supplied path-presence and freshness requirements met |
| 1 | Known missing paths, stale evidence or policy failures |
| 2 | Unknowns, malformed input or I/O error; reports retain known failures |

## Boundaries that matter

An observed path proves neither that **all** its current files were backed up,
nor that their contents are intact. A root with one file can pass the default
presence check even when another file was excluded. Add known required files
and minimums, and retain `restic check` plus real restore drills. A recent
snapshot containing an old SQL dump is caught only when you configure an mtime
requirement. A nonempty SQL file does not prove database consistency.

Only one supplied snapshot/host is checked. Inventory excludes unmounted Docker
volumes, container writable layers and undiscovered hosts. Scoped discovery has
scoped coverage. Linux-container POSIX paths are supported, not native Windows
container paths, UNC mounts or Kubernetes discovery. Full limits and caveats
are in [POLICY.md](docs/POLICY.md) and [SECURITY.md](SECURITY.md).

## Existing tools and contribution

[restic](https://github.com/restic/restic) provides the storage and integrity
engine. [Backrest](https://github.com/garethgeorge/backrest) and
[Offen docker-volume-backup](https://github.com/offen/docker-volume-backup)
manage backups. [Arkeep](https://github.com/arkeep-io/arkeep) is a broader
server/agent platform with a coverage-map roadmap; this idea is not unique.
[Databasus](https://github.com/databasus/databasus) is a stronger fit if you need
database backup scheduling and automated restore verification.

BackupScope's narrow choice is a small, read-only checker over exported evidence
with no migration to a new backup platform. If this proves more useful as an
integration in an existing project, prefer that over duplicating an orchestrator.
See [research and the 30-day plan](docs/RESEARCH.ru.md).

## Development

```sh
python -m pip install -e . pytest==9.1.1 build==1.6.1
python -m pytest -q
python -m build
python scripts/verify_wheel.py
python scripts/restic_integration.py --restic /path/to/restic
```

The wheel verifier installs offline into a fresh environment and tests the CLI
outside the source tree. The optional restic integration uses only disposable
generated fixtures. CI covers Python 3.11/3.14 on three operating systems, plus
Linux restic and Docker discovery integration. Actual execution results are in
[VALIDATION.md](docs/VALIDATION.md); configured jobs are not evidence of a run.

MIT licensed. See [CONTRIBUTING](CONTRIBUTING.md), [security](SECURITY.md) and
[changelog](CHANGELOG.md).
