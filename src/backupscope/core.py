"""Evaluate explicit path-presence requirements; never certify restoreability."""
from collections import Counter
from . import __version__
from .inventory import validate_inventory
from .validation import absolute, fields, need, number, relative, text, timestamp, utc_now


def selector(rule):
    kind = rule["type"]
    need(kind in ("bind", "volume"), "Rule type must be bind or volume")
    source = absolute(rule["source"], "rule source") if kind == "bind" else text(rule["source"], "rule volume", 256)
    return kind, source


def validate_policy(policy):
    fields(policy, {"version", "host", "max_age_hours", "max_inventory_age_hours", "required_tags", "mappings", "ignores"}, {"version", "host"}, "policy")
    need(type(policy["version"]) is int and policy["version"] == 1, "Unsupported policy version")
    text(policy["host"], "policy host", 256)
    for name in ("max_age_hours", "max_inventory_age_hours"):
        number(policy.get(name, 24), name, minimum=0.001)
    tags = policy.get("required_tags", [])
    need(isinstance(tags, list) and len(tags) <= 100, "policy tags: expected at most 100 tags")
    for tag in tags:
        text(tag, "policy tag", 256)
    mappings, ignores, targets = {}, {}, set()
    for key in ("mappings", "ignores"):
        need(isinstance(policy.get(key, []), list) and len(policy.get(key, [])) <= 5000, "policy: at most 5000 rules")
    for rule in policy.get("mappings", []):
        fields(rule, {"type", "source", "snapshot_path", "required_files", "allow_empty", "min_files", "min_bytes"}, {"type", "source", "snapshot_path"}, "mapping")
        key = selector(rule)
        need(key not in mappings, "Duplicate mapping selector")
        path = absolute(rule["snapshot_path"], "mapping snapshot_path")
        need(path != "/" and path not in targets, "Each mapped resource needs a distinct non-root snapshot path")
        targets.add(path)
        need(type(rule.get("allow_empty", False)) is bool, "allow_empty must be boolean")
        number(rule.get("min_files", 1), "min_files", maximum=200000, integer=True)
        number(rule.get("min_bytes", 0), "min_bytes", maximum=2**63-1, integer=True)
        need(not rule.get("allow_empty") or (rule.get("min_files", 0) == 0 and rule.get("min_bytes", 0) == 0), "allow_empty conflicts with positive minimums")
        required = rule.get("required_files", [])
        need(isinstance(required, list) and len(required) <= 100, "At most 100 required files per mapping")
        required_paths = set()
        for entry in required:
            fields(entry, {"path", "min_bytes", "max_age_hours"}, {"path"}, "required file")
            p = relative(entry["path"])
            need(p not in required_paths, "Duplicate required file")
            required_paths.add(p)
            number(entry.get("min_bytes", 1), "required file min_bytes", maximum=2**63-1, integer=True)
            if "max_age_hours" in entry:
                number(entry["max_age_hours"], "required file max_age_hours", minimum=0.001)
        mappings[key] = {**rule, "snapshot_path": path}
    for rule in policy.get("ignores", []):
        fields(rule, {"type", "source", "reason", "expires_at"}, {"type", "source", "reason"}, "ignore")
        key = selector(rule)
        need(key not in mappings and key not in ignores, "Duplicate or conflicting ignore selector")
        text(rule["reason"], "ignore reason", 1000)
        if "expires_at" in rule:
            timestamp(rule["expires_at"], "ignore expiry")
        ignores[key] = rule
    return mappings, ignores


def under(path, root):
    return path == root or path.startswith(root.rstrip("/") + "/")


