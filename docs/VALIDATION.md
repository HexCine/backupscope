# Validation record — 0.1.0

Executed locally on Windows on **2026-09-22**. This is an initial implementation,
not a production deployment report. Fixtures contain generated data only.

| Check | Observed result |
| --- | --- |
| Unit and CLI suite, Python 3.14.5 | 79 passed |
| Unit and CLI suite, Python 3.11.15 | 79 passed |
| Source and wheel build, hatchling 1.32.4 | Both built successfully |
| Fresh-venv wheel install, Python 3.14.5 | Offline install; no runtime dependencies; CLI exits 1/0/2 verified |
| Fresh-venv wheel install, Python 3.11.15 | Same checks passed outside the source tree |
| Real restic 0.19.1 repository and restore | Experiment below passed |
| Workflow static validation, actionlint 1.7.12 | Passed |
| HTML report, desktop and 390 px mobile viewport | Visually inspected; no page overflow; JSON disclosure works |
| Real Docker discovery locally | Not run: Docker daemon unavailable |
| GitHub Actions OS matrix | Configured; no hosted run is claimed in this record |

The 79-test suite covers missing/new/read-only mounts, shared volume consumers,
path boundaries, empty and special nodes, required-file age and size, global
freshness and identity, expired/unused ignores, retained failures alongside
unknowns, strict JSON validation, Docker command projection, error exits,
exclusive output writes and HTML escaping. Parser cases include both restic
discriminators, duplicate headers/nodes and invalid ancestors.

The wheel verifier exercises the installed public CLI and example outcomes; it
does not rerun the entire unit suite against the installed wheel. It removes
source import overrides, installs using `--no-index --no-deps` into a fresh
venv, runs outside the checkout and verifies that an existing output survives
a refused overwrite.

## Real restic experiment

Run `python scripts/restic_integration.py --restic /path/to/restic`.
The script creates its own temporary repository and generated files. The
Docker mount inventory in this experiment is **synthetic**; restic backup,
integrity check, listing and restore are real.

1. Back up the generated directory with its documents folder excluded.
2. `restic check --read-data` exits **0**: stored data is internally consistent.
3. BackupScope exits **1** for the missing mapped documents path.
4. Make a complete backup; BackupScope exits **0**.
5. Restore the generated file and compare its contents with the source.

Observed summary:

```json
{
  "restic": "restic 0.19.1 compiled with go1.26.4 on windows/amd64",
  "excluded_backup_integrity_check": 0,
  "excluded_path_check": 1,
  "complete_path_check": 0,
  "restored_fixture_sha256": "675bfa80306ea6aadbb4710e38887683d2a04df6f4653b13a2ce597ce56a2889",
  "docker_inventory": "synthetic Linux mount projection; restic backup and restore are real"
}
```

The Windows binary came from the official restic v0.19.1 GitHub release.
Its downloaded archive SHA-256 was checked against release metadata:
`da948ad707ed690426473aaba2046cd61f8f90f6f0e7dab6be0d5796531de67d`.
The binary is not bundled in BackupScope.

## Reproduce remaining platform checks

CI defines six Python/OS combinations (3.11 and 3.14 on Linux, Windows and
macOS), clean wheel verification, a checksummed restic integration and Docker
discovery on Linux. A configured workflow is not evidence of successful runs.

`scripts/docker_integration.py` needs a running Linux Docker daemon. It creates
its own uniquely named, never-started Alpine container with a temporary read-only
bind mount, checks project-scoped discovery, and removes only that container.
It may pull the official Alpine image. It does not inspect arbitrary containers.

## Limits of these results

No real-user backup was inspected; no user interviews, load testing on a large
production repository, Linux/macOS local execution or live Docker integration
is claimed. Path presence is not file completeness, integrity, database
consistency or proof of recoverability. See [POLICY.md](POLICY.md).
