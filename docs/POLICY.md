# Policy and diagnostic reference

See [examples/policy.json](../examples/policy.json) for a complete contract.
Unknown keys, duplicate JSON keys, nonfinite numbers and ambiguous paths fail.
All times require explicit timezones. Paths use absolute POSIX spelling with
no dot segments, repeated separators, backslashes or control characters.

## Root policy

`version: 1` and `host` are required. `host` must match both inventory `host`
and snapshot `hostname`. `max_age_hours` and `max_inventory_age_hours` default
to 24. `required_tags` defaults to an empty array; configure it to select the
intended backup stream. Additional snapshot tags are allowed. Times more than
five minutes in the future produce an unknown rather than negative-age success.

## Mappings

Each mapping has `type` (`bind` or `volume`), `source`, and `snapshot_path`.
For binds, source is the exact absolute host path. For volumes, source is the
exact runtime volume name, including Compose's prefix. It is not a container
destination or a Compose YAML logical key. Without a mapping, the exact host
source path is used. There is no glob or parent-prefix remapping.

Distinct explicit mappings cannot share the same snapshot root. Root `/` is
not allowed as an explicit mapping. You must review the generated draft if
discovery contains root bind mounts or duplicate physical paths.

The root node must actually occur in the supplied listing. A regular file root
supports single-file binds or explicitly mapped dump artifacts. Directory roots
need regular-file evidence below them; symlinks/special nodes do not count.
The default minimum is one regular file and zero bytes. `min_files` and
`min_bytes` may strengthen the requirement. The count includes all descendant
regular files by path boundary, not by substring (`/data-old` is not `/data`).

An existing empty directory can pass only with `allow_empty: true`. It cannot
be combined with positive minimums. This does not permit an absent root.

`required_files` strengthens a directory mapping:

```json
{"path":"postgres.sql","min_bytes":100,"max_age_hours":24}
```

`path` is a relative file path, `min_bytes` defaults to 1, and modification-age
checking is optional. An old file in a new snapshot stays old. Missing mtime
means unknown when freshness is required. This does not parse or restore SQL.

## Ignores and inventory scope

An ignore uses the same type/source selector and a nonempty `reason`, with
optional ISO-8601 `expires_at`. At expiry it becomes a failure. Unused mapping
or ignore selectors are failures so renames do not silently leave dead rules.
All ignored mounts and their owners remain in the report. Excluding every
resource produces an unknown; tmpfs is separately labeled ephemeral.

Read-only mounts are included. Shared volumes are grouped but all consumer
containers/destinations are shown. The same volume name resolving to multiple
source paths is rejected. Unknown Docker mount types stay unknown.

Discovery includes stopped containers; use `--project` for an explicit smaller
scope. Discovery is not atomic across container changes. No unmounted volumes,
container writable layers, other Docker contexts or other hosts are inferred.
When normalizing saved inspect JSON, `--captured-at` must be its original capture
time, not the current time; full inspect input is never echoed into inventory.

## Codes

| Code | Meaning |
| --- | --- |
| BS001 | Mapped root absent |
| BS002 | File/byte minimum not met |
| BS003 | Required regular file absent or too small |
| BS004 / BS005 | Snapshot / inventory too old |
| BS006 | Ignore expired |
| BS007 | Policy selector has no matching mount |
| BS008 | Required file too old |
| BSU01 | Evidence timestamp in the future |
| BSU02 / BSU03 | Host mismatch / missing required tags |
| BSU04 | Empty mount inventory |
| BSU05 | Unsupported mount type |
| BSU06 | Root is a symlink or special node |
| BSU07 | No regular-file evidence in a directory |
| BSU08 | Missing required mtime |
| BSU09 | Every resource excluded |

Rows labeled `observed` meet local path requirements, but global freshness or
identity findings can still make the report fail. Always inspect `exit_code`,
`findings` and `unknowns`, not only a row. Unknowns take exit-code precedence.
`missing` means the mapped root is absent; `failed` means another local
requirement failed, such as an old dump, a minimum size or an expired ignore.

## Bounds and evidence limits

JSON inventory/policy files: 8 MiB each. At most 1000 containers, 100 mounts per
container, 5000 unique resources/rules and 100 required files per rule. Listings:
128 MiB, 1 MiB per line, 200000 nodes and one million cumulative path segments.
Paths: 4096 characters and 64 segments. Larger inputs fail instead of passing.

Use exactly one complete, unfiltered `restic ls --json` export whose command
exited zero. Both `struct_type` and newer `message_type` discriminators work;
if supplied together they must agree. Invalid/truncated JSON, duplicate nodes,
multiple headers and non-directory ancestors are rejected. A valid-line-boundary
truncation cannot always be detected. Listing presence is not a comparison with
the current source tree or authentication of the snapshot. The default is a
mount/path presence check, not full backup completeness.

Primary format references: [restic JSON scripting](https://restic.readthedocs.io/en/stable/075_scripting.html)
and [Docker inspect](https://docs.docker.com/reference/cli/docker/inspect/).