def analyze(inventory, catalog, policy, now=None):
    resources = validate_inventory(inventory)
    mappings, ignores = validate_policy(policy)
    moment = timestamp(now or utc_now())
    snapshot, nodes = catalog["snapshot"], catalog["nodes"]
    findings, unknowns, rows, used = [], [], [], set()

    def add(code, message, resource=None, unknown=False):
        entry = {"code": code, "message": message}
        if resource:
            entry["resource"] = resource
        (unknowns if unknown else findings).append(entry)

    def age(value, maximum, label, code, resource=None):
        hours = (moment - timestamp(value)).total_seconds() / 3600
        if hours < -5 / 60:
            add("BSU01", label + " is more than five minutes in the future", resource, True)
        elif hours > maximum:
            add(code, label + " exceeds the configured age limit", resource)
        return round(hours, 3)

    snapshot_age = age(snapshot["time"], policy.get("max_age_hours", 24), "Snapshot", "BS004")
    inventory_age = age(inventory["captured_at"], policy.get("max_inventory_age_hours", 24), "Inventory", "BS005")
    trusted = inventory["host"] == policy["host"] == snapshot["hostname"]
    if not trusted:
        add("BSU02", "Inventory, policy and snapshot host identities must match", unknown=True)
    if not set(policy.get("required_tags", [])) <= set(snapshot["tags"]):
        trusted = False
        add("BSU03", "Snapshot lacks a required policy tag", unknown=True)
    if not resources:
        add("BSU04", "No mounts were supplied; empty discovery is not evidence of backup coverage", unknown=True)

    # Index counts by ancestor once. Avoid scanning all nodes for every mount.
    totals = Counter()
    sizes = Counter()
    for path, node in nodes.items():
        if node["type"] != "file":
            continue
        parent = path
        while parent:
            totals[parent] += 1
            sizes[parent] += node["size"]
            parent = parent.rsplit("/", 1)[0]
    for resource in resources:
        key = (resource["type"], resource["source"])
        label = ":".join(key)
        row = {**resource, "resource": label, "status": "unknown", "snapshot_path": None, "files": 0, "bytes": 0, "detail": "Unsupported mount; manual review required"}
        rows.append(row)
        if resource["type"] == "tmpfs":
            row.update(status="ephemeral", detail="Docker tmpfs is not persistent storage")
            continue
        if resource["type"] not in ("bind", "volume"):
            add("BSU05", "Unsupported Docker mount type", label, True)
            continue
        used.add(key)
        if key in ignores:
            ignore = ignores[key]
            if "expires_at" in ignore and timestamp(ignore["expires_at"]) <= moment:
                add("BS006", "Ignore expired; review the mount or renew its documented reason", label)
                row.update(status="failed", detail="Expired ignore")
            else:
                row.update(status="ignored", detail=ignore["reason"])
            continue
        rule = mappings.get(key, {})
        root = rule.get("snapshot_path", resource["host_path"])
        row["snapshot_path"] = root
        if not trusted:
            row["detail"] = "Snapshot identity does not match the policy"
            continue
        before = (len(findings), len(unknowns))
        node = nodes.get(root)
        row.update(files=totals[root], bytes=sizes[root])
        if node is None:
            add("BS001", "Mapped root is absent from the selected snapshot", label)
        elif node["type"] not in ("file", "dir"):
            add("BSU06", "Mapped root is a symlink or special node; target contents are not proved", label, True)
        elif row["files"] == 0 and not rule.get("allow_empty", False):
            add("BSU07", "Directory has no regular-file evidence; allow_empty must be explicit", label, True)
        else:
            if row["files"] < rule.get("min_files", 0 if rule.get("allow_empty") else 1) or row["bytes"] < rule.get("min_bytes", 0):
                add("BS002", "Observed regular-file count or byte count is below the policy minimum", label)
        for requirement in rule.get("required_files", []):
            path = root.rstrip("/") + "/" + requirement["path"]
            actual = nodes.get(path)
            if not actual or actual["type"] != "file":
                add("BS003", "Required regular file is absent: " + requirement["path"], label)
                continue
            if actual["size"] < requirement.get("min_bytes", 1):
                add("BS003", "Required file is smaller than its minimum: " + requirement["path"], label)
            if "max_age_hours" in requirement:
                if actual["mtime"] is None:
                    add("BSU08", "Required file lacks mtime: " + requirement["path"], label, True)
                else:
                    age(actual["mtime"], requirement["max_age_hours"], "Required file " + requirement["path"], "BS008", label)
        row["status"] = ("unknown" if len(unknowns) > before[1] else
                         ("missing" if node is None else "failed") if len(findings) > before[0] else
                         "observed")
        row["detail"] = "Path-presence requirements met; content integrity and restoreability are untested" if row["status"] == "observed" else "Review diagnostics for this resource"
    for key in sorted((set(mappings) | set(ignores)) - used):
        add("BS007", "Policy selector matches no current mount; stale inventory, rename or policy drift", ":".join(key))
    counts = dict(Counter(row["status"] for row in rows))
    if rows and all(row["status"] in ("ignored", "ephemeral") for row in rows):
        add("BSU09", "Every mount was excluded; no persistent path was checked", unknown=True)
    return {
        "schema_version": 1, "tool_version": __version__, "checked_at": moment.isoformat().replace("+00:00", "Z"),
        "snapshot": snapshot, "snapshot_age_hours": snapshot_age, "inventory_age_hours": inventory_age,
        "rows": rows, "findings": findings, "unknowns": unknowns,
        "summary": {"mounts": len(rows), "statuses": counts, "findings": len(findings), "unknowns": len(unknowns)},
        "exit_code": 2 if unknowns else 1 if findings else 0,
        "scope": "Selected snapshot path presence and freshness only. No full-file comparison, content verification, application consistency or restore test.",
    }


def draft_policy(inventory):
    resources = validate_inventory(inventory)
    return {"version": 1, "host": inventory["host"], "max_age_hours": 24, "max_inventory_age_hours": 24,
            "required_tags": [], "mappings": [{"type": r["type"], "source": r["source"], "snapshot_path": r["host_path"]} for r in resources if r["type"] in ("volume", "bind")], "ignores": []}
