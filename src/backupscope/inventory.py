"""Redacted Docker mount inventory; no daemon access during offline checks."""
import json
import subprocess
from .validation import InputError, absolute, fields, need, text, timestamp, utc_now


def validate_inventory(data):
    fields(data, {"version", "host", "captured_at", "containers"}, {"version", "host", "captured_at", "containers"}, "inventory")
    need(type(data["version"]) is int and data["version"] == 1, "Unsupported inventory version")
    text(data["host"], "inventory host", 256)
    timestamp(data["captured_at"], "inventory captured_at")
    need(isinstance(data["containers"], list) and len(data["containers"]) <= 1000, "inventory: at most 1000 containers")
    resources, names = {}, set()
    for container in data["containers"]:
        fields(container, {"name", "mounts"}, {"name", "mounts"}, "container")
        name = text(container["name"], "container name", 256)
        need(name not in names, "Duplicate container name")
        names.add(name)
        mounts = container["mounts"]
        need(isinstance(mounts, list) and len(mounts) <= 100, "container: at most 100 mounts")
        destinations = set()
        for mount in mounts:
            fields(mount, {"type", "source", "destination", "read_only", "volume"}, {"type", "source", "destination", "read_only"}, "mount")
            kind = text(mount["type"], "mount type", 40)
            destination = absolute(mount["destination"], "mount destination")
            need(destination not in destinations, "Duplicate destination in a container")
            destinations.add(destination)
            need(type(mount["read_only"]) is bool, "mount read_only: expected boolean")
            if kind in ("volume", "bind"):
                source = absolute(mount["source"], "mount source")
                identifier = text(mount.get("volume"), "volume name", 256) if kind == "volume" else source
            else:
                need(isinstance(mount["source"], str), "mount source: expected text")
                source = mount["source"]
                identifier = name + ":" + destination
            key = (kind, identifier)
            item = resources.setdefault(key, {"type": kind, "source": identifier, "host_path": source, "owners": []})
            need(item["host_path"] == source, "A volume name resolves to conflicting host paths")
            item["owners"].append({"container": name, "destination": destination, "read_only": mount["read_only"]})
    need(len(resources) <= 5000, "inventory: at most 5000 unique mounts")
    return sorted(resources.values(), key=lambda r: (r["type"], r["source"]))


def from_inspect(data, host, captured_at):
    need(isinstance(data, list), "Docker inspect must be an array")
    containers = []
    for c in data:
        need(isinstance(c, dict) and isinstance(c.get("Mounts"), list), "Invalid Docker mount projection")
        mounts = []
        for m in c["Mounts"]:
            need(isinstance(m, dict), "Invalid Docker mount")
            need(type(m.get("RW")) is bool, "Docker mount RW is missing")
            mount = {"type": m.get("Type"), "source": m.get("Source", ""), "destination": m.get("Destination"), "read_only": not m["RW"]}
            if m.get("Type") == "volume":
                mount["volume"] = m.get("Name")
            mounts.append(mount)
        containers.append({"name": text(c.get("Name"), "Docker container name").lstrip("/"), "mounts": mounts})
    inventory = {"version": 1, "host": host, "captured_at": captured_at, "containers": containers}
    validate_inventory(inventory)
    return inventory


def command(args):
    try:
        result = subprocess.run(args, capture_output=True, timeout=30, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise InputError("Docker command unavailable or timed out; check the selected Docker context") from exc
    need(result.returncode == 0, "Docker command failed; check daemon access and context (raw stderr withheld)")
    need(len(result.stdout) <= 8 * 1024 * 1024, "Docker output exceeds 8 MiB")
    try:
        return result.stdout.decode("utf-8")
    except UnicodeError as exc:
        raise InputError("Docker output is not UTF-8") from exc


def collect(host, project=None):
    args = ["docker", "container", "ls", "--all", "--quiet", "--no-trunc"]
    if project:
        text(project, "project", 256)
        args += ["--filter", "label=com.docker.compose.project=" + project]
    ids = command(args).split()
    need(len(ids) <= 1000 and all(len(i) == 64 and all(c in "0123456789abcdef" for c in i) for i in ids), "Unexpected Docker container identifiers")
    result = []
    # Project only fields needed for coverage. Env, labels and commands never leave Docker.
    template = '{"Name":{{json .Name}},"Mounts":{{json .Mounts}}}'
    for offset in range(0, len(ids), 50):
        output = command(["docker", "container", "inspect", "--format", template, *ids[offset:offset + 50]])
        try:
            result.extend(json.loads(line) for line in output.splitlines() if line.strip())
        except ValueError as exc:
            raise InputError("Invalid Docker projection JSON") from exc
    return from_inspect(result, host, utc_now())
