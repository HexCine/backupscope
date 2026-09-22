"""Read a single unfiltered restic ls --json listing, without file contents."""
from pathlib import Path
from .validation import InputError, absolute, need, number, parse_json, text, timestamp


def read_catalog(path):
    target = Path(path)
    need(not target.is_symlink(), "Listing symlinks are not accepted")
    with target.open("rb") as stream:
        return parse_catalog(stream)


def parse_catalog(stream):
    """Parse a binary stream; callers must establish capture completion separately."""
    snapshot, nodes, total, segments = None, {}, 0, 0
    for index in range(200002):
        raw = stream.readline(1024 * 1024 + 1)
        if not raw:
            break
        total += len(raw)
        need(len(raw) <= 1024 * 1024 and total <= 128 * 1024 * 1024, "Restic listing exceeds line/128 MiB limit")
        try:
            line = raw.decode("utf-8-sig" if index == 0 else "utf-8")
        except UnicodeError as exc:
            raise InputError("Restic listing must be UTF-8") from exc
        need(bool(line.strip()), "Restic listing contains an empty record")
        item = parse_json(line)
        need(isinstance(item, dict), "Restic listing record must be an object")
        kind = item.get("message_type", item.get("struct_type"))
        if "message_type" in item and "struct_type" in item:
            need(item["message_type"] == item["struct_type"], "Conflicting restic record types")
        if kind == "snapshot":
            need(snapshot is None and not nodes, "Expected exactly one snapshot header, first")
            identifier = text(item.get("id"), "snapshot id", 64)
            need(len(identifier) == 64 and all(c in "0123456789abcdef" for c in identifier), "Expected a full lowercase snapshot ID")
            timestamp(item.get("time"), "snapshot time")
            host = text(item.get("hostname"), "snapshot hostname", 256)
            tags = item.get("tags", [])
            if tags is None:
                tags = []
            need(isinstance(tags, list) and len(tags) <= 100, "Invalid snapshot tags")
            for tag in tags:
                text(tag, "snapshot tag", 256)
            snapshot = {"id": identifier, "time": item["time"], "hostname": host, "tags": tags}
        elif kind == "node":
            need(snapshot is not None, "Snapshot header must precede nodes")
            path = absolute(item.get("path"), "snapshot node path")
            segments += path.count("/")
            need(segments <= 1000000, "Restic listing exceeds path work budget")
            need(path not in nodes, "Duplicate snapshot node path")
            node_type = text(item.get("type"), "snapshot node type", 40)
            size = item.get("size", 0)
            number(size, "node size", maximum=2**63-1, integer=True)
            mtime = item.get("mtime")
            if mtime is not None:
                timestamp(mtime, "node mtime")
            nodes[path] = {"type": node_type, "size": size, "mtime": mtime}
            need(len(nodes) <= 200000, "Restic listing exceeds 200000 nodes")
        else:
            raise InputError("Unexpected restic record; use unfiltered restic ls --json, not backup or snapshots output")
    else:
        raise InputError("Restic listing exceeds record limit")
    need(snapshot is not None, "Restic listing has no snapshot")
    for path in nodes:
        parent = path.rsplit("/", 1)[0]
        while parent:
            need(parent not in nodes or nodes[parent]["type"] == "dir", "Snapshot node has a non-directory ancestor")
            parent = parent.rsplit("/", 1)[0]
    return {"snapshot": snapshot, "nodes": nodes}
